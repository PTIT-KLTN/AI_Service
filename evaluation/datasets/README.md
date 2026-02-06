# Evaluation Datasets Documentation

## Tổng quan

Ba bộ dataset đánh giá được sinh tự động, deterministic (fixed seeds) để đo lường hiệu năng của AI Service pipeline: dish extraction → RAG retrieval → ontology normalization → conflict detection → replacement suggestion.

**Metadata chung:**
- Dataset version: `v1`
- Format: JSONL (JSON Lines)
- **Scale:** ~3,000 test cases (30% của ~10,000 GT dishes)
- Reproducible: Identical outputs với fixed seeds
- Offline: Không sử dụng external APIs

---

## 1. Dish Query Set

**Mục đích:** Đánh giá độ chính xác dish extraction, ingredient resolution, và ontology normalization.

### Cấu trúc

**Thư mục:** `dish_query_set/`

**Files:**
- `dish_queries_in_kb.jsonl` (~750 cases) - Queries từ dish names có trong KB
- `dish_queries_out_kb.jsonl` (~750 cases) - Queries paraphrased/noisy
- `stats.json` - Thống kê và metadata

### Phân loại Queries

**IN-KB Split (~750 cases):**
- **Base** (300): Chỉ dish name, không modification
- **Excluded** (200): Loại bỏ 1 ingredient từ dish gốc
- **Extra** (200): Thêm 1 ingredient không có trong dish gốc
- **Excluded+Extra** (50): Kết hợp loại bỏ và thêm ingredient

**OUT-OF-KB Split (~750 cases):**
- **Paraphrased** (750): Dish names với typos, reordering, Vietnamese prefixes/suffixes

### Schema Record

```json
{
  "case_id": "DQ_IN_0001",
  "split": "in_kb" | "out_kb",
  "user_input": "Tôi muốn nấu phở bò, bỏ hành, thêm trứng",
  "expected": {
    "dish_id": "dish0001",
    "dish_name_vi": "Phở bò",
    "gt_ingredient_ids": ["ingre001", "ingre002"],
    "gt_core_ingredient_ids": ["ingre001"],
    "excluded": {
      "names": ["Hành"],
      "ingredient_ids": ["ingre003"]
    },
    "extra": {
      "names": ["Trứng"],
      "ingredient_ids": ["ingre004"]
    }
  },
  "tags": ["base"|"excluded"|"extra"|"excluded+extra"|"paraphrased"],
  "meta": { "seed": 2024, "dataset_version": "v1", ... }
}
```

### Metrics Đánh giá

- **Dish Extraction Accuracy:** % dish_id match chính xác
- **Ingredient P/R/F1:** Precision, Recall, F1 trên ingredient_ids
- **Core Ingredient F1:** F1 score trên core ingredients (importance ≥ 2)
- **Excluded Resolution Rate:** % excluded ingredients được resolve đúng
- **Extra Resolution Rate:** % extra ingredients được resolve đúng

---

## 2. Conflict Unit Set

**Mục đích:** Đánh giá độ chính xác conflict detection độc lập, không phụ thuộc dish retrieval hay LLM.

### Cấu trúc

**Thư mục:** `conflict_unit_set/`

**Files:**
- `conflict_unit_tests.jsonl` (~800 cases)
- `stats.json`

### Phân loại Cases

- **Single Pair** (480): 1 conflict pair
- **Multi Pair** (320): 2-3 conflict pairs không overlap

**Input Format Distribution:**
- 40% `name`: Chỉ name_vi
- 40% `id`: Chỉ ingredient_id
- 20% `mixed`: Cả name_vi và ingredient_id

### Schema Record

```json
{
  "case_id": "CF_0001",
  "input_ingredients": {
    "format": "name"|"id"|"mixed",
    "items": [
      {"name_vi": "Sữa", "ingredient_id": "ingre001"},
      {"name_vi": "Chanh", "ingredient_id": "ingre002"}
    ]
  },
  "expected": {
    "conflict_pairs": [
      {
        "a_id": "ingre001",
        "b_id": "ingre002",
        "severity": "high"|"medium"|"low",
        "reason": "..."
      }
    ],
    "conflict_count": 1
  },
  "tags": ["single_pair"|"multi_pair", "severity_*"],
  "meta": { "seed": 2025, ... }
}
```

### Metrics Đánh giá

- **Conflict Detection Precision/Recall:** % conflict pairs phát hiện chính xác
- **Severity Classification Accuracy:** % severity level đúng
- **False Positive Rate:** % non-conflict pairs bị báo nhầm
- **Resolution Rate:** % pairs có cả a_id và b_id resolved

---

## 3. Replacement Constraint Set

**Mục đích:** Đánh giá constraint satisfaction của replacement suggestions: same category, exclude conflicts, uniqueness, size cap (K=3).

### Cấu trúc

**Thư mục:** `replacement_constraint_set/`

**Files:**
- `replacement_cases.jsonl` (~700 cases)
- `stats.json`

### Đặc điểm Dataset

- **Source:** Derived từ conflict rules
- **Valid Cases:** 80%+ có valid replacements trong ontology
- **Edge Cases:** 20% không có valid replacements (test robustness)

### Schema Record

```json
{
  "case_id": "RP_0001",
  "context": {
    "dish_id": null,
    "dish_name_vi": null,
    "conflicted_pair": {"a_id": "ingre001", "b_id": "ingre002"},
    "target_replace_id": "ingre001",
    "target_category": "vegetables",
    "exclude_ids": ["ingre001", "ingre002", "ingre003"]
  },
  "constraints": {
    "same_category": true,
    "must_not_include_ids": ["ingre001", "ingre002"],
    "unique": true,
    "max_suggestions": 3
  },
  "expected": {
    "valid_replacement_exists_in_ontology": true,
    "min_valid_suggestions": 1
  },
  "tags": ["from_conflict_rules", "category_based"],
  "meta": { "seed": 2026, ... }
}
```

### Metrics Đánh giá

- **Constraint Satisfaction Rate:** % suggestions thỏa mãn tất cả constraints
- **Category Match Rate:** % suggestions cùng category với target
- **Exclusion Compliance:** % suggestions không chứa excluded IDs
- **Uniqueness Rate:** % suggestions không duplicate
- **Coverage:** % cases có ≥1 valid suggestion

---

## Sử dụng Datasets

### Load JSONL

```python
import json

def load_jsonl(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f]

# Load dataset
dish_queries = load_jsonl('dish_query_set/dish_queries_in_kb.jsonl')
conflicts = load_jsonl('conflict_unit_set/conflict_unit_tests.jsonl')
replacements = load_jsonl('replacement_constraint_set/replacement_cases.jsonl')
```

### Load Statistics

```python
with open('dish_query_set/stats.json', 'r', encoding='utf-8') as f:
    stats = json.load(f)
    print(f"Total IN-KB cases: {stats['in_kb']['total_cases']}")
    print(f"Avg ingredients: {stats['in_kb']['avg_gt_ingredient_count']:.2f}")
```

---

## Reproducibility

**Fixed Seeds:**
- Dish Query Set: `2024`
- Conflict Unit Set: `2025`
- Replacement Constraint Set: `2026`

**Regenerate:**
```bash
cd evaluation
jupyter notebook 01_build_eval_datasets.ipynb
# Run all cells
```

Output sẽ identical với lần chạy trước nếu source data không thay đổi.

---

## Dataset Quality Checks

✅ **Dish Query Set:**
- 90%+ excluded ingredients resolvable
- 90%+ extra ingredients resolvable
- Diverse dish distribution (low duplication)
- OUT-OF-KB inputs khác biệt với canonical names

✅ **Conflict Unit Set:**
- 100% cases có ≥1 expected conflict pair
- 70%+ cases có both IDs resolved
- Multiple severity levels represented

✅ **Replacement Constraint Set:**
- 80%+ cases có valid replacements in ontology
- 80%+ target_category resolved
- 20% edge cases cho robustness testing

---

**Generated by:** `01_build_eval_datasets.ipynb`  
**Version:** v1  
**Last updated:** 2026-02-06
