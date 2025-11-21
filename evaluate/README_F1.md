# README – Đánh giá F1-Score cho Hệ thống RAG

## 📋 Giới thiệu

Tài liệu này mô tả quy trình đánh giá chất lượng hệ thống **RAG (Retrieval-Augmented Generation)** khi truy xuất công thức món ăn, so sánh với **Knowledge Base** gốc. Điểm đặc biệt là sử dụng **LLM để so sánh ngữ nghĩa** thay vì so khớp chuỗi thông thường, giúp phát hiện các nguyên liệu đồng nghĩa, viết khác hoặc lỗi chính tả.

### 🎯 Mục tiêu

- Đánh giá độ chính xác (Precision) và đầy đủ (Recall) của danh sách nguyên liệu từ RAG
- So sánh ngữ nghĩa để phát hiện các trường hợp đồng nghĩa ("Gạo nếp" ≈ "Gạo nếp cái hoa vàng")
- Đo lường sai số về số lượng nguyên liệu (MAE, MAPE)
- Tạo báo cáo chi tiết theo món, theo category, và tổng thể

---

## 🔄 Quy trình Xử lý

### **1. Chuẩn bị Dữ liệu**

**Input:** File `popular_dishes_30.json` chứa 30 món ăn phổ biến từ Knowledge Base, mỗi món có `dish_id`, `name_vi`, và `category`.

**Knowledge Base gốc:**
- `dish_knowledge_base.json`: Danh sách món ăn với nguyên liệu chuẩn (Ground Truth)

### **2. Trích xuất Kết quả RAG**

**Notebook:** `extract_rag_predictions.ipynb`

Quy trình tự động:
1. Khởi tạo pipeline kết nối với AWS Bedrock Knowledge Base
2. Với mỗi món trong 30 món test, gọi RAG để lấy danh sách nguyên liệu
3. Lưu kết quả vào `predictions_cache_v1.json` (bao gồm Ground Truth và RAG Prediction)


### **3. So sánh Ngữ nghĩa bằng LLM**

**Notebook:** `f1-evaluation (1).ipynb`  
**Model:** Qwen/Qwen2.5-3B-Instruct

#### Tại sao dùng LLM?

Thay vì so khớp chuỗi thông thường (exact matching), LLM hiểu **ngữ nghĩa** của nguyên liệu:

| Trường hợp | Exact Match | Semantic Match (LLM) |
|------------|-------------|---------------------|
| "Gạo nếp" vs "Gạo nếp cái hoa vàng" | ❌ | ✅ |
| "Thịt bò" vs "Thịt bò Úc" | ❌ | ✅ |
| "Cà rốt" vs "Củ cà rốt" | ❌ | ✅ |
| "Bí đỏ" vs "Pumpkin" | ❌ | ✅ |

#### Cách hoạt động:

1. **Xây dựng Prompt:** Liệt kê nguyên liệu GT (G1, G2, ...) và Pred (P1, P2, ...), yêu cầu LLM xác định cặp khớp ngữ nghĩa
2. **LLM Inference:** Model trả về các cặp dạng "G1 P3", "G2 P1"
3. **Parse & Validate:** Đảm bảo mỗi nguyên liệu chỉ khớp 1-1

### **4. Tính toán Metrics**

#### Ingredient-Level (F1-Score)

**a) Micro-F1 All Ingredients**

Đánh giá trên tất cả nguyên liệu:

$$
\text{Precision} = \frac{TP}{TP + FP}, \quad \text{Recall} = \frac{TP}{TP + FN}, \quad \text{F1} = \frac{2 \times \text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}
$$

**b) Micro-F1 Core Ingredients**

Chỉ đánh giá nguyên liệu quan trọng (`importance >= 2`), tập trung vào những nguyên liệu chính tạo nên đặc trưng món ăn.

#### Slot-Level (Quantity Error)

Đo sai số số lượng trên các cặp đã match:

- **MAE** (Mean Absolute Error): Sai số tuyệt đối trung bình
- **MAPE** (Mean Absolute Percentage Error): Sai số phần trăm trung bình

#### Category-Level

Tính Precision, Recall, F1 riêng cho từng loại nguyên liệu (Ngũ cốc, Thịt, Rau củ, Gia vị, Hải sản, ...).

### **5. Xuất Kết quả**

**Output:**
- `semantic_f1_per_dish.csv`: Chi tiết metrics từng món (dish_name, num_gt, num_pred, tp, fp, fn, precision, recall, f1)
- `semantic_f1_summary.json`: Tổng hợp toàn bộ (ingredient_level, slot_level, category_level, error_statistics)

---

## 💡 Ưu điểm Thực tiễn

### So sánh Ngữ nghĩa

Phát hiện chính xác các trường hợp:
- **Đồng nghĩa:** "Gạo nếp" = "Gạo nếp cái hoa vàng"
- **Chính tả:** "Cà rốt" = "Củ cà rốt"
- **Đa ngôn ngữ:** "Bí đỏ" = "Pumpkin"
- **Chi tiết hóa:** "Hành tây" = "Hành tây tím"

→ Đánh giá F1-Score sát thực tế hơn so với exact matching.

### Cải thiện Knowledge Base

Từ kết quả đánh giá, phát hiện:
- Nguyên liệu cần chuẩn hóa tên gọi
- Đồng nghĩa cần bổ sung vào ontology
- Lỗi dữ liệu trong KB

---

## 📊 Kết quả Mẫu (30 món ăn)

```
INGREDIENT-LEVEL — MICRO-F1 ALL INGREDIENTS
Precision: 91.19% | Recall: 85.23% | F1: 88.11%

CORE INGREDIENTS (importance ≥ 2)
Precision: 61.92% | Recall: 86.28% | F1: 72.10%
```
---

## Các bước tiến hành

### Bước 1: Trích xuất RAG

Chạy notebook `extract_rag_predictions.ipynb`:
- Cấu hình: 30 món, cache file `predictions_cache_v1.json`
- Kết quả: File cache chứa Ground Truth và RAG Prediction

### Bước 2: Đánh giá F1

Chạy notebook `f1-evaluation (1).ipynb`:
- Load model Qwen2.5-3B-Instruct
- Thực hiện semantic alignment cho 30 món
- Xuất `semantic_f1_per_dish.csv` và `semantic_f1_summary.json`

### Bước 3: Phân tích

```python
import pandas as pd
df = pd.read_csv('semantic_f1_per_dish.csv')
print(df[['dish_name', 'f1_all', 'f1_core']].sort_values('f1_all', ascending=False))
```

---

## 📚 Files liên quan

- `popular_dishes_30.json`: Danh sách 30 món test
- `predictions_cache_v1.json`: Cache kết quả RAG
- `extract_rag_predictions.ipynb`: Notebook trích xuất
- `f1-evaluation (1).ipynb`: Notebook đánh giá
- `semantic_f1_per_dish.csv`: Kết quả chi tiết
- `semantic_f1_summary.json`: Tổng hợp metrics

