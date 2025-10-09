import json
from pathlib import Path

class OntologyService:
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        path = Path("app/data/knowledge_base")
        
        with open(path / "ingredient_knowledge_base.json", 'r', encoding='utf-8') as f:
            self.ingredients = {ing['id']: ing for ing in json.load(f)}
        
        with open(path / "dish_knowledge_base.json", 'r', encoding='utf-8') as f:
            self.dishes = {d['id']: d for d in json.load(f)}
        
        self._initialized = True
    
    def get_ingredient(self, ing_id: str) -> dict:
        return self.ingredients.get(ing_id)
    
    def get_dish(self, dish_id: str) -> dict:
        return self.dishes.get(dish_id)
    
    def search_similar_dishes(self, ing_ids: list, min_match: int = 2) -> list:
        matches = []
        
        for dish_id, dish in self.dishes.items():
            dish_ings = [i['ingredient_id'] for i in dish.get('ingredients', [])]
            matched = set(ing_ids) & set(dish_ings)
            
            if len(matched) >= min_match:
                matches.append({
                    'dish_id': dish_id,
                    'dish_name': dish.get('name_vi', 'Unknown'),
                    'match_count': len(matched),
                    'match_ratio': len(matched) / len(dish_ings) if dish_ings else 0
                })
        
        matches.sort(key=lambda x: (x['match_ratio'], x['match_count']), reverse=True)
        return matches
    
    def get_dish_by_name(self, name: str) -> dict:
        name_lower = name.lower()
        for dish_id, dish in self.dishes.items():
            if dish.get('name_vi', '').lower() == name_lower:
                return {
                    'dish_name': dish.get('name_vi'),
                    'ingredients': dish.get('ingredients', []),  # Dùng trực tiếp, đã có quantity/unit
                    'instructions': dish.get('instructions', '')
                }
        return None