from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from app.utils.string_utils import norm_text
from app.services.ontology_service import OntologyService


class ConflictDetectionService:

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.data_path = data_path or Path("app/data/conflict/ingredient_conflict_restructured.json")
        self._conflicts: List[Dict[str, object]] = self._load_conflicts()
        self.ontology = OntologyService()
        # Build fast lookup indices to speed up matching
        self._index_by_id: Dict[str, List[Dict[str, object]]] = {}
        self._index_by_name: Dict[str, List[Dict[str, object]]] = {}
        self._build_indices()


    def check_conflicts(
        self, 
        dish_name: str, 
        ingredients: Iterable[Dict[str, str]] | Iterable[str]
    ) -> List[Dict[str, object]]:
        """
        New logic theo yêu cầu:
        1. Tập A = ingredients từ món ăn + extra ingredients
        2. Map tập A với conflict KB để lấy ingredient_id và dish_id
        3a. Check dish × ingredients trong tập A
        3b. Check ingredient × ingredient cross-pair trong tập A
        """
        
        # Normalize inputs
        dish_norm = norm_text(dish_name)
        
        # Parse ingredients into set A
        set_a_ids: Set[str] = set()
        set_a_names: Dict[str, str] = {}  # normalized -> original
        set_a_items: List[Dict[str, str]] = []  # for tracking

        for ing in ingredients:
            if isinstance(ing, dict):
                ing_id = ing.get('ingredient_id')
                ing_name = ing.get('name_vi') or ing.get('name', '')
                
                if ing_id:
                    set_a_ids.add(ing_id)
                if ing_name:
                    set_a_names[norm_text(ing_name)] = ing_name
                    set_a_items.append({
                        'ingredient_id': ing_id,
                        'name': ing_name,
                        'name_norm': norm_text(ing_name)
                    })
            
            elif isinstance(ing, str) and ing:
                set_a_names[norm_text(ing)] = ing
                set_a_items.append({
                    'ingredient_id': None,
                    'name': ing,
                    'name_norm': norm_text(ing)
                })
        
        # Step 2: Map ingredients to conflict KB
        mapped_items = self._map_ingredients_to_conflicts(set_a_items)
        
        results: List[Dict[str, object]] = []
        
        # Step 3a: Check dish × ingredients conflicts
        dish_conflicts = self._check_dish_ingredient_conflicts(
            dish_name, 
            dish_norm, 
            mapped_items
        )
        results.extend(dish_conflicts)
        
        # Step 3b: Check ingredient × ingredient cross-pair conflicts
        ingredient_conflicts = self._check_ingredient_pair_conflicts(mapped_items)
        results.extend(ingredient_conflicts)
        
        return results

    def _build_indices(self) -> None:
        """Build lookup indices for fast conflict entry retrieval.
        - _index_by_id: ingredient_id -> [entries]
        - _index_by_name: normalized name -> [entries]
        """
        try:
            for entry in self._conflicts:
                for pair_item in entry.get('item_pairs', []) or []:
                    pid = pair_item.get('ingredient_id')
                    pname = norm_text(pair_item.get('name', '') or '')
                    if pid:
                        self._index_by_id.setdefault(pid, []).append(entry)
                    if pname:
                        self._index_by_name.setdefault(pname, []).append(entry)

                for detail_item in entry.get('conflict_details', []) or []:
                    did = detail_item.get('ingredient_id')
                    dname = norm_text(detail_item.get('name', '') or '')
                    if did:
                        self._index_by_id.setdefault(did, []).append(entry)
                    if dname:
                        self._index_by_name.setdefault(dname, []).append(entry)
        except Exception:
            # If indexing fails, leave indices empty and fallback to full-scan behavior
            self._index_by_id = {}
            self._index_by_name = {}
    
    def _map_ingredients_to_conflicts(
        self, 
        items: List[Dict[str, str]]
    ) -> List[Dict[str, object]]:
        """
        Map từng item trong tập A với conflict KB
        Return: [{ingredient_id, name, conflict_entries: []}]
        """
        mapped = []

        for item in items:
            item_id = item.get('ingredient_id')
            item_name = item.get('name', '')
            item_norm = item.get('name_norm', '')

            # Use indices to find candidate entries quickly
            related_entries = []
            seen_entries = set()

            # Lookup by id
            if item_id and item_id in self._index_by_id:
                for e in self._index_by_id[item_id]:
                    eid = id(e)
                    if eid not in seen_entries:
                        related_entries.append(e)
                        seen_entries.add(eid)

            # Lookup by exact or token-match name keys (fast path)
            if item_norm and item_norm in self._index_by_name:
                for e in self._index_by_name[item_norm]:
                    eid = id(e)
                    if eid not in seen_entries:
                        related_entries.append(e)
                        seen_entries.add(eid)

            # Fallback: try substring / token based on indexed keys (cheap; index keys << entries)
            if item_norm:
                for key, entries in self._index_by_name.items():
                    if key == item_norm or item_norm in key or key in item_norm:
                        for e in entries:
                            eid = id(e)
                            if eid not in seen_entries:
                                related_entries.append(e)
                                seen_entries.add(eid)

            mapped.append({
                'ingredient_id': item_id,
                'name': item_name,
                'name_norm': item_norm,
                'conflict_entries': related_entries
            })

        return mapped
    
    def _check_dish_ingredient_conflicts(
        self,
        dish_name: str,
        dish_norm: str,
        mapped_items: List[Dict[str, object]]
    ) -> List[Dict[str, object]]:
        """
        Kiểm tra dish có conflict với bất kỳ ingredient nào trong tập A không
        """
        results = []
        
        # Find candidate entries that mention this dish using the name index
        candidate_entries = []
        seen = set()
        for key, entries in self._index_by_name.items():
            if dish_norm == key or dish_norm in key or key in dish_norm:
                for e in entries:
                    eid = id(e)
                    if eid not in seen:
                        candidate_entries.append(e)
                        seen.add(eid)

        # Check only candidate entries
        for entry in candidate_entries:
            dish_found = False
            dish_item_name = None
            dish_item_id = None
            conflicting_ingredients = []
            
            # Check if dish is in item_pairs
            for pair_item in entry.get('item_pairs', []):
                pair_name = pair_item.get('name', '')
                pair_norm = norm_text(pair_name)
                
                if self._names_match(dish_norm, pair_norm):
                    dish_found = True
                    dish_item_name = pair_name
                    dish_item_id = pair_item.get('ingredient_id')
                    break
            
            if not dish_found:
                continue
            
            # If dish found, check if any ingredient from set A is in this entry
            for mapped in mapped_items:
                item_id = mapped.get('ingredient_id')
                item_norm = mapped.get('name_norm')
                item_name = mapped.get('name')
                
                # Check in conflict_details (items that conflict with dish)
                for detail_item in entry.get('conflict_details', []):
                    detail_id = detail_item.get('ingredient_id')
                    detail_name = norm_text(detail_item.get('name', ''))
                    
                    if item_id and detail_id == item_id:
                        conflicting_ingredients.append(item_name)
                        break
                    elif self._names_match(item_norm, detail_name):
                        conflicting_ingredients.append(item_name)
                        break

            # Remove duplicates while preserving order
            seen_ci = set()
            unique_conflicting = []
            for n in conflicting_ingredients:
                if n and n not in seen_ci:
                    seen_ci.add(n)
                    unique_conflicting.append(n)

            # If found conflicts, create warning
            if unique_conflicting:
                # Get replacement suggestions for conflicting ingredients
                conflicted_ids = set()
                for detail_item in entry.get('conflict_details', []):
                    detail_id = detail_item.get('ingredient_id')
                    if detail_id:
                        conflicted_ids.add(detail_id)
                
                replacements = []
                for detail_item in entry.get('conflict_details', []):
                    detail_id = detail_item.get('ingredient_id')
                    if detail_id:
                        suggestions = self.ontology.get_replacement_suggestions(
                            detail_id,
                            max_suggestions=3,
                            exclude_ids=conflicted_ids
                        )
                        if suggestions:
                            replacements.extend(suggestions[:2])  # Top 2 per ingredient

                # Remove duplicates
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
                    "advice": entry.get("advice", ""),
                    "conflicting_items": unique_conflicting,  # ONLY ingredients, NOT dish
                    "conflicting_item_ids": [
                        # include ids when available by looking up conflict_details
                        d.get('ingredient_id') for d in entry.get('conflict_details', [])
                        if d.get('ingredient_id')
                    ],
                    "dish_name": dish_item_name,  # Store dish separately
                    "dish_id": dish_item_id,
                    "sources": entry.get("sources", []),
                    "replacement_suggestions": unique_replacements[:3],
                    "conflict_type": "dish_ingredient"
                })
        
        return results
    
    def _check_ingredient_pair_conflicts(
        self,
        mapped_items: List[Dict[str, object]]
    ) -> List[Dict[str, object]]:
        """
        Kiểm tra chéo các cặp ingredient trong tập A
        """
        results = []
        checked_pairs = set()
        
        # Build candidate entries from mapped_items to avoid scanning all conflicts
        candidate_entries_ids = set()
        for mapped in mapped_items:
            for e in mapped.get('conflict_entries', []):
                candidate_entries_ids.add(id(e))

        id_to_entry = {id(e): e for e in self._conflicts}

        for eid in candidate_entries_ids:
            entry = id_to_entry.get(eid)
            if not entry:
                continue
            item_pairs = entry.get('item_pairs', [])
            conflict_details = entry.get('conflict_details', [])
            
            # Find which items from set A appear in this entry
            matched_items = []
            
            for mapped in mapped_items:
                item_id = mapped.get('ingredient_id')
                item_norm = mapped.get('name_norm')
                item_name = mapped.get('name')
                
                # Check in item_pairs
                for pair_item in item_pairs:
                    pair_id = pair_item.get('ingredient_id')
                    pair_name = norm_text(pair_item.get('name', ''))
                    
                    if item_id and pair_id == item_id:
                        matched_items.append({
                            'id': item_id,
                            'name': item_name,
                            'from': 'item_pairs'
                        })
                        break
                    elif self._names_match(item_norm, pair_name):
                        matched_items.append({
                            'id': item_id,
                            'name': item_name,
                            'from': 'item_pairs'
                        })
                        break
                else:
                    # Check in conflict_details
                    for detail_item in conflict_details:
                        detail_id = detail_item.get('ingredient_id')
                        detail_name = norm_text(detail_item.get('name', ''))
                        
                        if item_id and detail_id == item_id:
                            matched_items.append({
                                'id': item_id,
                                'name': item_name,
                                'from': 'conflict_details'
                            })
                            break
                        elif self._names_match(item_norm, detail_name):
                            matched_items.append({
                                'id': item_id,
                                'name': item_name,
                                'from': 'conflict_details'
                            })
                            break
            
            # Remove duplicate matched items by name
            unique_seen = {}
            deduped = []
            for m in matched_items:
                key = (m.get('id') or '') + '|' + (m.get('name') or '')
                if key not in unique_seen:
                    unique_seen[key] = True
                    deduped.append(m)

            # Need at least 2 unique items to form a conflict pair
            if len(deduped) < 2:
                continue
            # Check if we have items from both item_pairs and conflict_details
            has_pair_item = any(m['from'] == 'item_pairs' for m in deduped)
            has_conflict_item = any(m['from'] == 'conflict_details' for m in deduped)

            if not (has_pair_item and has_conflict_item):
                continue
            
            # Create unique key for this pair to avoid duplicates
            item_names = sorted([m['name'] for m in deduped])
            pair_key = f"{entry.get('id')}:{','.join(item_names)}"
            
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            
            # Get replacement suggestions
            # Priority: replace item with lower score (nếu có score) or from conflict_details
            conflicted_ids = set()
            items_to_replace = []
            
            for m in deduped:
                if m.get('id'):
                    conflicted_ids.add(m['id'])
                if m['from'] == 'conflict_details':
                    items_to_replace.append(m)
            
            # If no specific items to replace, use all matched items
            if not items_to_replace:
                items_to_replace = matched_items
            
            replacements = []
            for item in items_to_replace:
                if item.get('id'):
                    suggestions = self.ontology.get_replacement_suggestions(
                        item['id'],
                        max_suggestions=3,
                        exclude_ids=conflicted_ids
                    )
                    if suggestions:
                        # Get highest score suggestion for ingredient conflicts
                        replacements.extend(suggestions[:2])
            
            # Remove duplicates
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
                "advice": entry.get("advice", ""),
                "conflicting_items": item_names,
                "conflicting_item_ids": [m.get('id') for m in deduped if m.get('id')],
                "sources": entry.get("sources", []),
                "replacement_suggestions": unique_replacements[:3],
                "conflict_type": "ingredient_ingredient"
            })
        
        return results
    
    
    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two normalized names match (exact or partial)"""
        if not name1 or not name2:
            return False
        
        # Exact match
        if name1 == name2:
            return True
        
        # One contains the other (for compound names)
        if name1 in name2 or name2 in name1:
            return True
        
        # Token-based matching for multi-word names
        tokens1 = set(name1.split())
        tokens2 = set(name2.split())
        
        # If they share significant tokens
        if len(tokens1) > 1 and len(tokens2) > 1:
            common = tokens1 & tokens2
            if len(common) >= min(len(tokens1), len(tokens2)) * 0.7:
                return True
        
        return False


    def build_explanations(self, dish_name: str, conflicts: Iterable[Dict[str, object]]) -> List[str]:
        explanations: List[str] = []
        for conflict in conflicts:
            conflicting_items = ", ".join(conflict.get("conflicting_items", []))
            reason = conflict.get("message", "")
            advice = conflict.get("advice", "")
            conflict_type = conflict.get("conflict_type", "")
            
            if conflict_type == "dish_ingredient":
                # For dish-ingredient conflicts, use the stored dish name
                conflict_dish = conflict.get("dish_name", dish_name)
                if conflicting_items:
                    message = (
                        f"{conflict_dish} không nên kết hợp với {conflicting_items} vì {reason}."
                    )
                else:
                    message = f"{conflict_dish} có cảnh báo: {reason}."
            else:
                # For ingredient-ingredient conflicts
                if conflicting_items:
                    message = (
                        f"Không nên kết hợp {conflicting_items} vì {reason}."
                    )
                else:
                    message = f"Có cảnh báo: {reason}."
            
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