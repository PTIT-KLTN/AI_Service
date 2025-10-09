from dotenv import load_dotenv
from app.services.invoke_model_service import BedrockModelService
from app.services.bedrock_kb_service import BedrockKBService
from app.services.validation_service import ValidationService
from app.services.ontology_service import OntologyService
from app.services.unit_converter_service import UnitConverterService 

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
        
        if not extracted.get('dish_name'):
            return {'error': 'Không tìm thấy tên món ăn'}
        
        dish_name = extracted['dish_name']
        extra_ingredients = extracted.get('ingredients', [])
        
        # Get recipe
        recipe = self._get_recipe(dish_name)
        if not recipe.get('ingredients'):
            return {'error': f'Không tìm thấy công thức cho "{dish_name}"'}
        
        # Merge: công thức + nguyên liệu thêm
        all_ingredients = recipe['ingredients'] + self._normalize_extra(extra_ingredients)
        
        # Convert units
        cart_items = self.converter.normalize_ingredients(all_ingredients)
        
        # Add category
        for item in cart_items:
            ing_info = self.ontology.get_ingredient(item['ingredient_id'])
            item['category'] = ing_info.get('category', 'other') if ing_info else 'other'
        
        # Get suggestions
        suggestions = self._get_suggestions([item['ingredient_id'] for item in all_ingredients])
        
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
        recipe = self.kb_service.get_dish_recipe(dish_name)
        if recipe.get('ingredients'):
            return recipe
        
        local = self.ontology.get_dish_by_name(dish_name)
        return local if local else {'ingredients': []}
    
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
    
    def _get_suggestions(self, ingredient_ids: list) -> list:
        """
        Get ingredient suggestions based on co-occurrence
        """
        validation = self.validator.check_missing(
            [{'id': id} for id in ingredient_ids], 
            []
        )
        
        suggestions = []
        for sug in validation.get('suggestions', [])[:3]:
            ing = self.ontology.get_ingredient(sug['id'])
            if ing:
                # Convert unit cho suggestion
                suggestion_item = {
                    'ingredient_id': sug['id'],
                    'name_vi': ing.get('name_vi', ''),
                    'quantity': '',
                    'unit': '',
                    'score': sug['score'],
                    'reason': 'Thường đi kèm với món này'
                }
                
                # Normalize để có converted_unit
                converted = self.converter.normalize_ingredients([suggestion_item])
                if converted:
                    suggestions.append(converted[0])
        
        return suggestions