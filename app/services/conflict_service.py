from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from app.utils.string_utils import norm_text
from app.services.ontology_service import OntologyService


class ConflictDetectionService:

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.data_path = data_path or Path("app/data/conflict/ingredient_conflict.json")
        self._conflicts: List[Dict[str, object]] = self._load_conflicts()
        self.ontology = OntologyService()
        self._index_by_name: Dict[str, List[Dict[str, object]]] = {}
        self._build_indices()


    def check_conflicts(
        self, 
        dish_name: str, 
        ingredients: Iterable[Dict[str, str]] | Iterable[str]
    ) -> List[Dict[str, object]]:
        
        dish_norm = norm_text(dish_name)
        user_items: List[Dict[str, str]] = []
        user_names_norm = set()
        
        for ing in ingredients:
            if isinstance(ing, dict):
                ing_id = ing.get('ingredient_id')
                ing_name = ing.get('name_vi') or ing.get('name', '')
                
                if ing_name:
                    user_items.append({
                        'ingredient_id': ing_id,
                        'name': ing_name,
                        'name_norm': norm_text(ing_name)
                    })
                    user_names_norm.add(norm_text(ing_name))
            
            elif isinstance(ing, str) and ing:
                user_items.append({
                    'ingredient_id': None,
                    'name': ing,
                    'name_norm': norm_text(ing)
                })
                user_names_norm.add(norm_text(ing))
        
        results: List[Dict[str, object]] = []
        
        for entry in self._conflicts:
            main_ingre = entry.get('ingre', [])
            conflict_items = entry.get('conflicts', [])
            
            matched_main = []
            matched_main_users = []
            for item_name in main_ingre:
                item_norm = norm_text(item_name)
                for user_item in user_items:
                    if self._names_match(user_item['name_norm'], item_norm):
                        matched_main.append(user_item['name'])
                        matched_main_users.append(user_item['name'])
                        break
            
            matched_conflicts = []
            matched_conflict_users = []
            for conflict_name in conflict_items:
                conflict_norm = norm_text(conflict_name)
                for user_item in user_items:
                    if self._names_match(user_item['name_norm'], conflict_norm):
                        matched_conflicts.append(user_item['name'])
                        matched_conflict_users.append(user_item['name'])
                        break
            
            if matched_main and matched_conflicts:
                overlap = set(matched_main_users) & set(matched_conflict_users)
                if overlap:
                    continue
                
                conflicted_ids = set()
                replacement_candidates = []
                
                for user_item in user_items:
                    if user_item['name'] in matched_conflicts and user_item.get('ingredient_id'):
                        conflicted_ids.add(user_item['ingredient_id'])
                        replacement_candidates.append(user_item['ingredient_id'])
                
                replacements = []
                for ing_id in replacement_candidates:
                    suggestions = self.ontology.get_replacement_suggestions(
                        ing_id,
                        max_suggestions=3,
                        exclude_ids=conflicted_ids
                    )
                    if suggestions:
                        replacements.extend(suggestions[:2])
                
                seen_ids = set()
                unique_replacements = []
                for repl in replacements:
                    if repl['ingredient_id'] not in seen_ids:
                        seen_ids.add(repl['ingredient_id'])
                        unique_replacements.append(repl)
                
                results.append({
                    "id": entry.get("id"),
                    "severity": entry.get("severity", "medium"),
                    "message": entry.get("reason", ""),
                    "conflicting_item_1": matched_main,
                    "conflicting_item_2": matched_conflicts,
                    "sources": entry.get("sources", []),
                    "replacement_suggestions": unique_replacements[:3],
                    "conflict_type": "ingredient_ingredient"
                })
        
        return results

    def _build_indices(self) -> None:
        try:
            for entry in self._conflicts:
                for ingre_name in entry.get('ingre', []):
                    name_norm = norm_text(ingre_name)
                    if name_norm:
                        self._index_by_name.setdefault(name_norm, []).append(entry)
                
                for conflict_name in entry.get('conflicts', []):
                    name_norm = norm_text(conflict_name)
                    if name_norm:
                        self._index_by_name.setdefault(name_norm, []).append(entry)
        except Exception:
            self._index_by_name = {}
    
    def _names_match(self, name1: str, name2: str) -> bool:
        if not name1 or not name2:
            return False
        
        # Exact match
        if name1 == name2:
            return True
        
        # Split into tokens
        tokens1 = name1.split()
        tokens2 = name2.split()
        
        # Determine shorter and longer
        if len(tokens1) <= len(tokens2):
            shorter_tokens = tokens1
            longer_tokens = tokens2
        else:
            shorter_tokens = tokens2
            longer_tokens = tokens1
        
        shorter_len = len(shorter_tokens)
        longer_len = len(longer_tokens)
        
        if shorter_len == 1:
            return False
        
        if shorter_len < longer_len:
            if longer_tokens[:shorter_len] == shorter_tokens:
                return True
        
        return False

    def build_explanations(self, dish_name: str, conflicts: Iterable[Dict[str, object]]) -> List[str]:
        explanations: List[str] = []
        
        for conflict in conflicts:
            reason = conflict.get("message", "")
            advice = conflict.get("advice", "")
            
            if reason:
                message = reason
                if advice:
                    message += f" {advice}"
                explanations.append(message.strip())
        
        return explanations


    def _load_conflicts(self) -> List[Dict[str, object]]:
        if not self.data_path.exists():
            return []
        try:
            with self.data_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return []
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
            return []


__all__ = ["ConflictDetectionService"]