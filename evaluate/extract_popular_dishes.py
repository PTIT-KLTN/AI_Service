import json
from difflib import SequenceMatcher

# Đọc file knowledge base
with open(r'd:\DOAN_BT\THUCTAP\AI_Service\app\data\knowledge_base\dish_knowledge_base.json', 'r', encoding='utf-8') as f:
    dishes = json.load(f)

# Lọc món ăn có 10-20 nguyên liệu
filtered = [d for d in dishes if 10 <= len(d.get('ingredients', [])) <= 20]

print(f'Tổng số món: {len(dishes)}')
print(f'Món có 10-20 nguyên liệu: {len(filtered)}')

# Danh sách món ăn quen thuộc và đa dạng theo category
diverse_categories = {
    'mon canh': ['canh', 'súp', 'lẩu'],
    'mon pho_bun': ['phở', 'bún', 'miến', 'hủ tiếu', 'bánh đa', 'mì'],
    'mon com': ['cơm'],
    'mon xao': ['xào', 'rang'],
    'mon kho': ['kho', 'rim'],
    'mon nuong': ['nướng', 'quay'],
    'mon chien': ['chiên', 'rán'],
    'mon hap': ['hấp', 'luộc'],
    'mon goi': ['gỏi', 'salad', 'nộm'],
    'mon an vat': ['bánh', 'chả', 'nem', 'giò']
}

# Ưu tiên món phổ biến
priority_keywords = {
    'phở': 100,
    'bún': 90,
    'cơm': 85,
    'lẩu': 80,
    'canh': 70,
    'gỏi': 65,
    'xào': 60,
    'nướng': 55,
    'kho': 50,
    'hấp': 45,
    'chiên': 40,
    'súp': 35
}

# Tính độ tương đồng giữa 2 tên món
def calculate_similarity(name1, name2):
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()

# Kiểm tra món có thuộc category nào
def get_dish_category_type(dish_name):
    name_lower = dish_name.lower()
    for cat, keywords in diverse_categories.items():
        if any(kw in name_lower for kw in keywords):
            return cat
    return 'khac'

# Chấm điểm độ phổ biến với ưu tiên
def score_popularity(dish_name):
    name_lower = dish_name.lower()
    score = 0
    
    # Điểm ưu tiên cao
    for keyword, priority_score in priority_keywords.items():
        if keyword in name_lower:
            score += priority_score
    
    # Điểm phụ cho các từ khóa thông dụng khác
    common_keywords = [
        'gà', 'thịt', 'cá', 'tôm', 'bò', 'heo', 'sườn', 'chả', 
        'nem', 'salad', 'rang', 'rim', 'quay', 'rán', 'luộc'
    ]
    for kw in common_keywords:
        if kw in name_lower:
            score += 5
    
    return score

# Sắp xếp theo độ phổ biến
filtered_scored = [(d, score_popularity(d['name_vi'])) for d in filtered]
filtered_scored.sort(key=lambda x: (-x[1], x[0]['name_vi']))

# Nhóm món theo category type
category_groups = {}
for dish, score in filtered_scored:
    cat_type = get_dish_category_type(dish['name_vi'])
    if cat_type not in category_groups:
        category_groups[cat_type] = []
    category_groups[cat_type].append((dish, score))

print(f'\nPhân bố theo loại món:')
for cat, dishes_in_cat in category_groups.items():
    print(f'  {cat}: {len(dishes_in_cat)} món')

# Chọn đa dạng: lấy tối đa 4 món từ mỗi category (trừ món phở/bún/cơm lấy nhiều hơn)
selected = []
category_limits = {
    'mon pho_bun': 6,
    'mon com': 4,
    'mon canh': 4,
    'mon xao': 3,
    'mon goi': 3,
    'mon nuong': 3,
    'mon kho': 2,
    'mon chien': 2,
    'mon hap': 2,
    'mon an vat': 3,
    'khac': 2
}
similarity_threshold = 0.55

# Round 1: Lấy đại diện từ mỗi category theo limit
for cat_type in sorted(category_groups.keys(), key=lambda x: category_limits.get(x, 0), reverse=True):
    cat_dishes = category_groups[cat_type]
    limit = category_limits.get(cat_type, 2)
    count = 0
    
    for dish, score in cat_dishes:
        if count >= limit:
            break
        
        # Kiểm tra tương đồng với các món đã chọn trong cùng category
        is_too_similar = False
        for sel_dish in selected:
            if get_dish_category_type(sel_dish['name_vi']) == cat_type:
                similarity = calculate_similarity(dish['name_vi'], sel_dish['name_vi'])
                if similarity > similarity_threshold:
                    is_too_similar = True
                    break
        
        if not is_too_similar:
            selected.append(dish)
            count += 1

# Round 2: Nếu chưa đủ 30, lấy thêm món phổ biến nhất còn lại
if len(selected) < 30:
    for dish, score in filtered_scored:
        if len(selected) >= 30:
            break
        
        if dish not in selected:
            # Kiểm tra tương đồng với TẤT CẢ món đã chọn
            is_too_similar = False
            for sel_dish in selected:
                similarity = calculate_similarity(dish['name_vi'], sel_dish['name_vi'])
                if similarity > 0.7:  # Ngưỡng cao hơn cho round 2
                    is_too_similar = True
                    break
            
            if not is_too_similar:
                selected.append(dish)

top_30 = selected[:30]

# Xuất kết quả
result = []
for dish in top_30:
    result.append({
        'dish_id': dish['id'],
        'name_vi': dish['name_vi'],
        'name_normalize': dish['name_normalized'],
        'category': dish['category']
    })

# Lưu file
output_path = r'd:\DOAN_BT\THUCTAP\AI_Service\popular_dishes_30.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f'\n✅ Đã lưu 30 món ăn vào: {output_path}')
print('\nDanh sách 30 món đa dạng:')
print('=' * 80)

# Nhóm kết quả theo category để hiển thị
result_by_cat = {}
for d in result:
    orig_dish = [dd for dd in dishes if dd['id'] == d['dish_id']][0]
    ing_count = len(orig_dish['ingredients'])
    cat_type = get_dish_category_type(d['name_vi'])
    
    if cat_type not in result_by_cat:
        result_by_cat[cat_type] = []
    result_by_cat[cat_type].append((d, ing_count))

i = 1
for cat_type in sorted(result_by_cat.keys()):
    print(f'\n[{cat_type.upper()}]')
    for d, ing_count in result_by_cat[cat_type]:
        print(f'{i:2}. {d["name_vi"]:45} ({d["dish_id"]}) - {ing_count} nguyên liệu')
        i += 1
print('=' * 80)
