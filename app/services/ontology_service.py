import json
from typing import Dict, List, Optional
from pathlib import Path

class OntologyService:
    """Knowledge base lookup service"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Singleton - load knowledge base 1 lần"""
        if self._initialized:
            return
            
        kb_path = Path("app/data/knowledge_base")
        
        with open(kb_path / "ingredient_knowledge_base.json", 'r', encoding='utf-8') as f:
            self.ingredients = {ing['id']: ing for ing in json.load(f)}
        
        with open(kb_path / "dish_knowledge_base.json", 'r', encoding='utf-8') as f:
            self.dishes = {dish['id']: dish for dish in json.load(f)}
        
        print(f"Loaded KB: {len(self.ingredients)} ingredients, {len(self.dishes)} dishes")
        self._initialized = True
    
    def get_ingredient(self, ingredient_id: str) -> Optional[Dict]:
        """Lấy thông tin nguyên liệu"""
        return self.ingredients.get(ingredient_id)
    
    def get_dish(self, dish_id: str) -> Optional[Dict]:
        """Lấy thông tin món ăn"""
        return self.dishes.get(dish_id)
    
    def search_dish_by_ingredients(self, ingredient_ids: List[str], min_match: int = 2) -> List[Dict]:
        """
        Tìm món ăn dựa trên nguyên liệu
        
        Args:
            ingredient_ids: List ID nguyên liệu
            min_match: Số nguyên liệu tối thiểu phải khớp
            
        Returns:
            List món ăn khớp, sorted by match ratio
        """
        matches = []
        
        for dish_id, dish in self.dishes.items():
            dish_ing_ids = [ing['ingredient_id'] for ing in dish.get('ingredients', [])]
            
            # Count matches
            matched = set(ingredient_ids) & set(dish_ing_ids)
            match_count = len(matched)
            
            if match_count >= min_match:
                matches.append({
                    'dish_id': dish_id,
                    'dish_name': dish.get('name_vi', 'Unknown'),
                    'match_count': match_count,
                    'total_ingredients': len(dish_ing_ids),
                    'match_ratio': match_count / len(dish_ing_ids) if dish_ing_ids else 0,
                    'matched_ingredients': list(matched)
                })
        
        # Sort by match ratio
        matches.sort(key=lambda x: (x['match_ratio'], x['match_count']), reverse=True)
        return matches
    
    def enrich_ingredients(self, ingredient_ids: List[str]) -> List[Dict]:
        """Thêm thông tin chi tiết cho nguyên liệu"""
        enriched = []
        for ing_id in ingredient_ids:
            ing = self.get_ingredient(ing_id)
            if ing:
                enriched.append({
                    'id': ing_id,
                    'name_vi': ing.get('name_vi', 'Unknown'),
                    'name_en': ing.get('name_en', 'Unknown'),
                    'category': ing.get('category', 'unknown')
                })
        return enriched