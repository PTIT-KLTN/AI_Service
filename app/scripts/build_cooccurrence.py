import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime

def build_cooccurrence_matrix():
    """Build ma trận co-occurrence từ knowledge base"""
    
    print("🔨 Building co-occurrence matrix...")
    
    # Load data
    kb_path = Path("app/data/knowledge_base")
    with open(kb_path / "dish_knowledge_base.json", 'r', encoding='utf-8') as f:
        dishes = json.load(f)
    
    # Build matrix
    cooccurrence = defaultdict(lambda: defaultdict(int))
    frequency = defaultdict(int)
    
    for dish in dishes:
        ing_ids = [ing['ingredient_id'] for ing in dish.get('ingredients', [])]
        
        # Count frequency
        for ing_id in ing_ids:
            frequency[ing_id] += 1
        
        # Count co-occurrence
        for i, id1 in enumerate(ing_ids):
            for id2 in ing_ids[i+1:]:
                cooccurrence[id1][id2] += 1
                cooccurrence[id2][id1] += 1
    
    # Save to files
    output_path = Path("app/data/cooccurrence")
    output_path.mkdir(parents=True, exist_ok=True)
    
    with open(output_path / "matrix.json", 'w', encoding='utf-8') as f:
        json.dump(cooccurrence, f, ensure_ascii=False, indent=2)
    
    with open(output_path / "frequency.json", 'w', encoding='utf-8') as f:
        json.dump(frequency, f, ensure_ascii=False, indent=2)
    
    with open(output_path / "metadata.json", 'w', encoding='utf-8') as f:
        json.dump({
            'total_dishes': len(dishes),
            'total_ingredients': len(frequency),
            'build_date': datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Matrix built successfully!")
    print(f"   - {len(dishes)} dishes")
    print(f"   - {len(frequency)} ingredients")
    print(f"   - Saved to: {output_path}")

if __name__ == "__main__":
    build_cooccurrence_matrix()