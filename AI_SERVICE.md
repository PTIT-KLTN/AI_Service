# Sơ đồ cho mục 2.3.6.c. Thiết kế luồng xử lý (bên trong AI Service)

Sơ đồ luồng xử lý tổng quát trong AI Service
(áp dụng cho cả yêu cầu văn bản và hình ảnh)

[START] Yêu cầu phân tích món ăn
        (đã được AI Service nhận)

        |
        v
+----------------------------------+
| Xác định loại yêu cầu            |
|  - VĂN BẢN (text)                |
|  - HÌNH ẢNH (image + metadata)   |
+----------------------------------+
        |                     |
        | (VĂN BẢN)           | (HÌNH ẢNH)
        v                     v

   [TEXT PIPELINE]           [IMAGE PIPELINE]
   - Làm sạch mô tả          - Tải ảnh từ S3
     món ăn / công thức        (S3ImageService)
   - Kiểm tra Guardrails      - Mã hóa ảnh, chuẩn hóa
     đầu vào                    thông tin ảnh
   - Gọi Nova (text)          - Gọi Nova Pro (VLM)
     để trích xuất              để nhận diện món ăn
     món ăn + nguyên liệu       + nguyên liệu từ ảnh

        \                     /
         \                   /
          \                 /
           v               v
+----------------------------------+
| Hợp nhất thông tin ban đầu       |
|  - Tên món ăn (nếu có)           |
|  - Danh sách nguyên liệu thô     |
+----------------------------------+
        |
        v
+-------------------------------------------+
| Gọi BedrockKBService.get_dish_recipe      |
|  - Truy vấn Bedrock Knowledge Base        |
|  - Model Nova Pro + KB (RAG)              |
|  - Thu công thức chuẩn và nguyên liệu gốc |
+-------------------------------------------+
        |
        v
+----------------------------------+
| Chuẩn hóa nguyên liệu            |
|  - IngredientResolver            |
|  - OntologyService: ánh xạ ID,   |
|    nhóm nguyên liệu, tên chuẩn   |
+----------------------------------+
        |
        v
+----------------------------------+
| Chuẩn hóa đơn vị                  |
|  - UnitConverterService           |
|  - Quy đổi đơn vị về chuẩn        |
|    (gram, ml, cái, ...)           |
+----------------------------------+
        |
        v
+---------------------------------------------+
| Phát hiện xung đột & kiểm tra an toàn      |
|  - ConflictDetectionService:                |
|       * tìm cặp nguyên liệu xung đột       |
|       * gợi ý nguyên liệu thay thế         |
|  - ValidationService:                       |
|       * kiểm tra quy tắc nội bộ, dị ứng    |
+---------------------------------------------+
        |
        v
+------------------------------------------+
| Tối ưu giỏ hàng & gợi ý                 |
|  - OptimizedShoppingCartPipeline         |
|  - SuggestionService (ghi chú, gợi ý)    |
+------------------------------------------+
        |
        v
[END] Kết quả trả về (cấu trúc thống nhất):
      - Thông tin món ăn
      - Danh sách nguyên liệu chuẩn hóa
      - Xung đột + gợi ý thay thế (nếu có)
      - Thông tin guardrails / cảnh báo


# 2. Sơ đồ cho mục 2.3.6.e. Thiết kế luồng tương tác giữa AI Service và Main Service

Sơ đồ luồng tương tác giữa Main Service và AI Service
(sử dụng RabbitMQ và worker AI)

Người dùng (Frontend)
        |
        | 1) Gửi HTTP request
        |    - /ai/analysis (text)
        |    - /ai/image-analysis (image)
        v
+----------------------------------------+
| Main Service - Lớp API                 |
|  - Nhận request HTTP                   |
|  - Xác định loại: TEXT / IMAGE         |
|  - Kiểm tra + chuẩn hóa dữ liệu        |
+----------------------------------------+
        |
        | 2) Gửi tác vụ cho bộ điều phối AI
        v
+----------------------------------------+
| Main Service - AIServiceClient         |
|  - Sinh correlation_id                 |
|  - Đóng gói payload JSON               |
|  - Gọi RabbitMQService.send_*_request  |
+----------------------------------------+
        |
        | 3) Đưa message vào hàng đợi AI
        v
+----------------------------+
| RabbitMQ - Request Queue   |
|  - Hàng đợi tác vụ AI      |
+----------------------------+
        |
        | 4) Worker AI nhận yêu cầu
        v
+----------------------------------------+
| AI Service - RabbitMQ Worker           |
|  - Nhận message từ Request Queue       |
|  - Parse payload                       |
|  - Chọn pipeline TEXT / IMAGE          |
+----------------------------------------+
        |
        | 5) Gọi pipeline AI nội bộ
        v
+---------------------------------------------+
| AI Service - Pipeline xử lý nội bộ          |
|  - GuardrailedBedrockClient (Guardrails)    |
|  - BedrockKBService (RAG với KB)           |
|  - IngredientResolver, OntologyService     |
|  - UnitConverterService                    |
|  - ConflictDetectionService, Validation    |
|  - OptimizedShoppingCartPipeline           |
+---------------------------------------------+
        |
        | 6) Trả kết quả về worker
        v
+----------------------------------------+
| AI Service - RabbitMQ Worker           |
|  - Đóng gói kết quả JSON               |
|  - Gắn lại correlation_id              |
|  - Gửi vào Reply/Callback Queue       |
+----------------------------------------+
        |
        | 7) RabbitMQ chuyển tới Main Service
        v
+----------------------------+
| RabbitMQ - Reply Queue     |
+----------------------------+
        |
        | 8) Nhận và ghép kết quả
        v
+----------------------------------------+
| Main Service - RabbitMQService         |
|  - Đọc message từ Reply Queue         |
|  - Tìm future theo correlation_id      |
|  - Gán result và "đánh thức" request  |
+----------------------------------------+
        |
        | 9) Chuẩn hóa response nội bộ
        v
+----------------------------------------+
| Main Service - API                     |
|  - normalize_response()                |
|  - mapping sang domain (dish/cart)     |
+----------------------------------------+
        |
        | 10) Trả HTTP response cho Frontend
        v
Người dùng nhận:
  - Thông tin món ăn
  - Danh sách nguyên liệu đã xử lý
  - Cảnh báo guardrails / xung đột (nếu có)

