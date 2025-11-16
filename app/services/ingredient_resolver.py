"""
Ingredient Resolver Service.
Handles fuzzy matching and ingredient ID resolution.
"""
from typing import Optional

from app.utils.text_match import fuzzy_score, tokenize


class IngredientResolver:
    """Resolves ingredient names to IDs using fuzzy matching."""
    
    # Thresholds for matching
    NAME_VI_THRESHOLD = 0.7
    SYNONYMS_THRESHOLD = 0.65
    
    def __init__(self, ontology_service):
        self.ontology = ontology_service
    
    def resolve_name_to_id(self, name: str) -> Optional[str]:
        if not name:
            return None
        
        q_tokens = set(tokenize(name))
        ing_dict = getattr(self.ontology, 'ingredients', {}) or {}
        
        # Stage A: Match against name_vi
        match_id = self._match_by_name_vi(name, q_tokens, ing_dict)
        if match_id:
            return match_id
        
        # Stage B: Match against synonyms
        match_id = self._match_by_synonyms(name, q_tokens, ing_dict)
        return match_id
    
    def _match_by_name_vi(
        self,
        name: str,
        q_tokens: set,
        ing_dict: dict
    ) -> Optional[str]:
        """Match ingredient name against name_vi field."""
        best_id = None
        best_score = -1.0
        best_extras = 10**9
        best_len = 10**9
        
        for ing_id, ing in ing_dict.items():
            cand = ing.get('name_vi') or ''
            if not cand:
                continue
            
            sc = fuzzy_score(name, cand)
            extras = len(set(tokenize(cand)) - q_tokens)
            clen = len(cand)
            
            if self._is_better_match(sc, extras, clen, best_score, best_extras, best_len):
                best_id, best_score, best_extras, best_len = ing_id, sc, extras, clen
        
        if best_score >= self.NAME_VI_THRESHOLD:
            return best_id
        
        return None
    
    def _match_by_synonyms(
        self,
        name: str,
        q_tokens: set,
        ing_dict: dict
    ) -> Optional[str]:
        """Match ingredient name against synonyms field."""
        best_id = None
        best_score = -1.0
        best_extras = 10**9
        best_len = 10**9
        
        for ing_id, ing in ing_dict.items():
            syns = [s for s in ing.get('synonyms', []) if s]
            if not syns:
                continue
            
            local_best_sc, local_best_extras, local_best_len = self._find_best_synonym(
                name, q_tokens, syns
            )
            
            if self._is_better_match(
                local_best_sc, local_best_extras, local_best_len,
                best_score, best_extras, best_len
            ):
                best_id = ing_id
                best_score = local_best_sc
                best_extras = local_best_extras
                best_len = local_best_len
        
        if best_score >= self.SYNONYMS_THRESHOLD:
            return best_id
        
        return None
    
    def _find_best_synonym(self, name: str, q_tokens: set, synonyms: list) -> tuple:
        """Find best matching synonym from a list."""
        local_best_sc = -1.0
        local_best_extras = 10**9
        local_best_len = 10**9
        
        for s in synonyms:
            sc = fuzzy_score(name, s)
            extras = len(set(tokenize(s)) - q_tokens)
            slen = len(s)
            
            if self._is_better_match(sc, extras, slen, local_best_sc, local_best_extras, local_best_len):
                local_best_sc, local_best_extras, local_best_len = sc, extras, slen
        
        return local_best_sc, local_best_extras, local_best_len
    
    @staticmethod
    def _is_better_match(
        score: float, extras: int, length: int,
        best_score: float, best_extras: int, best_len: int
    ) -> bool:
        """
        Check if current match is better than best match.
        
        Priority: score > fewer extra tokens > shorter length
        """
        if score > best_score:
            return True
        if score == best_score:
            if extras < best_extras:
                return True
            if extras == best_extras and length < best_len:
                return True
        return False
