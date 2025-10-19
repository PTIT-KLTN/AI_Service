from dotenv import load_dotenv
from app.services.invoke_model_service import BedrockModelService
from app.services.bedrock_kb_service import BedrockKBService
from app.services.validation_service import ValidationService
from app.services.ontology_service import OntologyService
from app.services.unit_converter_service import UnitConverterService 
from app.utils import fuzzy_score, tokenize

load_dotenv()

class ShoppingCartPipeline:
    def __init__(self):
        self.extractor = BedrockModelService()
        self.kb_service = BedrockKBService()
        self.converter = UnitConverterService()
        self.validator = ValidationService()
        self.ontology = OntologyService()

    def process(self, user_input: str) -> dict:
        """
        Process: "Tôi muốn ăn bún bò Huế với trứng cút"
        -> Lấy công thức bún bò Huế + thêm trứng cút vào
        """
        # Extract dish name + extra ingredients
        extracted = self.extractor.extract_dish_name(user_input)
        
        print(f"Extracted from text: {extracted}")
        # if not extracted.get('dish_name'):
        #     return {'error': 'Không tìm thấy tên món ăn'}
        
        return self._build_response(extracted)
    
    def process_image(self, image_b64: str, description: str = "", image_mime: str = "image/png") -> dict:
        """Process pipeline when the primary input is an image."""
        extracted = self.extractor.extract_dish_from_image(image_b64, description, image_mime)
        return self._build_response(extracted)


    def _build_response(self, extracted: dict) -> dict:
        """Build the final response payload from extracted data."""
        if not extracted or not extracted.get('dish_name'):
            return {'error': 'Không tìm thấy tên món ăn'}
        
        dish_name = extracted['dish_name']
        extra_ingredients = extracted.get('ingredients', [])
        
        # Get recipe
        recipe = self._get_recipe(dish_name)
        if not recipe.get('ingredients'):
            return {'error': f'Không tìm thấy công thức cho "{dish_name}"'}
        
        recipe_ing = self._normalize_recipe_items(recipe.get('ingredients', []))
        extra_norm = self._normalize_extra(extra_ingredients)
        
        # Merge: công thức + nguyên liệu thêm
        all_ingredients = recipe_ing + [it for it in extra_norm if it.get('ingredient_id')]
        if not all_ingredients:
            return {'error': 'Không map được nguyên liệu nào từ công thức sang ontology'}
        
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
            'similar_dishes': similar[:3]
        }

    def _get_recipe(self, dish_name: str) -> dict:
        """Get recipe từ RAG hoặc local KB"""
        print(f"Fetching RAG recipe for dish: {dish_name}")
        recipe = self.kb_service.get_dish_recipe(dish_name)
        print(f"RAG recipe for {dish_name}: {recipe}")
        if recipe.get('ingredients'):
            print("Recipe found in RAG KB")
            return recipe
        
        # print("Falling back to local ontology for recipe")
        # local = self.ontology.get_dish_by_name(dish_name)
        # return local if local else {'ingredients': []}
        return {'ingredients': []}
    
    def _normalize_extra(self, extra_ingredients: list) -> list:
        """
        Map extra ingredients sang ontology format
        Input: [{"name": "trứng cút", "quantity": "", "unit": ""}]
        Output: [{"ingredient_id": "ing_xxx", "name_vi": "Trứng cút", ...}]
        """
        normalized = []
        
        for item in extra_ingredients:
            name = item.get('name', '').lower().strip()
            
            # Tìm trong ontology
            for ing_id, ing_data in self.ontology.ingredients.items():
                if ing_data.get('name_vi', '').lower() == name:
                    normalized.append({
                        'ingredient_id': ing_id,
                        'name_vi': ing_data['name_vi'],
                        'quantity': item.get('quantity', ''),
                        'unit': item.get('unit', '')
                    })
                    break
        
        return normalized
    
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
        for it in dish.get('ingredients', []):
            cat = it.get('category')
            if cat:
                cats.add(cat)
        if cats:
            return cats

        return {
            'seasonings','aromatics','sweeteners','fresh_meat','eggs','beverages',
            'vegetables','herbs'
        }
