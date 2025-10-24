from dotenv import load_dotenv
from typing import Dict, List
import json

from app.services.invoke_model_service import BedrockModelService
from app.services.bedrock_kb_service import BedrockKBService
from app.services.validation_service import ValidationService
from app.services.ontology_service import OntologyService
from app.services.unit_converter_service import UnitConverterService 
from app.utils import fuzzy_score, tokenize
from app.services.conflict_service import ConflictDetectionService

load_dotenv()

class ShoppingCartPipeline:
    def __init__(self):
        self.extractor = BedrockModelService()
        self.kb_service = BedrockKBService()
        self.converter = UnitConverterService()
        self.validator = ValidationService()
        self.ontology = OntologyService()
        self.conflicts = ConflictDetectionService()


    def process(self, user_input: str) -> dict:
        # Extract dish name + extra ingredients
        extracted = self.extractor.extract_dish_name(user_input)
        # print(f"Extracted from text: {extracted}")
        return self._build_response(extracted, user_input)


    def process_image(self, image_b64: str, description: str = "", image_mime: str = "image/png") -> dict:
        extracted = self.extractor.extract_dish_from_image(image_b64, description, image_mime)
        return self._build_response(extracted)


    def _build_response(self, extracted: dict, user_query: str = "") -> dict:

        if not extracted:
            return {'status': 'error', 'error': 'Không có dữ liệu trích xuất.'}

        guardrail_info = extracted.get('guardrail')
        warnings = self._normalize_warnings(extracted.get('warnings'))
        
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
            status = 'guardrail_blocked' if guardrail_info and guardrail_info.get('action') != 'allow' else 'error'
            response_text = extracted.get('response')
            payload = {
                'status': status,
                'dish': {'name': None},
                'warnings': self._unique_warnings(warnings),
                'response': response_text,
                'guardrail': guardrail_info,
            }
            if status == 'error':
                payload['error'] = 'Không tìm thấy tên món ăn'
                payload.setdefault('response', 'Không tìm thấy tên món ăn')
            return payload
        
        # Get recipe
        recipe = self._get_recipe(dish_name)
        if not recipe.get('ingredients'):
            if not dish_name:
                return {
                'status': 'error',
                'error': f'Không tìm thấy công thức cho "{dish_name}"',
                'warnings': self._unique_warnings(warnings),
            }
        
        recipe_ing = self._normalize_recipe_items(recipe.get('ingredients', []))
        extra_norm = self._normalize_extra(extra_ingredients)
        
        # Filter out excluded ingredients
        if excluded_ingredients:
            recipe_ing = self._filter_excluded_ingredients(recipe_ing, excluded_ingredients)
        
        # Merge: công thức + nguyên liệu thêm
        all_ingredients = recipe_ing + [it for it in extra_norm if it.get('ingredient_id')]
        if not all_ingredients:
            return {'error': 'Không có nguyên liệu hợp lệ'}
        
        # Convert units
        cart_items = self.converter.normalize_ingredients(all_ingredients)
        
        # Add category
        for item in cart_items:
            # print(item)
            ing_info = self.ontology.get_ingredient(item['ingredient_id'])
            item['category'] = ing_info.get('category', 'other') if ing_info else 'other'
        
        # Get suggestions
        suggestions = self._get_suggestions([item['ingredient_id'] for item in cart_items], dish_name)
        
        # Similar dishes
        similar = self.ontology.search_similar_dishes(
            [item['ingredient_id'] for item in all_ingredients], 
            min_match=3
        )

        # Conflict detection warnings
        ingredient_names: List[str] = []
        ingredient_names.extend([item.get('name_vi') or item.get('name') or '' for item in cart_items])
        ingredient_names.extend(
            [
                ing.get('name', '')
                for ing in extra_ingredients
                if isinstance(ing, dict)
            ]
        )
        conflict_results = self.conflicts.check_conflicts(dish_name, ingredient_names)
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
        insights = self.conflicts.build_explanations(dish_name, conflict_results)
        
        # ===== Contextual Grounding  =====
        assistant_text = extracted.get('response') or ""
        if assistant_text and recipe_ing:
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
            'dish': {
                'name': dish_name,
                'prep_time': recipe.get('prep_time'),
                'servings': recipe.get('servings')
            },
            'cart': {
                'total_items': len(cart_items),
                'items': cart_items
            },
            'suggestions': suggestions,
            'similar_dishes': similar[:3],
            'warnings': self._unique_warnings(warnings),
            'insights': insights,
            'assistant_response': assistant_text, 
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
        """Get recipe từ RAG hoặc local KB"""
        # print(f"Fetching RAG recipe for dish: {dish_name}")
        recipe = self.kb_service.get_dish_recipe(dish_name)
        # print(f"RAG recipe for {dish_name}: {recipe}")
        if recipe.get('ingredients'):
            print("Recipe found in RAG KB")
            return recipe
        
        # print("Falling back to local ontology for recipe")
        # local = self.ontology.get_dish_by_name(dish_name)
        # return local if local else {'ingredients': []}
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
                normalized.append({
                    'ingredient_id': matched_id,
                    'name_vi': ing_data.get('name_vi', name),
                    'quantity': item.get('quantity', ''),
                    'unit': item.get('unit', '')
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
        allowed_cats = self._allowed_categories_for_dish(dish_name)
        ban_ids = self._build_exclusion_set(current_ids)

        raw = self.validator.suggest_ingredients(
            seed_ids=current_ids,
            allowed_categories=allowed_cats,
            ban_ids=ban_ids,
            top_k=5,
            ingredients=self.ontology.ingredients
        )

        suggestions = []
        for sug in raw:
            ing = self.ontology.ingredients.get(sug['id'])
            if not ing:
                continue

            suggestion_item = {
                'ingredient_id': sug['id'],
                'name_vi': ing.get('name_vi', ''),
                'quantity': '',
                'unit': '',
                'score': sug['score'],
                'reason': 'Phù hợp với món & chưa có trong giỏ',
            }
            converted = self.converter.normalize_ingredients([suggestion_item])
            if converted:
                suggestions.append(converted[0])

        return suggestions
    
    def _resolve_name_to_ingredient_id(self, name: str):
        if not name:
            return None

        THRESHOLD_A = 0.70  # ngưỡng cho name_vi
        THRESHOLD_B = 0.65  # ngưỡng cho synonyms 
        q_tokens = set(tokenize(name))

        ing_dict = getattr(self.ontology, 'ingredients', {}) or {}

        # ---------- Stage A: chỉ xét name_vi ----------
        best_id = None
        best_score = -1.0
        best_extras = 10**9
        best_len = 10**9

        for ing_id, ing in ing_dict.items():
            cand = ing.get('name_vi') or ''
            if not cand:
                continue
            sc = fuzzy_score(name, cand)
            extras = len(set(tokenize(cand)) - q_tokens)  # ít từ dư hơn thì tốt hơn
            clen = len(cand)

            if (sc > best_score) or (sc == best_score and (extras < best_extras or (extras == best_extras and clen < best_len))):
                best_id, best_score, best_extras, best_len = ing_id, sc, extras, clen

        if best_score >= THRESHOLD_A:
            return best_id

        # ---------- Stage B: xét synonyms nếu Stage A không đủ ----------
        best_id = None
        best_score = -1.0
        best_extras = 10**9
        best_len = 10**9

        for ing_id, ing in ing_dict.items():
            syns = [s for s in ing.get('synonyms', []) if s]
            if not syns:
                continue

            # lấy synonym tốt nhất cho ingredient này
            local_best_sc = -1.0
            local_best_extras = 10**9
            local_best_len = 10**9
            for s in syns:
                sc = fuzzy_score(name, s)
                extras = len(set(tokenize(s)) - q_tokens)
                slen = len(s)
                if (sc > local_best_sc) or (sc == local_best_sc and (extras < local_best_extras or (extras == local_best_extras and slen < local_best_len))):
                    local_best_sc, local_best_extras, local_best_len = sc, extras, slen

            if (local_best_sc > best_score) or (local_best_sc == best_score and (local_best_extras < best_extras or (local_best_extras == best_extras and local_best_len < best_len))):
                best_id, best_score, best_extras, best_len = ing_id, local_best_sc, local_best_extras, local_best_len

        if best_score >= THRESHOLD_B:
            return best_id

        return None


    def _normalize_recipe_items(self, items: list) -> list:
        if not items:
            return []
        normalized = []
        for it in items:
            nm = it.get('name_vi') or it.get('name') or ''
            ing_id = self._resolve_name_to_ingredient_id(nm)
            if not ing_id:
                continue
            normalized.append({
                'ingredient_id': ing_id,
                'name_vi': nm, 
                'quantity': it.get('quantity', ''),
                'unit': it.get('unit', '')
            })
        return normalized

    
    def _build_exclusion_set(self, current_ids: list) -> set:
        exclude = set(current_ids)
        # map tên -> id nhanh
        name_to_id = {}
        for iid, ing in getattr(self.ontology, 'ingredients', {}).items():
            nm = (ing.get('name_vi') or '').strip().lower()
            if nm:
                name_to_id[nm] = iid
            for syn in ing.get('synonyms', []):
                name_to_id[str(syn).strip().lower()] = iid

        # thêm các id suy ra từ tên/synonyms của các id hiện có
        for iid in list(current_ids):
            ing = self.ontology.ingredients.get(iid, {})
            names = [ing.get('name_vi', '')] + ing.get('synonyms', [])
            for n in names:
                mid = name_to_id.get(str(n).strip().lower())
                if mid:
                    exclude.add(mid)
        return exclude
    
    def _allowed_categories_for_dish(self, dish_name: str) -> set:
        cats = set()
        dish = self.ontology.get_dish_by_name(dish_name) or {}
        
        # Lấy category từ ingredient knowledge base
        for it in dish.get('ingredients', []):
            ing_id = it.get('ingredient_id')
            if ing_id:
                ing_data = self.ontology.get_ingredient(ing_id)
                if ing_data:
                    cat = ing_data.get('category')
                    if cat:
                        cats.add(cat)
        
        if cats:
            return cats

        return {
            'seasonings','aromatics','sweeteners','fresh_meat','eggs','beverages',
            'vegetables','herbs'
        }
