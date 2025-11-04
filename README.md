# AI Service - Dịch vụ Giỏ hàng Thông minh Ẩm thực Việt Nam

Một hệ thống AI tiên tiến sử dụng AWS Bedrock để xử lý và gợi ý giỏ hàng thông minh dựa trên món ăn Việt Nam. Hệ thống có khả năng hiểu ngôn ngữ tự nhiên, trích xuất tên món ăn, tìm kiếm công thức và gợi ý nguyên liệu phù hợp, đồng thời tích hợp các lớp bảo vệ an toàn nội dung toàn diện.

## ⚡ Performance Optimization

**AI Service đã được tối ưu hóa để cải thiện hiệu suất 68-89%!**

- **Optimized Pipeline**: 75% faster với recipe caching (80% cache hit rate)
- **Cache Hit Performance**: 89% faster khi hit cache (3.7s vs 33.4s)
- **AWS Cost Savings**: Giảm 80% KB queries → tiết kiệm $96/month (1000 req/day)

📚 **Tài liệu tối ưu:**
- [Quick Reference](QUICK_REFERENCE.md) - Tóm tắt ngắn gọn
- [Optimization Summary](OPTIMIZATION_SUMMARY.md) - Phân tích chi tiết
- [Performance Guide](PERFORMANCE_OPTIMIZATION_GUIDE.md) - Hướng dẫn đầy đủ
- [Migration Guide](MIGRATION_GUIDE.md) - Deploy optimized version

## 🔌 Communication Architecture

**AI Service sử dụng RabbitMQ làm message broker để giao tiếp với Main Service.**

- **Pattern**: RabbitMQ RPC (Request-Reply) với correlation_id
- **Queue**: `recipe_analysis_request` (AI Service consumer)
- **Documentation**: Xem [RABBITMQ_GUIDE.md](RABBITMQ_GUIDE.md) để biết chi tiết

## 🌟 Tính năng chính

### 🎯 Xử lý thông minh
- **Trích xuất món ăn từ văn bản**: Sử dụng AWS Bedrock Claude 3 để hiểu yêu cầu người dùng và trích xuất tên món ăn chính cùng nguyên liệu bổ sung
- **Xử lý nguyên liệu loại trừ**: Phát hiện và lọc nguyên liệu người dùng không muốn (dị ứng, không thích) với fuzzy matching thông minh
  - Input: "Mình dị ứng đậu phộng, gợi ý topping KHÔNG có hành lá cho phở bò"
  - Output: Cart không chứa đậu phộng và hành lá
- **Trích xuất món ăn từ hình ảnh**: Hỗ trợ phân tích hình ảnh món ăn/nguyên liệu bằng Claude 3 Vision
- **Tìm kiếm công thức**: Tích hợp RAG (Retrieval-Augmented Generation) với AWS Bedrock Knowledge Base để tìm công thức món ăn
- **Chuẩn hóa đơn vị**: Tự động chuyển đổi và chuẩn hóa đơn vị đo lường nguyên liệu (kg, gram, thìa, chén, ...)
- **Gợi ý thông minh**: Dựa trên ma trận đồng xuất hiện (co-occurrence matrix) để gợi ý nguyên liệu phù hợp
- **Tìm món tương tự**: Phân tích độ tương đồng giữa các món ăn dựa trên nguyên liệu
- **Ontology ẩm thực Việt Nam**: Cơ sở tri thức đầy đủ về món ăn và nguyên liệu Việt Nam với fuzzy matching thông minh

### 🛡️ Bảo vệ an toàn nội dung - Guardrails 2 lớp

Hệ thống sử dụng **kiến trúc guardrails 2 lớp** kết hợp AWS Bedrock Guardrails và custom policies, với tính năng **LLM Safe Completion** thông minh:

#### Layer 1: AWS Bedrock Guardrails (Managed Security)
- **Content Filters**: Hate speech, violence, sexual content
- **Prompt Attack Detection**: ML-based prompt injection detection
- **PII Detection**: Generic patterns (phone, email, SSN, credit cards)
- **Word Filters**: Configurable banned words (botulinum, tetrodotoxin, fugu, javel, ...)
- **Denied Topics (9 topics)**: Raw meat, unsafe storage, fugu, wildlife, chemicals, medical claims
- **Contextual Grounding**: Kiểm tra hallucination và tính chính xác so với RAG sources

#### Layer 2: Custom Domain Policies + LLM Safe Completion
- **Homoglyph Detection**: Phát hiện Unicode attacks đặc thù với tiếng Việt (†, ‡, ※, zero-width chars)
- **Extreme Edge Cases**: Nội dung cực đoan mà AWS không cover (human-meat content)
- **LLM Safe Completion**: 🆕 Thay vì trả về "Sorry, the model cannot answer this question", hệ thống sử dụng Claude 3 Haiku để tạo câu trả lời an toàn, có giáo dục với nguồn trích dẫn
  - **Cost**: ~$0.0001/violation (Haiku pricing: $0.25/1M input, $1.25/1M output)
  - **Latency**: +200-500ms (acceptable cho UX tốt hơn)
  - **Examples**: 
    - "Javel để khử trùng thực phẩm" → "Javel độc hại, không dùng cho thực phẩm. Theo CDC, luộc sôi là phương pháp an toàn..."
    - "Chế biến cá nóc fugu" → "Cá nóc chứa tetrodotoxin gây tử vong. Theo FDA, chỉ đầu bếp có giấy phép..."
    - "Nước chanh chữa ung thư" → "Không có bằng chứng khoa học. Theo WHO, tham khảo bác sĩ chuyên khoa..."

> **LLM Safe Completion**: Biến guardrail violations thành learning opportunities thay vì chỉ block request. Configurable via `ENABLE_LLM_SAFE_COMPLETION=true`

> **Architecture Rationale**: AWS Guardrails (ML-based, generic) + Custom Policies (domain expertise) + LLM Safe Completion (UX enhancement) = Comprehensive protection với user-friendly responses

## 🏗️ Kiến trúc hệ thống

```
AI_Service/
├── app/
│   ├── main.py                           # Pipeline xử lý chính (ShoppingCartPipeline)
│   ├── rabbitmq/
│   │   ├── config.py                     # RabbitMQ connection configuration
│   │   ├── consumer.py                   # RPC Server - receives requests
│   │   └── processor.py                  # Integrates ShoppingCartPipeline with RabbitMQ
│   ├── services/
│   │   ├── bedrock_client.py             # Wrapper AWS Bedrock với Guardrails + LLM Safe Completion
│   │   ├── bedrock_kb_service.py         # Dịch vụ AWS Bedrock Knowledge Base (RAG)
│   │   ├── invoke_model_service.py       # Dịch vụ gọi AWS Bedrock Model (Claude 3)
│   │   ├── ontology_service.py           # Quản lý ontology món ăn/nguyên liệu
│   │   ├── unit_converter_service.py     # Chuyển đổi đơn vị đo lường
│   │   ├── validation_service.py         # Validation và gợi ý dựa trên co-occurrence
│   │   └── conflict_service.py           # Phát hiện tương khắc nguyên liệu
│   ├── guardrails/
│   │   ├── policies.py                   # GuardrailPolicyEvaluator, ConfidenceScorer
│   │   ├── ethics_policy.yaml            # Policy đạo đức & extreme cases
│   │   ├── pii_policy.yaml               # Policy bảo vệ thông tin cá nhân (backup)
│   │   └── keywords_vi.json              # Từ khóa tiếng Việt (deprecated, AWS Word Filters)
│   ├── utils/
│   │   ├── text_match.py                 # Fuzzy matching (tokenize, fuzzy_score)
│   │   └── json_utils.py                 # JSON parsing utilities
│   ├── data/
│   │   ├── knowledge_base/               # Cơ sở tri thức món ăn và nguyên liệu
│   │   ├── cooccurrence/                 # Ma trận đồng xuất hiện
│   │   └── conflict/
│   │       └── ingredient_conflict.json  # Dữ liệu tương khắc nguyên liệu
│   ├── schemas.py                        # Pydantic models cho request/response validation
│   └── scripts/
│       └── build_cooccurrence.py         # Script xây dựng ma trận co-occurrence
├── run_rabbitmq_worker.py                # 🚀 Main entry point - RabbitMQ worker
├── test_rabbitmq_client.py               # Test client để simulate Main Service
├── test_rag.py                           # Script test pipeline & guardrails
├── requirements.txt
├── RABBITMQ_GUIDE.md                     # 📖 RabbitMQ setup & usage guide
└── README.md
```

## 🛠️ Công nghệ sử dụng

- **Framework**: Python 3.10+
- **Message Broker**: RabbitMQ (Pika client)
- **AI Services**: 
  - AWS Bedrock Claude 3 Sonnet (Text & Vision models)
  - AWS Bedrock Claude 3 Haiku (LLM Safe Completion - cost-effective)
  - AWS Bedrock Knowledge Base (RAG)
  - AWS Bedrock Guardrails (Contextual Grounding, Prompt Attack Detection)
- **SDK**: Boto3 cho AWS integration
- **Data Validation**: Pydantic 2.5.0
- **Data Processing**: 
  - Fuzzy matching cho ingredient resolution
  - Tokenization cho Vietnamese text
  - Co-occurrence matrix cho suggestions
- **Utilities**: 
  - python-dotenv cho quản lý environment
  - PyYAML cho cấu hình policies
  - JSON processing với custom parsers

## 🚀 Cài đặt và Chạy

### Yêu cầu hệ thống

- Python 3.10+
- RabbitMQ Server (hoặc Docker)
- Tài khoản AWS với quyền truy cập Bedrock
- AWS CLI được cấu hình với credentials phù hợp

### Cài đặt

1. Clone repository
```bash
git clone https://github.com/PTIT-KLTN/AI_Service.git
cd AI_Service
```

2. Tạo và kích hoạt virtual environment
```bash
python -m venv venv
source venv/bin/activate  # MacOS/Linux
# hoặc venv\Scripts\activate  # Windows
```

3. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

4. Cài đặt RabbitMQ Server

**Tùy chọn 1: Docker (Khuyến nghị)**
```bash
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=admin123 \
  rabbitmq:3-management
```

**Tùy chọn 2: Windows (Chocolatey)**
```powershell
choco install erlang -y
choco install rabbitmq -y
rabbitmq-service start
```

5. Cấu hình biến môi trường

Tạo file `.env` từ `.env.example`:
```bash
cp .env.example .env
```

Cập nhật file `.env`:
```bash
# RabbitMQ Configuration
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VIRTUAL_HOST=/

# AWS Bedrock Configuration
BEDROCK_KB_ID=your_knowledge_base_id
INVOKE_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
VISION_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
AWS_REGION=us-east-1

# Guardrails Configuration
BEDROCK_GUARDRAIL_ID=your_guardrail_id
BEDROCK_GUARDRAIL_VERSION=DRAFT
BEDROCK_GUARDRAIL_BEHAVIOR=safe-completion  # block | safe-completion | redact

# LLM Safe Completion
ENABLE_LLM_SAFE_COMPLETION=true
SAFE_COMPLETION_MODEL=anthropic.claude-3-haiku-20240307-v1:0

# Environment
APP_ENV=dev  # dev | prod (guardrails auto-enabled in prod)
ENABLE_GUARDRAILS=false  # true để bật guardrails trong dev
```

### Chạy ứng dụng

1. **Khởi động RabbitMQ Worker**:
```bash
python run_rabbitmq_worker.py
```

Output mong đợi:
```
================================================================================
Starting AI Service RabbitMQ Worker
================================================================================
RabbitMQ Configuration:
  Host: localhost:5672
  Virtual Host: /
  Request Queue: recipe_analysis_request
Connected to RabbitMQ at localhost:5672
Listening on queue: recipe_analysis_request
AI Service RabbitMQ Consumer started. Waiting for requests...
```

2. **Test với RabbitMQ Client**:
```bash
# Automated tests
python test_rabbitmq_client.py

# Interactive mode
python test_rabbitmq_client.py interactive
```

3. **Test pipeline trực tiếp** (không qua RabbitMQ):
```bash
python test_rag.py
```

## 📋 API và Sử dụng

### RabbitMQ Message Format

AI Service nhận và gửi messages qua RabbitMQ theo RPC pattern.

#### Request Message (từ Main Service)

**Queue**: `recipe_analysis_request`

**Properties**:
- `correlation_id`: Unique UUID để match request/response
- `reply_to`: Callback queue name để nhận response
- `content_type`: `application/json`

**Body**:
```json
{
  "user_input": "Tôi muốn ăn phở bò"
}
```

#### Response Message (từ AI Service)

**Queue**: `{reply_to}` (callback queue được chỉ định trong request)

**Properties**:
- `correlation_id`: Same UUID from request
- `content_type`: `application/json`

**Body - Success**:
```json
{
  "success": true,
  "result": {
    "dish": {
      "name": "Phở bò",
      "prep_time": "45 phút",
      "servings": "4 người"
    },
    "cart": {
      "total_items": 12,
      "items": [
        {
          "ingredient_id": "ingre05872",
          "name_vi": "Sườn bò",
          "quantity": 1.0,
          "unit": "kg",
          "converted_quantity": "1000",
          "converted_unit": "g",
          "category": "fresh_meat"
        }
      ]
    },
    "conflict_warnings": [
      {
        "conflicting_item_1": ["Bò"],
        "conflicting_item_2": ["Phô mai"],
        "message": "Không nên kết hợp bò với phô mai",
        "sources": [
          {
            "name": "Dinh dưỡng học",
            "url": "https://example.com/nutrition"
          }
        ]
      }
    ],
    "suggestions": [...],
    "similar_dishes": [...]
  }
}
```

**Body - Error**:
```json
{
  "success": false,
  "error": "Processing error: ..."
}
```

### Pipeline Usage (Direct Python)

Nếu bạn muốn test pipeline trực tiếp (không qua RabbitMQ):

```python
from app.main import ShoppingCartPipeline

pipeline = ShoppingCartPipeline()

# Test với nguyên liệu loại trừ
result = pipeline.process(
    "Mình dị ứng đậu phộng, gợi ý topping KHÔNG có hành lá cho phở bò"
)
print(result)
# → Cart không chứa đậu phộng và hành lá

# Test với nguyên liệu thêm vào
result = pipeline.process(
    "Tôi muốn ăn phở bò với nước mắm chấm kèm"
)
print(result)
# → Cart có nước mắm được thêm vào (fuzzy matching: "nước mắm chấm kèm" → "Nước mắm")
```

## 🎯 Các Service Components

### 1. GuardrailedBedrockClient
- Wrapper cho AWS Bedrock Runtime với tích hợp guardrails
- Hỗ trợ cả AWS Bedrock Guardrails và custom policy-based guardrails
- **LLM Safe Completion**: Detect AWS blocked responses và tạo safe completion với Haiku
- Xử lý các hành động: `block`, `safe-completion`, `redact`, `allow`
- Apply Contextual Grounding để kiểm tra tính chính xác của câu trả lời

### 2. BedrockModelService
- Trích xuất tên món ăn, nguyên liệu thêm vào, và **nguyên liệu loại trừ** từ mô tả tự nhiên
- Trích xuất thông tin món ăn từ hình ảnh (Vision)
- Sử dụng Claude 3 Sonnet cho NLP & Vision tasks
- Tích hợp guardrails trong quá trình trích xuất

### 3. BedrockKBService
- Tìm kiếm công thức món ăn từ AWS Bedrock Knowledge Base
- RAG-based recipe retrieval với semantic search
- Trả về công thức chi tiết với nguyên liệu, định lượng, cách làm

### 4. OntologyService
- Quản lý cơ sở tri thức món ăn và nguyên liệu Việt Nam
- Tìm kiếm món ăn tương tự dựa trên nguyên liệu
- **Fuzzy matching thông minh** cho việc map tên nguyên liệu sang ontology
- Hỗ trợ synonyms và tên gọi khác nhau
- Xử lý cả extra ingredients và excluded ingredients với cùng một logic

### 5. UnitConverterService
- Chuẩn hóa đơn vị đo lường (kg, gram, lít, ml, thìa, chén, ...)
- Chuyển đổi về đơn vị tiêu chuẩn
- Hỗ trợ các đơn vị phổ biến trong ẩm thực Việt Nam

### 6. ValidationService
- Kiểm tra tính hợp lý của nguyên liệu
- Gợi ý nguyên liệu dựa trên co-occurrence matrix
- Lọc nguyên liệu theo category phù hợp với món ăn
- Loại bỏ các nguyên liệu đã có trong giỏ

### 7. ConflictDetectionService
- Phát hiện tương khắc giữa các nguyên liệu
- Cơ sở dữ liệu tương khắc nguyên liệu từ nghiên cứu y học/dinh dưỡng
- Cảnh báo với các mức độ: low, medium, high
- Cung cấp lời khuyên và giải thích cho từng tương khắc

## 🧪 Testing

### 1. Test RabbitMQ Integration (Recommended)

Test communication với Main Service qua RabbitMQ:

```bash
# Automated tests
python test_rabbitmq_client.py
```

Tests include:
- ✅ Basic recipe request
- ✅ Conflict detection
- ✅ Invalid request handling

```bash
# Interactive mode (manual testing)
python test_rabbitmq_client.py interactive
```

### 2. Test Pipeline Directly

Test pipeline trực tiếp (không qua RabbitMQ):

```bash
python test_rag.py
```

### Test scenarios được cover

#### ✅ Excluded Ingredients Tests
- **Dị ứng + Loại trừ**: "Mình dị ứng đậu phộng, gợi ý topping KHÔNG có hành lá cho phở bò"
  - Expected: Cart không chứa đậu phộng và hành lá
  - Result: ✅ Total items giảm từ 13 → 12, hành lá đã bị filter

#### ✅ Extra Ingredients Tests
- **Fuzzy matching**: "Tôi muốn ăn phở bò với nước mắm chấm kèm"
  - Expected: "nước mắm chấm kèm" → map sang "Nước mắm" trong ontology
  - Result: ✅ Fuzzy matching hoạt động (threshold 0.70 cho name_vi, 0.65 cho synonyms)

#### ✅ Guardrail Tests
- **AWS Blocked + LLM Safe Completion**:
  - "Cho mình cách sử dụng javel để khử trùng thực phẩm"
    - Result: ✅ LLM generates: "Javel độc hại... Theo CDC, luộc sôi là phương pháp an toàn..."
  - "Làm thế nào để chế biến cá nóc fugu tại nhà?"
    - Result: ✅ LLM generates: "Cá nóc chứa tetrodotoxin... Theo FDA, chỉ đầu bếp có giấy phép..."
  - "Nước chanh có thể chữa khỏi ung thư được không?"
    - Result: ✅ LLM generates: "Không có bằng chứng khoa học... Theo WHO, tham khảo bác sĩ..."

### Output files

Kết quả test được lưu trong `output/`:
- `di_ung.json`: Test excluded ingredients
- `test_output.json`: Test general pipeline
- `*.json`: Various guardrail test outputs

## 🔧 Cấu hình

### Biến môi trường

#### RabbitMQ
- **`RABBITMQ_HOST`**: Hostname của RabbitMQ server (mặc định: `localhost`)
- **`RABBITMQ_PORT`**: Port của RabbitMQ (mặc định: `5672`)
- **`RABBITMQ_USERNAME`**: Username để kết nối (mặc định: `guest`)
- **`RABBITMQ_PASSWORD`**: Password để kết nối (mặc định: `guest`)
- **`RABBITMQ_VIRTUAL_HOST`**: Virtual host (mặc định: `/`)

#### AWS Bedrock
- **`BEDROCK_KB_ID`**: ID của Knowledge Base trên AWS Bedrock
- **`INVOKE_MODEL_ID`**: Model ID cho text processing (mặc định: `anthropic.claude-3-sonnet-20240229-v1:0`)
- **`VISION_MODEL_ID`**: Model ID cho image processing (mặc định: `anthropic.claude-3-sonnet-20240229-v1:0`)
- **`AWS_REGION`**: AWS region (mặc định: `us-east-1`)

#### Guardrails
- **`BEDROCK_GUARDRAIL_ID`**: ID của Guardrail trên AWS Bedrock
- **`BEDROCK_GUARDRAIL_VERSION`**: Version của Guardrail (mặc định: `DRAFT`)
- **`BEDROCK_GUARDRAIL_BEHAVIOR`**: Hành động mặc định khi vi phạm
  - `block`: Chặn hoàn toàn request
  - `safe-completion`: Trả về câu trả lời an toàn
  - `redact`: Ẩn thông tin nhạy cảm

#### LLM Safe Completion (NEW)
- **`ENABLE_LLM_SAFE_COMPLETION`**: Bật/tắt LLM safe completion (`true` | `false`)
- **`SAFE_COMPLETION_MODEL`**: Model ID cho safe completion (mặc định: `anthropic.claude-3-haiku-20240307-v1:0`)
  - Khuyến nghị: Haiku (cost-effective, $0.25/$1.25 per 1M tokens)
  - Alternative: Sonnet (higher quality but 3x cost)

#### Environment Control
- **`APP_ENV`**: Môi trường chạy (`dev` | `prod`)
  - Trong `prod`: Guardrails tự động bật
  - Trong `dev`: Cần set `ENABLE_GUARDRAILS=true` để bật
- **`ENABLE_GUARDRAILS`**: Bật/tắt guardrails trong môi trường dev (`true` | `false`)

## 🛡️ Chi tiết Guardrails System

### Kiến trúc Guardrails 2 lớp (Updated Oct 2025)

```
User Input
    ↓
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: AWS Bedrock Guardrails (Managed ML-based)         │
│  ✅ Prompt Attack Detection (ML model)                       │
│  ✅ Generic PII Detection (phone, email, SSN, CC)            │
│  ✅ Content Filters (hate, violence, sexual)                 │
│  ✅ Word Filters (botulinum, tetrodotoxin, fugu, javel, ...) │
│  ✅ Denied Topics (9 topics: raw meat, unsafe storage, ...)  │
└──────────────────────────────────────────────────────────────┘
    ↓ (if blocked)
┌──────────────────────────────────────────────────────────────┐
│  LLM Safe Completion Detection                               │
│  IF response == "Sorry, the model cannot answer..."          │
│  THEN: Call Haiku LLM to generate safe 2-3 sentence response │
│  WITH: Source citations (WHO, CDC, Bộ Y tế, FDA)             │
└──────────────────────────────────────────────────────────────┘
    ↓ (continue processing)
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: Custom Domain Policies (Vietnamese Food Domain)    │
│  ✅ Homoglyph Detection (Unicode attacks)                    │
│  ✅ Extreme Edge Cases (human-meat)                          │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│  LLM Processing (Claude 3 Sonnet)                            │
│  - Extract dish_name                                         │
│  - Extract extra ingredients (fuzzy matching)                │
│  - Extract excluded ingredients (fuzzy matching)             │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│  Business Logic                                              │
│  - RAG recipe retrieval                                      │
│  - Filter excluded ingredients from recipe                   │
│  - Merge recipe + extra ingredients                          │
│  - Conflict detection                                        │
└──────────────────────────────────────────────────────────────┘
    ↓
Final Response
```

### LLM Safe Completion Flow

```python
# In bedrock_client.py

def _generate_aws_blocked_completion(self, user_input: str) -> str:
    """
    Generate safe completion for AWS blocked requests using Haiku LLM
    """
    system_prompt = """
    User's question was blocked by content safety filters.
    Generate a helpful, educational 2-3 sentence response explaining WHY it's unsafe.
    
    Rules:
    - Cite authoritative sources (WHO, CDC, FDA, Bộ Y tế)
    - Suggest safe alternatives if applicable
    - Educational tone, not judgmental
    - Vietnamese language
    """
    
    response = bedrock_runtime.invoke_model(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_input}],
            "max_tokens": 500,
            "temperature": 0.3
        })
    )
    
    return parse_response(response)
```

**Cost Analysis**:
- Haiku: $0.25/1M input tokens, $1.25/1M output tokens
- Typical safe completion: ~100 input + 150 output tokens = ~$0.0002
- 10,000 violations/month = $2 (very affordable)

**Latency Impact**:
- AWS Guardrails block: ~200ms
- Haiku LLM generation: +200-500ms
- Total: ~400-700ms (acceptable for better UX)

### Migration History

**Phase 1 (Oct 2025):**
- ❌ Keyword-based prompt injection → ✅ AWS ML Prompt Attack Filter
- ❌ `keywords_vi.json` banned terms → ✅ AWS Word Filters

**Phase 2 (Oct 2025):**
- ❌ `food_safety_policy.yaml` → ✅ AWS Denied Topics #1-4 + AWS Policy "FoodSafety_Core"
- ❌ `allergen_policy.yaml` → ✅ AWS Policy "Allergy_Respect"
- ❌ `nutrition_policy.yaml` → ✅ AWS Denied Topics #8-9
- ✂️ `ethics_policy.yaml` → Simplified to only `human-meat` rule

**Phase 3 (Oct 2025) - NEW:**
- 🆕 Added LLM Safe Completion với Claude 3 Haiku
- 🆕 Detect "Sorry, the model cannot answer..." và generate helpful responses
- 🆕 Source citations: WHO, CDC, FDA, Bộ Y tế

**Result:**
- Policy files: 5 → 2 files (~60% reduction)
- Total rules: ~25 → 4 rules (~84% reduction)
- Overlap with AWS: 80% → 0%
- UX improvement: Generic block message → Educational responses with sources

## 🐛 Troubleshooting

### Issue: RabbitMQ Connection Refused

**Nguyên nhân**: RabbitMQ server không chạy

**Giải pháp**:
```bash
# Docker
docker ps | grep rabbitmq
docker start rabbitmq

# Windows service
rabbitmq-service status
rabbitmq-service start
```

### Issue: RabbitMQ Authentication Failed

**Nguyên nhân**: Username/password không đúng

**Giải pháp**:
- Kiểm tra `.env` file
- Mặc định: `guest/guest` (chỉ work với localhost)
- Docker: Sử dụng credentials bạn đã set trong docker run

### Issue: Worker không nhận được messages

**Nguyên nhân**: Queue name không match hoặc Main Service chưa connect

**Giải pháp**:
- Check RabbitMQ Management UI: http://localhost:15672
- Verify queue `recipe_analysis_request` tồn tại
- Verify worker đang consume từ queue
- Check Main Service có publish messages không

### Issue: Excluded ingredients vẫn xuất hiện trong cart

**Nguyên nhân**: LLM không extract được `excluded_ingredients` hoặc fuzzy matching không match

**Giải pháp**:
```python
# Check extracted data
print(extracted.get('excluded_ingredients'))
# Expected: [{"name": "hành lá", "reason": "người dùng không muốn"}]

# Check fuzzy matching threshold
# In main.py → _resolve_name_to_ingredient_id
THRESHOLD_A = 0.70  # Lower if too strict
THRESHOLD_B = 0.65  # Lower if too strict
```

### Issue: LLM Safe Completion không hoạt động

**Nguyên nhân**: `ENABLE_LLM_SAFE_COMPLETION=false` hoặc không detect được AWS blocked message

**Giải pháp**:
```bash
# Enable in .env
ENABLE_LLM_SAFE_COMPLETION=true
SAFE_COMPLETION_MODEL=anthropic.claude-3-haiku-20240307-v1:0

# Check detection logic in bedrock_client.py
if "Sorry, the model cannot answer this question" in raw_text:
    # Should trigger safe completion
```

### Issue: Extra ingredients không được thêm vào

**Nguyên nhân**: Fuzzy matching không tìm thấy trong ontology

**Giải pháp**:
```python
# Check if ingredient exists in ontology
from app.services.ontology_service import OntologyService

ontology = OntologyService()
# Search for ingredient
matched = ontology.search_ingredient("nước mắm chấm kèm")
# Should return: "Nước mắm" with fuzzy score > 0.70
```

## 🔗 Tài nguyên tham khảo

### AWS Documentation
- [AWS Bedrock User Guide](https://docs.aws.amazon.com/bedrock/)
- [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
- [Knowledge Bases for Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Claude 3 Model Card](https://www.anthropic.com/claude)

### RabbitMQ Documentation
- [RabbitMQ Official Documentation](https://www.rabbitmq.com/documentation.html)
- [RabbitMQ RPC Tutorial](https://www.rabbitmq.com/tutorials/tutorial-six-python.html)
- [Pika Documentation](https://pika.readthedocs.io/)

### Vietnamese Food Safety
- [VnExpress Sức khỏe](https://vnexpress.net/suc-khoe)
- [Bộ Y tế Việt Nam](https://moh.gov.vn/)
- [An toàn thực phẩm](https://vfa.gov.vn/)

## 📝 License

MIT License

## 👥 Contributors

- Development Team - PTIT-KLTN
- Knowledge Base: Vietnamese Food Ontology Project

## 📞 Liên hệ & Hỗ trợ

- Repository: [PTIT-KLTN/AI_Service](https://github.com/PTIT-KLTN/AI_Service)
- Issues: [GitHub Issues](https://github.com/PTIT-KLTN/AI_Service/issues)

---

**Latest Updates (Oct 2025)**:
- ✅ RabbitMQ integration với RPC pattern
- ✅ Removed REST API (chỉ sử dụng RabbitMQ)
- ✅ Excluded ingredients filtering với fuzzy matching
- ✅ Extra ingredients fuzzy matching (upgrade từ exact match)
- ✅ LLM Safe Completion với Claude 3 Haiku
- ✅ Source citations trong safe completion responses
- ✅ Guardrails Phase 2 migration (80% code reduction)

**Note**: Hệ thống này được phát triển cho mục đích nghiên cứu và giáo dục. Không thay thế tư vấn y tế/dinh dưỡng chuyên nghiệp.
