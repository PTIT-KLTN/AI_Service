"""
OPTIMIZED VERSION of ShoppingCartPipeline
Implements performance improvements while preserving business logic
"""
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple
import json
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
from collections import OrderedDict

from app.services.invoke_model_service import BedrockModelService
from app.services.bedrock_kb_service import BedrockKBService
from app.services.validation_service import ValidationService
from app.services.ontology_service import OntologyService
from app.services.unit_converter_service import UnitConverterService 
from app.services.conflict_service import ConflictDetectionService
from app.services.ingredient_resolver import IngredientResolver
from app.services.suggestion_service import SuggestionService
from app.services.s3_image_service import S3ImageService

load_dotenv()
logger = logging.getLogger(__name__)


class TTLCache:
    """Simple TTL (Time-To-Live) cache implementation"""
    
    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 3600):
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[any]:
        """Get value from cache if not expired"""
        if key not in self.cache:
            return None
        
        # Check if expired
        if time.time() - self.timestamps[key] > self.ttl_seconds:
            # Remove expired entry
            del self.cache[key]
            del self.timestamps[key]
            return None
        
        # Move to end (LRU)
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def set(self, key: str, value: any) -> None:
        """Set value in cache"""
        # Remove oldest if at capacity
        if len(self.cache) >= self.maxsize and key not in self.cache:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]
        
        self.cache[key] = value
        self.cache.move_to_end(key)
        self.timestamps[key] = time.time()
    
    def clear(self) -> None:
        """Clear all cache"""
        self.cache.clear()
        self.timestamps.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self.cache)


class OptimizedShoppingCartPipeline:
    
    def __init__(self, max_workers: int = 3, recipe_cache_ttl: int = 3600):
        self.extractor = BedrockModelService()
        self.kb_service = BedrockKBService()
        self.converter = UnitConverterService()
        self.validator = ValidationService()
        self.ontology = OntologyService()
        self.conflicts = ConflictDetectionService()
        self.s3_service = S3ImageService()
        
        self.ingredient_resolver = IngredientResolver(self.ontology)
        self.suggestion_service = SuggestionService(self.ontology, self.converter, self.validator)
        
        # Thread pool for parallel operations
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # TTL Cache for KB recipes 
        self._recipe_cache = TTLCache(maxsize=1000, ttl_seconds=recipe_cache_ttl)
        
        # LRU Cache for ingredient resolution
        self._ingredient_id_cache: Dict[str, Optional[str]] = {}
        self._ingredient_info_cache: Dict[str, Dict] = {}
        
        # Pre-build ingredient name index
        self._build_ingredient_index()
        
        logger.info(f"OptimizedShoppingCartPipeline initialized with {max_workers} workers, TTL={recipe_cache_ttl}s")
    
    def _build_ingredient_index(self):
        """Pre-build ingredient name index for O(1) lookup"""
        self._ingredient_name_index = {}
        
        for ing_id, ing_info in self.ontology.ingredients.items():
            # Index by Vietnamese name (lowercase)
            name_vi = ing_info.get('vietnamese_name', '').lower().strip()
            if name_vi:
                self._ingredient_name_index[name_vi] = ing_id
            
            # Index by English name (lowercase)
            name_en = ing_info.get('name', '').lower().strip()
            if name_en:
                self._ingredient_name_index[name_en] = ing_id
        
        logger.info(f"Built ingredient index with {len(self._ingredient_name_index)} entries")

    def process(self, user_input: str) -> dict:
        """Process with optimizations"""
        # Extract dish name + extra ingredients
        extracted = self.extractor.extract_dish_name(user_input)
        return self._build_response(extracted, user_query=user_input, s3_url=None)

    def process_image(self, s3_url: str, description: str = "") -> dict:
        """Process image from S3 URL"""
        # Download image từ S3
        image_data = self.s3_service.download_image_as_base64(s3_url)
        
        if not image_data:
            return self._error_response('image_download_failed', s3_url=s3_url)
        
        # Extract từ image
        extracted = self.extractor.extract_dish_from_image(
            image_data=image_data['data'],
            description=description,
            image_mime=image_data['mime_type']
        )
        
        return self._build_response(extracted, s3_url=s3_url)

    def _build_response(self, extracted: dict, user_query: str = "", s3_url: str = None) -> dict:
        """Build response with optimizations"""
        
        if not extracted:
            return self._error_response('extraction_failed', s3_url=s3_url)

        guardrail_info = extracted.get('guardrail')
        warnings = self._normalize_warnings(extracted.get('warnings'))
        
        # Check if request was blocked by guardrails
        is_guardrail_blocked = (
            guardrail_info and 
            guardrail_info.get('action') in ['block', 'blocked'] and
            guardrail_info.get('triggered') is True
        )
        
        # Process guardrail messages
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

        # Extract ingredients
        dish_name = extracted.get('dish_name')
        extra_ingredients = extracted.get('ingredients', [])
        excluded_ingredients = extracted.get('excluded_ingredients', [])

        # Handle no dish name
        if not dish_name:
            if is_guardrail_blocked:
                return self._error_response('guardrail_violation', guardrail_info, warnings, s3_url=s3_url)
            elif extra_ingredients:
                warnings.append({
                    'message': 'Không tìm thấy tên món, chỉ xử lý danh sách nguyên liệu',
                    'severity': 'info',
                    'source': 'system',
                    'details': {}
                })
                recipe = {'ingredients': []}
                recipe_ing = []
            else:
                return self._error_response('dish_not_found', guardrail_info, warnings, s3_url=s3_url)
        else:
            # Get recipe
            recipe = self._get_recipe(dish_name)
            if not recipe.get('ingredients'):
                return self._error_response('recipe_not_found', guardrail_info, warnings, dish_name, s3_url)
            
            # Batch normalize recipe ingredients
            recipe_ing = self._normalize_recipe_items_batch(recipe.get('ingredients', []))
        
        # Batch normalize extra ingredients
        extra_norm = self._normalize_extra_batch(extra_ingredients)
        
        # Use set for faster lookup
        excluded_ids = self._resolve_excluded_ingredients_batch(excluded_ingredients)
        
        # Filter excluded ingredients using set
        if excluded_ids:
            recipe_ing = [
                item for item in recipe_ing
                if item.get('ingredient_id') not in excluded_ids
            ]
        
        # Merge ingredients
        all_ingredients = recipe_ing + [it for it in extra_norm if it.get('ingredient_id')]
        
        if not all_ingredients:
            return self._error_response('no_valid_ingredients', guardrail_info, warnings, dish_name, s3_url)
        
        # Convert units
        cart_items = self.converter.normalize_ingredients(all_ingredients)
        
        # Batch add categories
        self._add_categories_batch(cart_items)
        
        # Parallel processing for independent operations
        ingredient_ids = [item['ingredient_id'] for item in cart_items]
        
        # Submit parallel tasks
        futures = {
            'suggestions': self.executor.submit(
                self._get_suggestions,
                ingredient_ids,
                dish_name or ''
            ),
            'similar_dishes': self.executor.submit(
                self.ontology.search_similar_dishes,
                [item['ingredient_id'] for item in all_ingredients],
                3  # min_match
            ),
            'conflicts': self.executor.submit(
                self._check_conflicts_parallel,
                dish_name or '',
                cart_items,
                extra_ingredients
            )
        }
        
        # Wait for results
        suggestions = futures['suggestions'].result()
        similar = futures['similar_dishes'].result()
        conflict_warnings, insights = futures['conflicts'].result()
        
        warnings.extend(conflict_warnings)
        
        # Contextual grounding (chỉ khi cần)
        assistant_text = extracted.get('response') or ""
        if assistant_text and recipe_ing and dish_name:
            ar_resp = self._apply_contextual_grounding(
                recipe_ing, dish_name, user_query, assistant_text
            )
            if ar_resp:
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
            's3_url': s3_url or '',
            'dish': {
                'vietnamese_name': recipe.get('vietnamese_name') or dish_name or '',
                'name': recipe.get('name') or '',
                'prep_time': recipe.get('prep_time') if dish_name else None,
                'servings': recipe.get('servings') if dish_name else None
            },
            'cart': {
                'total_items': len(cart_items),
                'items': cart_items
            },
            'suggestions': suggestions,
            'similar_dishes': similar[:3],
            'excluded_ingredients': self._normalize_excluded_ingredients_batch(excluded_ingredients),
            'warnings': self._unique_warnings(warnings),
            'insights': insights,
            'guardrail': guardrail_info,
        }

    
    def _resolve_name_to_ingredient_id_cached(self, name: str) -> Optional[str]:
        """
        Cached version of ingredient resolution
        ✅ OPTIMIZATION: Try exact match first (O(1)), then fuzzy match
        """
        if name in self._ingredient_id_cache:
            return self._ingredient_id_cache[name]
        
        # Try exact match first (much faster)
        name_lower = name.lower().strip()
        if name_lower in self._ingredient_name_index:
            result = self._ingredient_name_index[name_lower]
            self._ingredient_id_cache[name] = result
            logger.debug(f"Exact match for '{name}' -> {result}")
            return result
        
        # Fallback to fuzzy matching
        result = self.ingredient_resolver.resolve_name_to_id(name)
        self._ingredient_id_cache[name] = result
        
        if result:
            logger.debug(f"Fuzzy match for '{name}' -> {result}")
        else:
            logger.debug(f"No match found for '{name}'")
        
        return result
    
    def _get_ingredient_info_cached(self, ingredient_id: str) -> Dict:
        """Cached version of ingredient info lookup"""
        if ingredient_id in self._ingredient_info_cache:
            return self._ingredient_info_cache[ingredient_id]
        
        result = self.ontology.get_ingredient(ingredient_id) or {}
        self._ingredient_info_cache[ingredient_id] = result
        return result

    
    def _normalize_recipe_items_batch(self, items: list) -> list:
        """Batch normalize recipe items"""
        if not items:
            return []
        
        normalized = []
        
        for it in items:
            # Extract Vietnamese name (prioritize vietnamese_name, then name_vi)
            vietnamese_name = str(it.get('vietnamese_name') or it.get('name_vi') or '').strip()
            
            # Extract English name (prioritize name field, then name_en)
            english_name = str(it.get('name') or it.get('name_en') or '').strip()
            
            # Fallback: if vietnamese_name is empty but 'name' exists and english_name is empty,
            # then 'name' might be Vietnamese (old format)
            if not vietnamese_name and it.get('name'):
                vietnamese_name = str(it.get('name')).strip()
                english_name = ''  # Clear english_name in this case
            
            # Skip if no valid Vietnamese name
            if not vietnamese_name:
                continue
            
            # Resolve ingredient ID (with cache)
            ing_id = self._resolve_name_to_ingredient_id_cached(vietnamese_name)
            if not ing_id:
                continue
            
            # Get ingredient info for fallback
            ing_info = self._get_ingredient_info_cached(ing_id)
            
            qty = it.get('quantity', '')
            if isinstance(qty, (int, float)):
                qty = str(qty)
            elif not isinstance(qty, str):
                qty = ''
            
            normalized.append({
                'ingredient_id': ing_id,
                'vietnamese_name': vietnamese_name,
                'name': english_name or ing_info.get('name_en', ''),
                'quantity': qty,
                'unit': str(it.get('unit', ''))
            })
        
        return normalized
    
    def _normalize_extra_batch(self, extra_ingredients: list) -> list:
        """Batch normalize extra ingredients"""
        if not extra_ingredients:
            return []
        
        normalized = []
        
        for item in extra_ingredients:
            # Extract Vietnamese and English names
            vietnamese_name = item.get('vietnamese_name', '').strip() or item.get('name_vi', '').strip() or item.get('name', '').strip()
            english_name = item.get('name', '').strip() or item.get('name_en', '').strip()
            
            if not vietnamese_name:
                continue
            
            matched_id = self._resolve_name_to_ingredient_id_cached(vietnamese_name)
            if matched_id:
                ing_data = self._get_ingredient_info_cached(matched_id)
                
                qty = item.get('quantity', '')
                if isinstance(qty, (int, float)):
                    qty = str(qty)
                elif not isinstance(qty, str):
                    qty = ''
                
                normalized.append({
                    'ingredient_id': matched_id,
                    'vietnamese_name': ing_data.get('vietnamese_name') or ing_data.get('name_vi', vietnamese_name),
                    'name': english_name or ing_data.get('name_en', ''),
                    'quantity': qty,
                    'unit': str(item.get('unit', ''))
                })
        
        return normalized
    
    def _resolve_excluded_ingredients_batch(self, excluded: list) -> set:
        """Batch resolve excluded ingredients to IDs (return set for O(1) lookup)"""
        if not excluded:
            return set()
        
        excluded_ids = set()
        
        for exc in excluded:
            name = exc.get('name', '').strip()
            if name:
                matched_id = self._resolve_name_to_ingredient_id_cached(name)
                if matched_id:
                    excluded_ids.add(matched_id)
        
        return excluded_ids
    
    def _normalize_excluded_ingredients_batch(self, excluded: list) -> list:
        """Batch normalize excluded ingredients"""
        if not excluded:
            return []
        
        normalized = []
        
        for exc in excluded:
            name = exc.get('name', '').strip()
            reason = exc.get('reason', '').strip()
            
            if not name:
                continue
            
            matched_id = self._resolve_name_to_ingredient_id_cached(name)
            
            if matched_id:
                ing_info = self._get_ingredient_info_cached(matched_id)
                normalized.append({
                    'ingredient_id': matched_id,
                    'vietnamese_name': ing_info.get('vietnamese_name') or ing_info.get('name_vi', name),
                    'name': ing_info.get('name') or ing_info.get('name_en', ''),
                    'category': ing_info.get('category', ''),
                    'reason': reason
                })
            else:
                normalized.append({
                    'ingredient_id': '',
                    'vietnamese_name': name,
                    'name': '',
                    'category': '',
                    'reason': reason
                })
        
        return normalized
    
    def _add_categories_batch(self, cart_items: list) -> None:
        """Batch add categories to cart items (in-place)"""
        for item in cart_items:
            ing_info = self._get_ingredient_info_cached(item['ingredient_id'])
            item['category'] = ing_info.get('category', 'other')
            
            # Ensure both vietnamese_name and name fields exist
            if 'vietnamese_name' not in item:
                item['vietnamese_name'] = ing_info.get('vietnamese_name') or ing_info.get('name_vi', '')
            if 'name' not in item:
                item['name'] = ing_info.get('name') or ing_info.get('name_en', '')


    def _check_conflicts_parallel(
        self,
        dish_name: str,
        cart_items: list,
        extra_ingredients: list
    ) -> Tuple[List[Dict], List[Dict]]:
        """Check conflicts and build insights (for parallel execution)"""
        
        conflict_ingredients = []
        
        for item in cart_items:
            conflict_ingredients.append({
                'ingredient_id': item.get('ingredient_id'),
                'vietnamese_name': item.get('vietnamese_name') or item.get('name_vi') or item.get('name')
            })
        
        for ing in extra_ingredients:
            if isinstance(ing, dict):
                conflict_ingredients.append({
                    'ingredient_id': ing.get('ingredient_id'),
                    'vietnamese_name': ing.get('vietnamese_name') or ing.get('name_vi', '') or ing.get('name', '')
                })
        
        conflict_results = self.conflicts.check_conflicts(dish_name, conflict_ingredients)
        
        conflict_warnings = [
            {
                'message': conflict.get('message', ''),
                'severity': conflict.get('severity', 'warning'),
                'source': 'conflict',
                'details': conflict,
            }
            for conflict in conflict_results
        ]
        
        insights = self.conflicts.build_explanations(dish_name, conflict_results)
        
        return conflict_warnings, insights

    
    def _apply_contextual_grounding(
        self,
        recipe_ing: list,
        dish_name: str,
        user_query: str,
        assistant_text: str
    ) -> Optional[Dict]:
        """Apply contextual grounding (only when needed)"""
        
        try:
            src_lines = []
            for it in recipe_ing:
                nm = it.get('vietnamese_name') or it.get('name_vi') or it.get('name') or ''
                qty = it.get('quantity', '')
                unit = it.get('unit', '')
                line = f"- {nm}".strip()
                if qty or unit:
                    line += f" ({qty} {unit})".strip()
                src_lines.append(line)
            
            source_text = f"Công thức {dish_name}:\n" + "\n".join(src_lines)

            ar_resp = self.extractor.bedrock_client.apply_contextual_grounding(
                source_text=source_text,
                user_query=user_query or f"Món {dish_name}",
                model_output=assistant_text
            )

            assessments = (ar_resp or {}).get("assessments") or []
            if assessments:
                return ar_resp
            
            return None
        
        except Exception as e:
            logger.error(f"Contextual grounding error: {e}")
            return None

    # ========== Helper methods (unchanged logic) ==========
    
    def _normalize_warnings(self, warnings) -> List[Dict[str, object]]:
        """Normalize warnings"""
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
        """Build guardrail warnings"""
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
        """Remove duplicate warnings"""
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

        # Check cache first
        cached_recipe = self._recipe_cache.get(dish_name)
        if cached_recipe is not None:
            logger.debug(f"Recipe cache HIT for '{dish_name}'")
            return cached_recipe
        
        # Cache miss - query KB
        logger.debug(f"Recipe cache MISS for '{dish_name}' - querying KB")
        recipe = self.kb_service.get_dish_recipe(dish_name)
        
        # Cache the result
        if recipe.get('ingredients'):
            self._recipe_cache.set(dish_name, recipe)
            return recipe
        
        # Cache empty result too (to avoid repeated failed queries)
        empty_recipe = {'ingredients': []}
        self._recipe_cache.set(dish_name, empty_recipe)
        return empty_recipe
    
    def _get_suggestions(self, current_ids: list, dish_name: str = "") -> list:
        """Get ingredient suggestions"""
        return self.suggestion_service.get_suggestions(current_ids, dish_name)
    
    def _error_response(
        self,
        error_type: str,
        guardrail_info=None,
        warnings=None,
        dish_name: str = '',
        s3_url: str = None
    ) -> dict:
        """Build error response"""
        error_messages = {
            'extraction_failed': 'Không có dữ liệu trích xuất.',
            'guardrail_violation': 'Nội dung vi phạm chính sách an toàn',
            'dish_not_found': 'Không tìm thấy tên món ăn trong yêu cầu',
            'recipe_not_found': f'Không tìm thấy công thức cho món "{dish_name}"',
            'no_valid_ingredients': 'Không có nguyên liệu hợp lệ sau khi xử lý',
            'image_download_failed': 'Không thể tải ảnh từ S3',
        }
        
        status = 'guardrail_blocked' if error_type == 'guardrail_violation' else 'error'
        
        return {
            'status': status,
            'error': error_messages.get(error_type, 'Unknown error'),
            'error_type': error_type,
            's3_url': s3_url or '',
            'dish': {'vietnamese_name': dish_name, 'name': ''},
            'cart': None,
            'suggestions': [],
            'similar_dishes': [],
            'excluded_ingredients': [],
            'warnings': self._unique_warnings(warnings or []),
            'insights': [],
            'guardrail': guardrail_info,
        }
    
    def get_cache_stats(self) -> Dict[str, any]:
        """Get cache statistics for monitoring"""
        return {
            'recipe_cache_size': self._recipe_cache.size(),
            'recipe_cache_maxsize': self._recipe_cache.maxsize,
            'ingredient_id_cache_size': len(self._ingredient_id_cache),
            'ingredient_info_cache_size': len(self._ingredient_info_cache),
            'ingredient_index_size': len(self._ingredient_name_index),
        }
    
    def clear_caches(self):
        """Clear all caches (useful for testing or memory management)"""
        self._recipe_cache.clear()
        self._ingredient_id_cache.clear()
        self._ingredient_info_cache.clear()
        logger.info("All caches cleared")
    
    def __del__(self):
        """Cleanup thread pool"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
