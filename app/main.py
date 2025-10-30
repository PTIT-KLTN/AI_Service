from dotenv import load_dotenv
from typing import Dict, List
import json

from app.services.invoke_model_service import BedrockModelService
from app.services.bedrock_kb_service import BedrockKBService
from app.services.validation_service import ValidationService
from app.services.ontology_service import OntologyService
from app.services.unit_converter_service import UnitConverterService 
from app.services.conflict_service import ConflictDetectionService
from app.services.ingredient_resolver import IngredientResolver
from app.services.suggestion_service import SuggestionService
load_dotenv()

class ShoppingCartPipeline:
    def __init__(self):
        self.extractor = BedrockModelService()
        self.kb_service = BedrockKBService()
        self.converter = UnitConverterService()
        self.validator = ValidationService()
        self.ontology = OntologyService()
        self.conflicts = ConflictDetectionService()
        
        self.ingredient_resolver = IngredientResolver(self.ontology)
        self.suggestion_service = SuggestionService(self.ontology, self.converter, self.validator)


    def process(self, user_input: str) -> dict:
        # Extract dish name + extra ingredients
        extracted = self.extractor.extract_dish_name(user_input)
        return self._build_response(extracted, user_input)


    def process_image(self, image_b64: str, description: str = "", image_mime: str = "image/png") -> dict:
        extracted = self.extractor.extract_dish_from_image(image_b64, description, image_mime)
        return self._build_response(extracted)


    def _build_response(self, extracted: dict, user_query: str = "") -> dict:

        if not extracted:
            return {
                'status': 'error',
                'error': 'Không có dữ liệu trích xuất.',
                'error_type': 'extraction_failed',
                'dish': {'name': ''},
                'cart': None,
                'suggestions': [],
                'similar_dishes': [],
                'warnings': [],
                'insights': [],
                'guardrail': None,
            }

        guardrail_info = extracted.get('guardrail')
        warnings = self._normalize_warnings(extracted.get('warnings'))
        
        # Check if request was blocked by guardrails
        is_guardrail_blocked = (
            guardrail_info and 
            guardrail_info.get('action') in ['block', 'blocked'] and
            guardrail_info.get('triggered') is True
        )
        
        # Add guardrails messages
        guardrail_messages = extracted.get('guardrail_messages')
        if guardrail_messages:
            has_guardrail_warnings = any(
                w.get('details', {}).get('policy_id')
                for w in warnings
            )

            if not has_guardrail_warnings:
                warnings.extend(self._guardrail_warnings(guardrail_info, guardrail_messages))

        elif guardrail_info and guardrail_info.get('triggered'):
            warnings.extend(self._guardrail_warnings(guardrail_info, None))


        # Get dish name
        dish_name = extracted.get('dish_name')
        extra_ingredients = extracted.get('ingredients', [])
        excluded_ingredients = extracted.get('excluded_ingredients', [])

        if not dish_name:
            # Case 1: Guardrail blocked
            if is_guardrail_blocked:
                return {
                    'status': 'guardrail_blocked',
                    'error': 'Nội dung vi phạm chính sách an toàn',
                    'error_type': 'guardrail_violation',
                    'dish': {'name': ''},
                    'cart': None,
                    'suggestions': [],
                    'similar_dishes': [],
                    'warnings': self._unique_warnings(warnings),
                    'insights': [],
                    'guardrail': guardrail_info,
                }
            
            # Case 2: No dish but has ingredients → Process ingredients only
            elif extra_ingredients:
                # Add warning that no dish was found
                warnings.append({
                    'message': 'Không tìm thấy tên món, chỉ xử lý danh sách nguyên liệu',
                    'severity': 'info',
                    'source': 'system',
                    'details': {}
                })
                # Skip to processing extra ingredients (set recipe to empty)
                recipe = {'ingredients': []}
                recipe_ing = []
            
            # Case 3: No dish and no ingredients → Error
            else:
                return {
                    'status': 'error',
                    'error': 'Không tìm thấy tên món ăn trong yêu cầu',
                    'error_type': 'dish_not_found',
                    'dish': {'name': ''},
                    'cart': None,
                    'suggestions': [],
                    'similar_dishes': [],
                    'warnings': self._unique_warnings(warnings),
                    'insights': [],
                    'guardrail': guardrail_info,
                }
        else:
            # Get recipe when dish_name exists
            recipe = self._get_recipe(dish_name)
            if not recipe.get('ingredients'):
                return {
                    'status': 'error',
                    'error': f'Không tìm thấy công thức cho món "{dish_name}"',
                    'error_type': 'recipe_not_found',
                    'dish': {'name': dish_name},
                    'cart': None,
                    'suggestions': [],
                    'similar_dishes': [],
                    'warnings': self._unique_warnings(warnings),
                    'insights': [],
                    'guardrail': guardrail_info,
                }
            recipe_ing = self._normalize_recipe_items(recipe.get('ingredients', []))
        
        extra_norm = self._normalize_extra(extra_ingredients)
        
        # Filter out excluded ingredients
        if excluded_ingredients:
            recipe_ing = self._filter_excluded_ingredients(recipe_ing, excluded_ingredients)
        
        # Merge: công thức + nguyên liệu thêm
        all_ingredients = recipe_ing + [it for it in extra_norm if it.get('ingredient_id')]
        if not all_ingredients:
            return {
                'status': 'error',
                'error': 'Không có nguyên liệu hợp lệ sau khi xử lý',
                'error_type': 'no_valid_ingredients',
                'dish': {'name': dish_name or ''},
                'cart': None,
                'suggestions': [],
                'similar_dishes': [],
                'warnings': self._unique_warnings(warnings),
                'insights': [],
                'guardrail': guardrail_info,
            }
        
        # Convert units
        cart_items = self.converter.normalize_ingredients(all_ingredients)
        
        # Add category
        for item in cart_items:
            ing_info = self.ontology.get_ingredient(item['ingredient_id'])
            item['category'] = ing_info.get('category', 'other') if ing_info else 'other'
        
        # Get suggestions
        suggestions = self._get_suggestions([item['ingredient_id'] for item in cart_items], dish_name or '')
        
        # Similar dishes
        similar = self.ontology.search_similar_dishes(
            [item['ingredient_id'] for item in all_ingredients], 
            min_match=3
        )

        # Conflict detection warnings
        conflict_ingredients = []
        
        # Add cart items with IDs
        for item in cart_items:
            conflict_ingredients.append({
                'ingredient_id': item.get('ingredient_id'),
                'name_vi': item.get('name_vi') or item.get('name')
            })
        
        # Add extra ingredients (may or may not have IDs)
        for ing in extra_ingredients:
            if isinstance(ing, dict):
                conflict_ingredients.append({
                    'ingredient_id': ing.get('ingredient_id'),
                    'name_vi': ing.get('name', '')
                })
        
        # Check conflicts
        conflict_results = self.conflicts.check_conflicts(dish_name or '', conflict_ingredients)
        conflict_warnings = [
            {
                'message': conflict.get('message', ''),
                'severity': conflict.get('severity', 'warning'),
                'source': 'conflict',
                'details': conflict,
            }
            for conflict in conflict_results
        ]
        warnings.extend(conflict_warnings)
        insights = self.conflicts.build_explanations(dish_name or '', conflict_results)
        
        # ===== Contextual Grounding  =====
        assistant_text = extracted.get('response') or ""
        if assistant_text and recipe_ing and dish_name:
            # Build nguồn từ RAG 
            src_lines = []
            for it in recipe_ing:
                nm = it.get('name_vi') or it.get('name') or ''
                qty = it.get('quantity', '')
                unit = it.get('unit', '')
                line = f"- {nm}".strip()
                if qty or unit:
                    line += f" ({qty} {unit})".strip()
                src_lines.append(line)
            source_text = f"Công thức {dish_name}:\n" + "\n".join(src_lines)

            # Gọi apply_guardrail 
            ar_resp = self.extractor.bedrock_client.apply_contextual_grounding(
                source_text=source_text,
                user_query=user_query or f"Món {dish_name}",
                model_output=assistant_text
            )

            assessments = (ar_resp or {}).get("assessments") or []
            if assessments:
                # Nếu guardrail -> thay bằng safe-completion 
                assistant_text = "Xin lỗi, tôi chỉ có thể trả lời dựa trên nội dung công thức/kiến thức đã cung cấp."
                warnings.append({
                    'message': 'Contextual grounding flagged the response; returned safe completion.',
                    'severity': 'warning',
                    'source': 'guardrail',
                    'details': ar_resp,
                })

        return {
            'status': 'success',
            'error': None,
            'error_type': None,
            'dish': {
                'name': dish_name or '',
                'prep_time': recipe.get('prep_time') if dish_name else None,
                'servings': recipe.get('servings') if dish_name else None
            },
            'cart': {
                'total_items': len(cart_items),
                'items': cart_items
            },
            'suggestions': suggestions,
            'similar_dishes': similar[:3],
            'warnings': self._unique_warnings(warnings),
            'insights': insights,
            'guardrail': guardrail_info,
        }

    def _normalize_warnings(self, warnings) -> List[Dict[str, object]]:
        normalized: List[Dict[str, object]] = []
        for warning in warnings or []:
            if isinstance(warning, dict):
                message = warning.get('message') or warning.get('text') or ''
                severity = warning.get('severity', 'warning')
                source = warning.get('source', 'model')
                details = {k: v for k, v in warning.items() if k not in {'message', 'text', 'severity', 'source'}}
                normalized.append({
                    'message': message,
                    'severity': severity,
                    'source': source,
                    'details': details,
                })
            else:
                normalized.append({
                    'message': str(warning),
                    'severity': 'warning',
                    'source': 'model',
                })
        return normalized

    def _guardrail_warnings(self, guardrail_info, guardrail_messages=None) -> List[Dict[str, object]]:
        if not guardrail_info:
            return []
        formatted: List[Dict[str, object]] = []
        for entry in guardrail_messages or []:
            if not isinstance(entry, dict):
                continue
            formatted.append({
                'message': entry.get('message', 'Guardrail đã kích hoạt.'),
                'severity': entry.get('severity', 'warning'),
                'source': entry.get('policy_id', 'guardrail'),
            })

        if not formatted:
            codes = guardrail_info.get('violation_codes') or []
            for code in codes:
                formatted.append({
                    'message': f'Guardrail kích hoạt: {code}',
                    'severity': 'warning',
                    'source': 'guardrail',
                })
        return formatted

    @staticmethod
    def _unique_warnings(warnings: List[Dict[str, object]]) -> List[Dict[str, object]]:
        seen = set()
        unique: List[Dict[str, object]] = []
        for warning in warnings:
            key = (warning.get('source'), warning.get('message'))
            if key in seen:
                continue
            seen.add(key)
            unique.append(warning)
        return unique

    def _get_recipe(self, dish_name: str) -> dict:
        """Get recipe từ RAG KB"""
        recipe = self.kb_service.get_dish_recipe(dish_name)
        if recipe.get('ingredients'):
            return recipe
        
        return {'ingredients': []}
    
    def _normalize_extra(self, extra_ingredients: list) -> list:
        """
        Map extra ingredients sang ontology format - SỬ DỤNG FUZZY MATCHING
        Input: [{"name": "trứng cút", "quantity": "", "unit": ""}]
        Output: [{"ingredient_id": "ing_xxx", "name_vi": "Trứng cút", ...}]
        """
        normalized = []
        
        for item in extra_ingredients:
            name = item.get('name', '').strip()
            if not name:
                continue
            
            # Sử dụng fuzzy matching như recipe ingredients
            matched_id = self._resolve_name_to_ingredient_id(name)
            if matched_id:
                ing_data = self.ontology.ingredients.get(matched_id, {})
                
                # Ensure quantity is always string
                qty = item.get('quantity', '')
                if isinstance(qty, (int, float)):
                    qty = str(qty)
                elif not isinstance(qty, str):
                    qty = ''
                
                normalized.append({
                    'ingredient_id': matched_id,
                    'name_vi': ing_data.get('name_vi', name),
                    'quantity': qty,
                    'unit': str(item.get('unit', ''))
                })
        
        return normalized
    
    def _filter_excluded_ingredients(self, recipe_items: list, excluded: list) -> list:
        """
        Filter out excluded ingredients from recipe using fuzzy matching
        Input excluded: [{"name": "hành lá", "reason": "dị ứng"}]
        """
        if not excluded:
            return recipe_items
        
        # Resolve excluded names to ingredient_ids using fuzzy matching
        excluded_ids = set()
        for exc in excluded:
            name = exc.get('name', '').strip()
            if name:
                matched_id = self._resolve_name_to_ingredient_id(name)
                if matched_id:
                    excluded_ids.add(matched_id)
        
        # Filter recipe items
        filtered = [
            item for item in recipe_items
            if item.get('ingredient_id') not in excluded_ids
        ]
        
        return filtered
    
    def _get_suggestions(self, current_ids: list, dish_name: str = "") -> list:
        """Get ingredient suggestions using SuggestionService."""
        return self.suggestion_service.get_suggestions(current_ids, dish_name)
    
    def _resolve_name_to_ingredient_id(self, name: str):
        """Delegate to IngredientResolver service."""
        return self.ingredient_resolver.resolve_name_to_id(name)

    def _normalize_recipe_items(self, items: list) -> list:
        if not items:
            return []
        normalized = []
        for it in items:
            nm = it.get('name_vi') or it.get('name') or ''
            
            # Skip if no valid name
            if not nm or not str(nm).strip():
                continue
            
            nm = str(nm).strip()
            ing_id = self._resolve_name_to_ingredient_id(nm)
            if not ing_id:
                continue
            
            # Ensure quantity is always string
            qty = it.get('quantity', '')
            if isinstance(qty, (int, float)):
                qty = str(qty)
            elif not isinstance(qty, str):
                qty = ''
            
            normalized.append({
                'ingredient_id': ing_id,
                'name_vi': nm, 
                'quantity': qty,
                'unit': str(it.get('unit', ''))
            })
        return normalized
