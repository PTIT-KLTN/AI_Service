import json
import math
from collections import defaultdict
from pathlib import Path

class ValidationService:
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        path = Path("app/data/cooccurrence")
        self.matrix = defaultdict(lambda: defaultdict(int))
        self.frequency = defaultdict(int)
        self.total = 0
        
        try:
            with open(path / "matrix.json", 'r') as f:
                self.matrix = defaultdict(lambda: defaultdict(int), json.load(f))
            with open(path / "frequency.json", 'r') as f:
                self.frequency = defaultdict(int, json.load(f))
            with open(path / "metadata.json", 'r') as f:
                self.total = json.load(f)['total_dishes']
        except:
            pass
        
        self._initialized = True
    
    def check_missing(self, required: list, user: list = None) -> dict:
        required_ids = {ing['id']: ing for ing in required}
        user_ids = {ing['id']: ing for ing in (user or [])}
        
        missing = []
        available = []
        
        for ing_id, ing in required_ids.items():
            if ing_id in user_ids:
                available.append({**ing, 'user_quantity': user_ids[ing_id].get('quantity'), 
                                'user_unit': user_ids[ing_id].get('unit')})
            else:
                missing.append(ing)
        
        suggestions = self._suggest(list(required_ids.keys()))
        
        return {
            'required': required,
            'missing': missing,
            'available': available,
            'suggestions': suggestions
        }
    
    def _suggest(self, ing_ids: list) -> list:
        if not self.total:
            return []
        
        candidates = defaultdict(float)
        for ing_id in ing_ids:
            for co_id, count in self.matrix[ing_id].items():
                if co_id not in ing_ids and count >= 3:
                    candidates[co_id] += self._pmi(ing_id, co_id)
        
        top = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:3]
        return [{'id': i, 'score': round(s, 2)} for i, s in top]
    
    def _pmi(self, id1: str, id2: str) -> float:
        if id1 not in self.frequency or id2 not in self.frequency:
            return 0.0
        
        co = self.matrix[id1].get(id2, 0)
        p_xy = co / self.total if self.total else 0
        p_x = self.frequency[id1] / self.total
        p_y = self.frequency[id2] / self.total
        
        if p_xy > 0 and p_x > 0 and p_y > 0:
            return math.log(p_xy / (p_x * p_y))
        return 0.0