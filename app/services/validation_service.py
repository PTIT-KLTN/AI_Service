import json
import math
from collections import defaultdict
from typing import Dict, List
from pathlib import Path

class ValidationService:
    """Co-occurrence validation service"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Singleton - chỉ load ma trận 1 lần"""
        if self._initialized:
            return
            
        self.matrix_path = Path("app/data/cooccurrence")
        self.cooccurrence_matrix = defaultdict(lambda: defaultdict(int))
        self.ingredient_frequency = defaultdict(int)
        self.total_dishes = 0
        
        self._load_matrix()
        self._initialized = True
    
    def _load_matrix(self):
        """Load ma trận từ file"""
        try:
            with open(self.matrix_path / "matrix.json", 'r') as f:
                data = json.load(f)
                self.cooccurrence_matrix = defaultdict(lambda: defaultdict(int), data)
            
            with open(self.matrix_path / "frequency.json", 'r') as f:
                self.ingredient_frequency = defaultdict(int, json.load(f))
            
            with open(self.matrix_path / "metadata.json", 'r') as f:
                meta = json.load(f)
                self.total_dishes = meta['total_dishes']
            
            print(f"✅ Loaded matrix: {len(self.ingredient_frequency)} ingredients")
        except FileNotFoundError:
            print("⚠️  Matrix not found. Run build_cooccurrence.py first!")
    
    def validate(self, ingredients: List[Dict], threshold_unusual: float = -2.0, 
                 threshold_common: float = 1.0) -> Dict:
        """
        Validate danh sách nguyên liệu
        
        Args:
            ingredients: [{"id": "ingre001", "confidence": 0.85}, ...]
            
        Returns:
            {"adjusted_ingredients": [...], "warnings": [...], "suggestions": [...]}
        """
        if self.total_dishes == 0:
            return {"adjusted_ingredients": ingredients, "warnings": [], "suggestions": []}
        
        ing_ids = [ing['id'] for ing in ingredients]
        adjusted = []
        warnings = []
        
        for ing in ingredients:
            ing_id = ing['id']
            confidence = ing.get('confidence', 0.0)
            
            # Tính PMI trung bình
            pmi_scores = [self._get_pmi(ing_id, other) for other in ing_ids if other != ing_id]
            avg_pmi = sum(pmi_scores) / len(pmi_scores) if pmi_scores else 0.0
            
            # Adjust confidence
            adjustment = 0.0
            status = 'normal'
            
            if avg_pmi < threshold_unusual:
                adjustment = -0.2
                status = 'unusual'
                warnings.append(f"⚠️ {ing.get('name', ing_id)} không phổ biến (PMI: {avg_pmi:.2f})")
            elif avg_pmi > threshold_common:
                adjustment = 0.15
                status = 'common'
            
            adjusted.append({
                **ing,
                'confidence': min(1.0, max(0.0, confidence + adjustment)),
                'original_confidence': confidence,
                'pmi_score': round(avg_pmi, 3),
                'status': status
            })
        
        suggestions = self._suggest_missing(ing_ids, top_n=3)
        
        return {
            'adjusted_ingredients': adjusted,
            'warnings': warnings,
            'suggestions': suggestions
        }
    
    def _get_pmi(self, ing_id_1: str, ing_id_2: str) -> float:
        """Tính PMI score"""
        if ing_id_1 not in self.ingredient_frequency or ing_id_2 not in self.ingredient_frequency:
            return 0.0
        
        cooccur = self.cooccurrence_matrix[ing_id_1].get(ing_id_2, 0)
        p_xy = cooccur / self.total_dishes if self.total_dishes > 0 else 0
        p_x = self.ingredient_frequency[ing_id_1] / self.total_dishes
        p_y = self.ingredient_frequency[ing_id_2] / self.total_dishes
        
        if p_xy > 0 and p_x > 0 and p_y > 0:
            return math.log(p_xy / (p_x * p_y))
        return 0.0
    
    def _suggest_missing(self, ingredient_ids: List[str], top_n: int = 3) -> List[Dict]:
        """Gợi ý nguyên liệu thiếu"""
        candidates = defaultdict(float)
        
        for ing_id in ingredient_ids:
            for co_id, count in self.cooccurrence_matrix[ing_id].items():
                if co_id not in ingredient_ids and count >= 3:
                    candidates[co_id] += self._get_pmi(ing_id, co_id)
        
        top = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [{'id': ing_id, 'score': round(score, 3)} for ing_id, score in top]