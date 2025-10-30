"""
Suggestion Service.
Generates ingredient suggestions and finds similar dishes.
"""
from typing import List, Dict, Any


class SuggestionService:
    """Generates suggestions for related ingredients and dishes."""
    
    def __init__(self, ontology_service, unit_converter, validation_service=None):
        """
        Initialize service.
        
        Args:
            ontology_service: OntologyService for ingredient/dish data
            unit_converter: UnitConverterService for normalizing quantities
            validation_service: ValidationService for PMI-based suggestions (optional)
        """
        self.ontology = ontology_service
        self.converter = unit_converter
        self.validator = validation_service
    
    def get_suggestions(
        self,
        current_ingredient_ids: List[str],
        dish_name: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Get ingredient suggestions based on PMI co-occurrence patterns.
        
        Args:
            current_ingredient_ids: List of current ingredient IDs in cart
            dish_name: Optional dish name for context
            
        Returns:
            List of suggested ingredients with metadata
        """
        if not current_ingredient_ids:
            return []
        
        # If validator not available, return empty
        if not self.validator:
            return []
        
        excluded_ids = self._build_exclusion_set(current_ingredient_ids)
        allowed_categories = self._get_allowed_categories(dish_name)
        
        # Use ValidationService for PMI-based suggestions
        raw_suggestions = self.validator.suggest_ingredients(
            seed_ids=current_ingredient_ids,
            allowed_categories=allowed_categories,
            ban_ids=excluded_ids,
            top_k=5,
            ingredients=self.ontology.ingredients
        )
        
        suggestions = []
        for sug in raw_suggestions:
            ing_data = self.ontology.get_ingredient(sug['id'])
            if not ing_data:
                continue
            
            suggestion_item = {
                'ingredient_id': sug['id'],
                'name_vi': ing_data.get('name_vi', ''),
                'category': ing_data.get('category', 'other'),
                'quantity': '',
                'unit': '',
                'score': sug['score'],
            }
            
            converted = self.converter.normalize_ingredients([suggestion_item])
            if converted:
                suggestions.append(converted[0])
        
        return suggestions
    
    def find_similar_dishes(
        self,
        ingredient_ids: List[str],
        min_match: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find dishes similar to current ingredients.
        
        Args:
            ingredient_ids: List of ingredient IDs
            min_match: Minimum number of matching ingredients
            
        Returns:
            List of similar dishes
        """
        return self.ontology.search_similar_dishes(
            ingredient_ids=ingredient_ids,
            min_match=min_match
        )
    
    def _build_exclusion_set(self, current_ids: List[str]) -> set:
        """Build set of ingredient IDs to exclude from suggestions."""
        excluded = set(current_ids)
        
        for ing_id in current_ids:
            ing_data = self.ontology.get_ingredient(ing_id)
            if not ing_data:
                continue
            
            category = ing_data.get('category', '')
            
            if category in {'protein', 'meat', 'seafood'}:
                protein_ids = self.ontology.get_ingredients_by_category(
                    ['protein', 'meat', 'seafood']
                )
                excluded.update(protein_ids)
            
            if category in {'starch', 'grain'}:
                starch_ids = self.ontology.get_ingredients_by_category(['starch', 'grain'])
                excluded.update(starch_ids)
        
        return excluded
    
    def _get_allowed_categories(self, dish_name: str) -> set:
        """Get allowed ingredient categories for a dish type."""
        if not dish_name:
            return set()
        
        dish_lower = dish_name.lower()
        
        salad_keywords = ['salad', 'sa lát', 'gỏi', 'nộm']
        if any(kw in dish_lower for kw in salad_keywords):
            return {'vegetable', 'herb', 'spice', 'condiment', 'protein', 'other'}
        
        soup_keywords = ['soup', 'súp', 'canh', 'cháo', 'phở']
        if any(kw in dish_lower for kw in soup_keywords):
            return {'vegetable', 'protein', 'meat', 'seafood', 'herb', 'spice', 'other'}
        
        return set()
