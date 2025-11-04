"""
Test processing time - So sánh thời gian xử lý 2 món ăn
"""
import sys
from pathlib import Path
import time
import json

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.main_optimized import OptimizedShoppingCartPipeline


def measure_step_times(pipeline, user_input):
    """Đo thời gian từng bước xử lý"""
    times = {}
    results = {}
    
    try:
        # Step 1: Extract dish name
        start = time.perf_counter()
        extracted = pipeline.extractor.extract_dish_name(user_input)
        times['step1_extract_dish'] = round((time.perf_counter() - start) * 1000, 2)
        
        dish_name = extracted.get('dish_name', '')
        results['dish_name'] = dish_name
        results['excluded_items'] = extracted.get('excluded_items', [])
        
        # Step 2: Get recipe from KB
        start = time.perf_counter()
        recipe = pipeline.kb_service.get_dish_recipe(dish_name)
        times['step2_get_recipe_kb'] = round((time.perf_counter() - start) * 1000, 2)
        
        # Step 3: Extract ingredients
        start = time.perf_counter()
        ingredients_raw = recipe.get('ingredients', [])
        times['step3_extract_ingredients'] = round((time.perf_counter() - start) * 1000, 2)
        
        # Step 4: Normalize ingredients
        start = time.perf_counter()
        normalized_items = []
        for ing_dict in ingredients_raw:
            normalized = pipeline._normalize_single_ingredient(ing_dict)
            if normalized:
                normalized_items.append(normalized)
        times['step4_normalize_ingredients'] = round((time.perf_counter() - start) * 1000, 2)
        results['cart_items'] = len(normalized_items)
        
        # Step 5: Generate suggestions
        start = time.perf_counter()
        cart_ingredient_ids = [item['ingredient']['ingredient_id'] for item in normalized_items]
        suggestions = pipeline.suggestion_service.get_suggestions(cart_ingredient_ids, dish_name)
        times['step5_generate_suggestions'] = round((time.perf_counter() - start) * 1000, 2)
        results['suggestions_count'] = len(suggestions)
        
        # Step 6: Find similar dishes
        start = time.perf_counter()
        similar_dishes = pipeline.ontology.search_similar_dishes(cart_ingredient_ids, min_match=2)
        times['step6_find_similar_dishes'] = round((time.perf_counter() - start) * 1000, 2)
        results['similar_dishes_count'] = len(similar_dishes)
        
        # Step 7: Check conflicts
        start = time.perf_counter()
        excluded_items = extracted.get('excluded_items', [])
        conflicts = []
        if excluded_items:
            conflicts = pipeline.conflicts.check_conflicts(normalized_items, excluded_items)
        times['step7_check_conflicts'] = round((time.perf_counter() - start) * 1000, 2)
        results['conflicts_count'] = len(conflicts)
        
        results['success'] = True
        
    except Exception as e:
        results['success'] = False
        results['error'] = str(e)
    
    return times, results


def test_processing_time():
    """Test và so sánh thời gian xử lý 2 món ăn"""
    
    # Test inputs
    test_inputs = [
        "tôi muốn ăn món phở bò",
        "Tôi muốn ăn món bún đậu mắm tôm nhưng không ăn đậu phộng và dị ứng tỏi"
    ]
    
    # Initialize pipeline
    pipeline = OptimizedShoppingCartPipeline(max_workers=3, recipe_cache_ttl=3600)
    
    # Results
    all_results = {}
    
    # Test 1: Phở bò
    print("\nTesting: pho bo...")
    total_start = time.perf_counter()
    times1, info1 = measure_step_times(pipeline, test_inputs[0])
    total_time1 = round((time.perf_counter() - total_start) * 1000, 2)
    
    all_results['test1_pho_bo'] = {
        'input': test_inputs[0],
        'total_time_ms': total_time1,
        'total_time_seconds': round(total_time1 / 1000, 2),
        'steps_ms': times1,
        'info': info1
    }
    
    # Calculate percentages
    all_results['test1_pho_bo']['steps_percentage'] = {}
    for step_name, step_time in times1.items():
        pct = round((step_time / total_time1) * 100, 1)
        all_results['test1_pho_bo']['steps_percentage'][step_name] = pct
    
    print(f"  Completed: {total_time1}ms ({round(total_time1/1000, 2)}s)")
    
    # Test 2: Bún đậu
    print("\nTesting: bun dau...")
    total_start = time.perf_counter()
    times2, info2 = measure_step_times(pipeline, test_inputs[1])
    total_time2 = round((time.perf_counter() - total_start) * 1000, 2)
    
    all_results['test2_bun_dau'] = {
        'input': test_inputs[1],
        'total_time_ms': total_time2,
        'total_time_seconds': round(total_time2 / 1000, 2),
        'steps_ms': times2,
        'info': info2
    }
    
    # Calculate percentages
    all_results['test2_bun_dau']['steps_percentage'] = {}
    for step_name, step_time in times2.items():
        pct = round((step_time / total_time2) * 100, 1)
        all_results['test2_bun_dau']['steps_percentage'][step_name] = pct
    
    print(f"  Completed: {total_time2}ms ({round(total_time2/1000, 2)}s)")
    
    # Comparison
    time_diff = total_time2 - total_time1
    all_results['comparison'] = {
        'time_difference_ms': round(time_diff, 2),
        'time_difference_seconds': round(time_diff / 1000, 2),
        'percentage_difference': round((time_diff / total_time1) * 100, 1),
        'test2_vs_test1': 'slower' if time_diff > 0 else 'faster'
    }
    
    # Step-by-step comparison
    all_results['comparison']['steps_comparison'] = {}
    
    # Get all step names from both tests
    all_step_names = set(list(times1.keys()) + list(times2.keys()))
    
    for step_name in sorted(all_step_names):
        time1_val = times1.get(step_name, 0)
        time2_val = times2.get(step_name, 0)
        diff = time2_val - time1_val
        all_results['comparison']['steps_comparison'][step_name] = {
            'test1_ms': time1_val,
            'test2_ms': time2_val,
            'difference_ms': round(diff, 2),
            'test2_vs_test1': 'slower' if diff > 0 else 'faster'
        }
    
    # Slowest steps
    all_results['slowest_steps'] = {
        'test1_pho_bo': [],
        'test2_bun_dau': []
    }
    
    sorted_steps1 = sorted(times1.items(), key=lambda x: x[1], reverse=True)
    for step_name, step_time in sorted_steps1[:3]:
        pct = round((step_time / total_time1) * 100, 1)
        all_results['slowest_steps']['test1_pho_bo'].append({
            'step': step_name,
            'time_ms': step_time,
            'percentage': pct
        })
    
    sorted_steps2 = sorted(times2.items(), key=lambda x: x[1], reverse=True)
    for step_name, step_time in sorted_steps2[:3]:
        pct = round((step_time / total_time2) * 100, 1)
        all_results['slowest_steps']['test2_bun_dau'].append({
            'step': step_name,
            'time_ms': step_time,
            'percentage': pct
        })
    
    # Save to JSON
    with open('processing_time_comparison.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("\n✅ Results saved to: processing_time_comparison.json\n")
    
    # Print summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nTest 1 (Pho bo):     {total_time1}ms ({round(total_time1/1000, 2)}s)")
    print(f"Test 2 (Bun dau):    {total_time2}ms ({round(total_time2/1000, 2)}s)")
    print(f"Difference:          {abs(time_diff)}ms ({'slower' if time_diff > 0 else 'faster'})")
    print(f"Percentage:          {abs(round((time_diff / total_time1) * 100, 1))}%")
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    test_processing_time()
