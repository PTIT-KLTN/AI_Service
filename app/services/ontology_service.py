import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

class OntologyService:
    _instance = None

    #: Role definitions dựa trên category + importance
    _ROLE_DEFINITIONS: Dict[str, Dict[str, object]] = {
        "core_protein": {
            "categories": {
                "fresh_meat",
                "seafood_&_fish_balls",
                "cold_cuts:_sausages_&_ham",
            },
            "min_importance": 2,
        },
        "core_produce": {
            "categories": {"vegetables", "fresh_fruits"},
            "min_importance": 2,
        },
        "core_staple": {
            "categories": {"grains_staples", "cereals_grains"},
            "min_importance": 2,
        },
        "flavor_enhancer": {
            "categories": {
                "seasonings",
                "others",
                "snacks",
                "fruit_jam",
                "candies",
                "milk",
                "ice_cream_&_cheese",
                "dried_fruits",
                "instant_foods",
                "beverages",
                "alcoholic_beverages",
                "yogurt",
                "cakes",
            },
            "min_importance": 1,
        },
    }

    _PRIMARY_ROLES: Set[str] = {"core_protein", "core_produce", "core_staple"}
    _ROLE_COVERAGE_THRESHOLD: float = 0.5
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        path = Path("app/data/knowledge_base")
        
        # with open(path / "ingredient_knowledge_base.json", 'r', encoding='utf-8') as f:
        #     self.ingredients = {ing['id']: ing for ing in json.load(f)}
        
        # with open(path / "dish_knowledge_base.json", 'r', encoding='utf-8') as f:
        #     self.dishes = {d['id']: d for d in json.load(f)}

        with open(path / "ingredient_knowledge_base.json", "r", encoding="utf-8") as f:
            self.ingredients = {ing["id"]: ing for ing in json.load(f)}

        with open(path / "dish_knowledge_base.json", "r", encoding="utf-8") as f:
            self.dishes = {d["id"]: d for d in json.load(f)}

        self.dish_profiles: Dict[str, Dict[str, object]] = {}
        for dish_id, dish in self.dishes.items():
            profile = self._build_dish_profile(dish)
            self.dish_profiles[dish_id] = profile
        
        self._initialized = True

    def _build_dish_profile(self, dish: dict) -> Dict[str, object]:
        ingredients = dish.get("ingredients", [])
        importance_map: Dict[str, int] = {}
        role_map: Dict[str, str] = {}
        required_roles: Set[str] = set()

        total_importance = 0
        for ing in ingredients:
            ing_id = ing.get("ingredient_id")
            importance = int(ing.get("importance", 1))
            category = ing.get("category", "")
            total_importance += importance
            importance_map[ing_id] = importance

            role = self._determine_role(category, importance)
            if role:
                role_map[ing_id] = role
                if (
                    role in self._PRIMARY_ROLES
                    and importance >= self._ROLE_DEFINITIONS.get(role, {}).get("min_importance", 1)
                ):
                    required_roles.add(role)

        return {
            "importance_map": importance_map,
            "role_map": role_map,
            "required_roles": required_roles,
            "total_importance": total_importance,
        }
    
    def _determine_role(self, category: str, importance: int) -> Optional[str]:
        for role, config in self._ROLE_DEFINITIONS.items():
            if category in config.get("categories", set()) and importance >= config.get(
                "min_importance", 1
            ):
                return role
        if importance >= 3:
            # Nguyên liệu cực kỳ quan trọng nhưng chưa map -> xem như core_produce
            return "core_produce"
        return None

    def _get_importance(self, dish_id: str, ing_id: str) -> int:
        return int(
            self.dish_profiles.get(dish_id, {})
            .get("importance_map", {})
            .get(ing_id, 1)
        )
    
    def get_ingredient(self, ing_id: str) -> dict:
        return self.ingredients.get(ing_id)
    
    def get_dish(self, dish_id: str) -> dict:
        return self.dishes.get(dish_id)
    
    def search_similar_dishes(
        self,
        ing_ids: Iterable[str],
        min_match: int = 2,
        role_coverage_threshold: Optional[float] = None,
    ) -> List[dict]:
        matches: List[dict] = []
        ing_ids_set = set(ing_ids)
        threshold = (
            role_coverage_threshold
            if role_coverage_threshold is not None
            else self._ROLE_COVERAGE_THRESHOLD
        )
        
        for dish_id, dish in self.dishes.items():
            dish_ings = [i["ingredient_id"] for i in dish.get("ingredients", [])]
            if not dish_ings:
                continue

            matched = ing_ids_set & set(dish_ings)
            if len(matched) < min_match:
                continue

            profile = self.dish_profiles.get(dish_id, {})
            total_importance = profile.get("total_importance", 0)
            matched_importance = sum(
                self._get_importance(dish_id, ing_id) for ing_id in matched
            )
            weighted_score = (
                matched_importance / total_importance
                if total_importance
                else 0
            )

            required_roles = profile.get("required_roles", set())
            role_map = profile.get("role_map", {})
            matched_roles = {role_map[ing_id] for ing_id in matched if ing_id in role_map}
            coverage = (
                len(matched_roles & required_roles) / len(required_roles)
                if required_roles
                else 1
            )

            if coverage < threshold:
                continue

            matches.append(
                {
                    "dish_id": dish_id,
                    "dish_name": dish.get("name_vi", "Unknown"),
                    "match_count": len(matched),
                    "match_ratio": len(matched) / len(dish_ings),
                    "weighted_score": weighted_score,
                    "matched_roles": sorted(matched_roles),
                    "required_roles": sorted(required_roles),
                    "role_coverage": coverage,
                }
            )

        matches.sort(
            key=lambda x: (
                x["weighted_score"],
                x["match_ratio"],
                x["match_count"],
            ),
            reverse=True,
        )
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