"""
Script để restructure ingredient_conflict.json thành format dễ mapping hơn.

Chuyển từ:
{
  "dishes": ["Sữa đậu nành + trứng"],
  "conflicts": ["Trứng gà"]
}

Thành:
{
  "item_pairs": [
    {"name": "Sữa đậu nành", "ingredient_id": null},
    {"name": "Trứng", "ingredient_id": null}
  ],
  "conflict_details": [
    {"name": "Trứng gà", "ingredient_id": null}
  ]
}
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any


def normalize_text(text: str) -> str:
    """Chuẩn hóa text: lowercase, bỏ dấu tiếng Việt"""
    import unicodedata
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')
    return text


def split_dish_pairs(dish_str: str) -> List[str]:
    """
    Tách chuỗi 'A + B' hoặc 'A/B' thành list ['A', 'B']
    Ví dụ:
    - "Sữa đậu nành + trứng" -> ["Sữa đậu nành", "Trứng"]
    - "Rượu/bia" -> ["Rượu", "Bia"]
    """
    # Thử tách theo dấu +
    if '+' in dish_str:
        parts = [p.strip() for p in dish_str.split('+')]
        return [p for p in parts if p]
    
    # Thử tách theo dấu /
    if '/' in dish_str:
        parts = [p.strip() for p in dish_str.split('/')]
        return [p for p in parts if p]
    
    # Nếu không có dấu phân cách, trả về nguyên
    return [dish_str.strip()] if dish_str.strip() else []


def load_ingredient_kb():
    """Load ingredient knowledge base để match names"""
    kb_path = Path("app/data/knowledge_base/ingredient_knowledge_base.json")
    if not kb_path.exists():
        print(f"⚠️  Không tìm thấy {kb_path}")
        return {}
    
    with open(kb_path, 'r', encoding='utf-8') as f:
        ingredients = json.load(f)
    
    # Tạo map: normalized_name -> ingredient_id
    name_to_id = {}
    for ing in ingredients:
        ing_id = ing.get('id')
        name_vi = ing.get('name_vi', '')
        name_norm = normalize_text(name_vi)
        
        if name_norm and ing_id:
            name_to_id[name_norm] = ing_id
        
        # Thêm synonyms
        for syn in ing.get('synonyms', []):
            syn_norm = normalize_text(syn)
            if syn_norm and ing_id:
                name_to_id[syn_norm] = ing_id
    
    return name_to_id


def find_ingredient_id(name: str, name_to_id: Dict[str, str]) -> str:
    """Tìm ingredient_id cho một tên nguyên liệu"""
    name_norm = normalize_text(name)
    
    # Exact match
    if name_norm in name_to_id:
        return name_to_id[name_norm]
    
    # Partial match (tìm trong các key có chứa name_norm)
    for key, ing_id in name_to_id.items():
        if name_norm in key or key in name_norm:
            return ing_id
    
    return None


def restructure_conflict_entry(entry: Dict[str, Any], name_to_id: Dict[str, str]) -> Dict[str, Any]:
    """Restructure một entry từ format cũ sang format mới"""
    
    # Lấy danh sách dishes (có thể là "A + B" hoặc list)
    dishes = entry.get('dishes', [])
    all_pairs = []
    
    for dish in dishes:
        parts = split_dish_pairs(dish)
        for part in parts:
            if part:
                ing_id = find_ingredient_id(part, name_to_id)
                all_pairs.append({
                    "name": part.strip(),
                    "ingredient_id": ing_id
                })
    
    # Lấy danh sách conflicts
    conflicts = entry.get('conflicts', [])
    conflict_details = []
    
    for conflict in conflicts:
        # Có thể có dạng "A/B"
        parts = split_dish_pairs(conflict)
        for part in parts:
            if part:
                ing_id = find_ingredient_id(part, name_to_id)
                conflict_details.append({
                    "name": part.strip(),
                    "ingredient_id": ing_id
                })
    
    # Build entry mới
    new_entry = {
        "id": entry.get('id'),
        "item_pairs": all_pairs,
        "conflict_details": conflict_details,
        "severity": entry.get('severity', 'low'),
        "reason": entry.get('reason', ''),
        "advice": entry.get('advice', ''),
        "sources": entry.get('sources', [])
    }
    
    return new_entry


def main():
    # Load ingredient knowledge base
    print("📖 Đang load ingredient knowledge base...")
    name_to_id = load_ingredient_kb()
    print(f"✅ Đã load {len(name_to_id)} ingredient names")
    
    # Load conflict file
    conflict_path = Path("app/data/conflict/ingredient_conflict.json")
    if not conflict_path.exists():
        print(f"❌ Không tìm thấy {conflict_path}")
        return
    
    with open(conflict_path, 'r', encoding='utf-8') as f:
        conflicts = json.load(f)
    
    print(f"📋 Đang restructure {len(conflicts)} conflict entries...")
    
    # Restructure từng entry
    new_conflicts = []
    mapped_count = 0
    unmapped_items = []
    
    for entry in conflicts:
        new_entry = restructure_conflict_entry(entry, name_to_id)
        new_conflicts.append(new_entry)
        
        # Count mapped items
        for item in new_entry['item_pairs']:
            if item['ingredient_id']:
                mapped_count += 1
            else:
                unmapped_items.append((entry['id'], item['name']))
        
        for item in new_entry['conflict_details']:
            if item['ingredient_id']:
                mapped_count += 1
            else:
                unmapped_items.append((entry['id'], item['name']))
    
    # Save restructured file
    output_path = Path("app/data/conflict/ingredient_conflict_restructured.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(new_conflicts, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Đã lưu file restructured vào: {output_path}")
    print(f"📊 Thống kê:")
    print(f"   - Tổng số conflict entries: {len(new_conflicts)}")
    print(f"   - Số items đã map được ID: {mapped_count}")
    print(f"   - Số items chưa map được: {len(unmapped_items)}")
    
    if unmapped_items:
        print(f"\n⚠️  Các items chưa map được ID:")
        for conflict_id, item_name in unmapped_items[:20]:  # Hiển thị 20 items đầu
            print(f"   - [{conflict_id}] {item_name}")
        if len(unmapped_items) > 20:
            print(f"   ... và {len(unmapped_items) - 20} items khác")


if __name__ == "__main__":
    main()
