from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.utils.string_utils import norm_text


class ConflictDetectionService:
    """Load curated ingredient conflicts and provide lookup utilities."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.data_path = data_path or Path("app/data/conflicts/ingredient_conflicts.json")
        self._conflicts: List[Dict[str, object]] = self._load_conflicts()


    def check_conflicts(self, dish_name: str, ingredient_names: Iterable[str]) -> List[Dict[str, object]]:
        dish_norm = norm_text(dish_name)
        normalized_ingredients = {
            norm_text(name): name for name in ingredient_names if name
        }
        results: List[Dict[str, object]] = []

        for entry in self._conflicts:
            dishes = [norm_text(d) for d in entry.get("dishes", []) if d]
            if dishes and not any(d in dish_norm or dish_norm in d for d in dishes):
                continue

            hits: List[str] = []
            for candidate in entry.get("conflicts", []):
                cand_norm = norm_text(candidate)
                if not cand_norm:
                    continue
                tokens = [token for token in cand_norm.split() if token]
                if not tokens:
                    continue
                if len(tokens) == 1 and len(tokens[0]) <= 2:
                    pattern = re.compile(rf"^{re.escape(tokens[0])}$")
                else:
                    pattern = re.compile(r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b")
                for ing_norm, original in normalized_ingredients.items():
                    if not ing_norm:
                        continue
                    if pattern.search(ing_norm):
                        hits.append(original)

            if not hits:
                continue

            unique_hits = sorted(set(hits), key=lambda x: x.lower())
            results.append(
                {
                    "id": entry.get("id"),
                    "severity": entry.get("severity", "medium"),
                    "message": entry.get("reason", ""),
                    "advice": entry.get("advice", ""),
                    "conflicting_items": unique_hits,
                }
            )

        return results


    def build_explanations(self, dish_name: str, conflicts: Iterable[Dict[str, object]]) -> List[str]:
        explanations: List[str] = []
        for conflict in conflicts:
            conflicting_items = ", ".join(conflict.get("conflicting_items", []))
            reason = conflict.get("message", "")
            advice = conflict.get("advice", "")
            if conflicting_items:
                message = (
                    f"{dish_name} không nên kết hợp với {conflicting_items} vì {reason}."
                )
            else:
                message = f"{dish_name} có cảnh báo: {reason}."
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