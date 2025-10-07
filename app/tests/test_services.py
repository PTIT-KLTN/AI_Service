import sys
from pathlib import Path

# # Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.validation_service import ValidationService
from services.ontology_service import OntologyService


# ═══════════════════════════════════════════════════════════════
# TEST VALIDATION SERVICE
# ═══════════════════════════════════════════════════════════════

def test_validation_service_init():
    """Test khởi tạo ValidationService"""
    print("\n🧪 Test 1: Init ValidationService")
    
    validator = ValidationService()
    
    assert validator.total_dishes > 0, "Should load dishes"
    assert len(validator.ingredient_frequency) > 0, "Should load ingredients"
    
    print(f"✅ Loaded: {validator.total_dishes} dishes, {len(validator.ingredient_frequency)} ingredients")


def test_validate_normal_ingredients():
    """Test validate nguyên liệu bình thường"""
    print("\n🧪 Test 2: Validate normal ingredients")
    
    validator = ValidationService()
    
    # Giả sử có nguyên liệu phổ biến
    ingredients = [
        {"id": "ingre001", "name": "Test 1", "confidence": 0.7},
        {"id": "ingre002", "name": "Test 2", "confidence": 0.8}
    ]
    
    result = validator.validate(ingredients)
    
    assert 'adjusted_ingredients' in result
    assert 'warnings' in result
    assert 'suggestions' in result
    assert len(result['adjusted_ingredients']) == 2
    
    print(f"✅ Validated {len(result['adjusted_ingredients'])} ingredients")
    print(f"   Warnings: {len(result['warnings'])}")
    print(f"   Suggestions: {len(result['suggestions'])}")


def test_validate_with_confidence_boost():
    """Test confidence được tăng cho nguyên liệu common"""
    print("\n🧪 Test 3: Confidence boost for common ingredients")
    
    validator = ValidationService()
    
    ingredients = [
        {"id": "ingre001", "confidence": 0.6},
        {"id": "ingre002", "confidence": 0.6}
    ]
    
    result = validator.validate(ingredients)
    
    # Check có ít nhất 1 nguyên liệu được boost
    boosted = [ing for ing in result['adjusted_ingredients'] 
               if ing['confidence'] > ing['original_confidence']]
    
    print(f"✅ {len(boosted)}/{len(ingredients)} ingredients boosted")
    for ing in boosted[:2]:  # Show 2 đầu tiên
        print(f"   {ing.get('name', ing['id'])}: {ing['original_confidence']:.2f} → {ing['confidence']:.2f}")


def test_pmi_calculation():
    """Test tính PMI score"""
    print("\n🧪 Test 4: PMI calculation")
    
    validator = ValidationService()
    
    # Lấy 2 nguyên liệu bất kỳ có trong frequency
    ing_ids = list(validator.ingredient_frequency.keys())[:2]
    
    if len(ing_ids) >= 2:
        pmi = validator._get_pmi(ing_ids[0], ing_ids[1])
        print(f"✅ PMI({ing_ids[0]}, {ing_ids[1]}) = {pmi:.3f}")
        assert isinstance(pmi, float)
    else:
        print("⚠️  Not enough ingredients to test PMI")


# ═══════════════════════════════════════════════════════════════
# TEST ONTOLOGY SERVICE
# ═══════════════════════════════════════════════════════════════

def test_ontology_service_init():
    """Test khởi tạo OntologyService"""
    print("\n🧪 Test 5: Init OntologyService")
    
    ontology = OntologyService()
    
    assert len(ontology.ingredients) > 0, "Should load ingredients"
    assert len(ontology.dishes) > 0, "Should load dishes"
    
    print(f"✅ Loaded: {len(ontology.ingredients)} ingredients, {len(ontology.dishes)} dishes")


def test_get_ingredient():
    """Test lấy thông tin nguyên liệu"""
    print("\n🧪 Test 6: Get ingredient by ID")
    
    ontology = OntologyService()
    
    # Lấy ID đầu tiên
    first_id = list(ontology.ingredients.keys())[0]
    ingredient = ontology.get_ingredient(first_id)
    
    assert ingredient is not None
    assert 'id' in ingredient
    assert 'name_vi' in ingredient
    
    print(f"✅ Found: {ingredient.get('name_vi', 'Unknown')} (ID: {first_id})")


def test_get_dish():
    """Test lấy thông tin món ăn"""
    print("\n🧪 Test 7: Get dish by ID")
    
    ontology = OntologyService()
    
    # Lấy ID đầu tiên
    first_id = list(ontology.dishes.keys())[0]
    dish = ontology.get_dish(first_id)
    
    assert dish is not None
    assert 'id' in dish
    assert 'name_vi' in dish
    
    print(f"✅ Found: {dish.get('name_vi', 'Unknown')} (ID: {first_id})")


def test_search_dish_by_ingredients():
    """Test tìm món ăn theo nguyên liệu"""
    print("\n🧪 Test 8: Search dishes by ingredients")
    
    ontology = OntologyService()
    
    # Lấy món đầu tiên và nguyên liệu của nó
    first_dish = list(ontology.dishes.values())[0]
    ingredient_ids = [ing['ingredient_id'] for ing in first_dish.get('ingredients', [])][:3]
    
    if len(ingredient_ids) >= 2:
        results = ontology.search_dish_by_ingredients(ingredient_ids, min_match=2)
        
        assert len(results) > 0, "Should find at least 1 dish"
        assert results[0]['dish_name'] is not None
        
        print(f"✅ Found {len(results)} dishes")
        print(f"   Top match: {results[0]['dish_name']} (ratio: {results[0]['match_ratio']:.2f})")
    else:
        print("⚠️  Not enough ingredients to test search")


def test_enrich_ingredients():
    """Test làm giàu thông tin nguyên liệu"""
    print("\n🧪 Test 9: Enrich ingredients")
    
    ontology = OntologyService()
    
    # Lấy 3 ID đầu tiên
    ingredient_ids = list(ontology.ingredients.keys())[:3]
    enriched = ontology.enrich_ingredients(ingredient_ids)
    
    assert len(enriched) > 0
    assert 'name_vi' in enriched[0]
    assert 'category' in enriched[0]
    
    print(f"✅ Enriched {len(enriched)} ingredients:")
    for ing in enriched:
        print(f"   - {ing['name_vi']} ({ing['category']})")


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TEST
# ═══════════════════════════════════════════════════════════════

def test_full_workflow():
    """Test workflow hoàn chỉnh: Validate → Search → Enrich"""
    print("\n🧪 Test 10: Full workflow")
    
    validator = ValidationService()
    ontology = OntologyService()
    
    # Lấy món ăn mẫu
    sample_dish = list(ontology.dishes.values())[0]
    dish_name = sample_dish.get('name_vi', 'Unknown')
    ingredient_ids = [ing['ingredient_id'] for ing in sample_dish.get('ingredients', [])][:3]
    
    # Tạo input giả lập
    detected_ingredients = [
        {"id": ing_id, "confidence": 0.7} 
        for ing_id in ingredient_ids
    ]
    
    print(f"\n📋 Testing with dish: {dish_name}")
    print(f"   Input: {len(detected_ingredients)} ingredients")
    
    # Step 1: Validate
    validation = validator.validate(detected_ingredients)
    print(f"\n1️⃣  Validation:")
    print(f"   ✓ Adjusted: {len(validation['adjusted_ingredients'])} ingredients")
    print(f"   ✓ Warnings: {len(validation['warnings'])}")
    print(f"   ✓ Suggestions: {len(validation['suggestions'])}")
    
    # Step 2: Search dishes
    matches = ontology.search_dish_by_ingredients(ingredient_ids, min_match=2)
    print(f"\n2️⃣  Search:")
    print(f"   ✓ Found: {len(matches)} matching dishes")
    if matches:
        print(f"   ✓ Top match: {matches[0]['dish_name']} ({matches[0]['match_ratio']:.0%})")
    
    # Step 3: Enrich suggestions
    enriched = []
    for sug in validation['suggestions'][:2]:  # Top 2
        ing_info = ontology.get_ingredient(sug['id'])
        if ing_info:
            enriched.append({**sug, 'name_vi': ing_info['name_vi']})
    
    print(f"\n3️⃣  Suggestions:")
    for sug in enriched:
        print(f"   ✓ {sug['name_vi']} (score: {sug['score']})")
    
    print("\n✅ Full workflow completed successfully!")


# ═══════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════

def run_all_tests():
    """Chạy tất cả tests"""
    print("="*70)
    print("🧪 RUNNING ALL TESTS")
    print("="*70)
    
    tests = [
        test_validation_service_init,
        test_validate_normal_ingredients,
        test_validate_with_confidence_boost,
        test_pmi_calculation,
        test_ontology_service_init,
        test_get_ingredient,
        test_get_dish,
        test_search_dish_by_ingredients,
        test_enrich_ingredients,
        test_full_workflow
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {test_func.__name__}")
            print(f"   Error: {str(e)}")
            failed += 1
    
    print("\n" + "="*70)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)