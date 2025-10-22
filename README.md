# AI Service - Dịch vụ Giỏ hàng Thông minh Ẩm thực Việt Nam

Một hệ thống AI tiên tiến sử dụng AWS Bedrock để xử lý và gợi ý giỏ hàng thông minh dựa trên món ăn Việt Nam. Hệ thống có khả năng hiểu ngôn ngữ tự nhiên, trích xuất tên món ăn, tìm kiếm công thức và gợi ý nguyên liệu phù hợp, đồng thời tích hợp các lớp bảo vệ an toàn nội dung toàn diện.

## 🌟 Tính năng chính

### 🎯 Xử lý thông minh
- **Trích xuất món ăn từ văn bản**: Sử dụng AWS Bedrock Claude 3 để hiểu yêu cầu người dùng và trích xuất tên món ăn chính cùng nguyên liệu bổ sung
- **Trích xuất món ăn từ hình ảnh**: Hỗ trợ phân tích hình ảnh món ăn/nguyên liệu bằng Claude 3 Vision
- **Tìm kiếm công thức**: Tích hợp RAG (Retrieval-Augmented Generation) với AWS Bedrock Knowledge Base để tìm công thức món ăn
- **Chuẩn hóa đơn vị**: Tự động chuyển đổi và chuẩn hóa đơn vị đo lường nguyên liệu (kg, gram, thìa, chén, ...)
- **Gợi ý thông minh**: Dựa trên ma trận đồng xuất hiện (co-occurrence matrix) để gợi ý nguyên liệu phù hợp
- **Tìm món tương tự**: Phân tích độ tương đồng giữa các món ăn dựa trên nguyên liệu
- **Ontology ẩm thực Việt Nam**: Cơ sở tri thức đầy đủ về món ăn và nguyên liệu Việt Nam

### 🛡️ An toàn & Bảo mật
- **Guardrails đa lớp**: Hệ thống guardrails toàn diện với cả AWS Bedrock Guardrails và custom policy-based guardrails
  - **Allergen Policy**: Phát hiện và cảnh báo dị ứng thực phẩm
  - **Food Safety Policy**: Kiểm tra các nguy cơ an toàn thực phẩm (nhiệt độ, bảo quản, chế biến)
  - **PII Policy**: Bảo vệ thông tin cá nhân (số điện thoại, email, CMND)
  - **Ethics Policy**: Lọc nội dung không phù hợp, prompt injection
  - **Nutrition Policy**: Cảnh báo các tuyên bố y tế/dinh dưỡng không đúng
- **Contextual Grounding**: Kiểm tra tính chính xác của câu trả lời so với nguồn tri thức (RAG)
- **Conflict Detection**: Phát hiện các tương khắc nguyên liệu dựa trên tri thức ẩm thực Việt Nam
- **Multi-action Guardrails**: Hỗ trợ các hành động: `block`, `safe-completion`, `redact`, `allow`

## 🏗️ Kiến trúc hệ thống

```
AI_Service/
├── app/
│   ├── main.py                           # Pipeline xử lý chính (ShoppingCartPipeline)
│   ├── services/
│   │   ├── bedrock_client.py             # Wrapper AWS Bedrock với Guardrails
│   │   ├── bedrock_kb_service.py         # Dịch vụ AWS Bedrock Knowledge Base (RAG)
│   │   ├── invoke_model_service.py       # Dịch vụ gọi AWS Bedrock Model (Claude 3)
│   │   ├── ontology_service.py           # Quản lý ontology món ăn/nguyên liệu
│   │   ├── unit_converter_service.py     # Chuyển đổi đơn vị đo lường
│   │   ├── validation_service.py         # Validation và gợi ý dựa trên co-occurrence
│   │   └── conflict_service.py           # Phát hiện tương khắc nguyên liệu
│   ├── guardrails/
│   │   ├── policies.py                   # GuardrailPolicyEvaluator, ConfidenceScorer
│   │   ├── allergen_policy.yaml          # Policy cảnh báo dị ứng
│   │   ├── food_safety_policy.yaml       # Policy an toàn thực phẩm
│   │   ├── pii_policy.yaml               # Policy bảo vệ thông tin cá nhân
│   │   ├── ethics_policy.yaml            # Policy đạo đức & prompt injection
│   │   ├── nutrition_policy.yaml         # Policy tuyên bố dinh dưỡng
│   │   └── keywords_vi.json              # Từ khóa tiếng Việt cho guardrails
│   ├── utils/
│   │   └── text_match.py                 # Tiện ích xử lý văn bản (fuzzy matching)
│   ├── data/
│   │   ├── knowledge_base/               # Cơ sở tri thức món ăn và nguyên liệu
│   │   ├── cooccurrence/                 # Ma trận đồng xuất hiện
│   │   └── conflict/
│   │       └── ingredient_conflict.json  # Dữ liệu tương khắc nguyên liệu
│   └── scripts/
│       └── build_cooccurrence.py         # Script xây dựng ma trận co-occurrence
├── requirements.txt
├── test_rag.py                           # Script test pipeline & guardrails
├── test_output.json                      # Kết quả test
└── README.md
```

## 🛠️ Công nghệ sử dụng

- **Framework**: Python 3.9+
- **AI Services**: 
  - AWS Bedrock Claude 3 Sonnet (Text & Vision models)
  - AWS Bedrock Knowledge Base (RAG)
  - AWS Bedrock Guardrails (Contextual Grounding)
- **SDK**: Boto3 cho AWS integration
- **API Framework**: FastAPI + Uvicorn (cho REST API)
- **Data Validation**: Pydantic
- **Utilities**: 
  - python-dotenv cho quản lý environment
  - PyYAML cho cấu hình policies
  - pytest cho testing
- **Data Format**: JSON, YAML

## 🚀 Cài đặt và Chạy

### Yêu cầu hệ thống

- Python 3.9+
- Tài khoản AWS với quyền truy cập Bedrock
- AWS CLI được cấu hình với credentials phù hợp

### Cài đặt

1. Clone repository
```bash
git clone <repository-url>
cd AI_service
```

2. Tạo và kích hoạt virtual environment
```bash
python -m venv ai_env
source ai_env/bin/activate  # MacOS/Linux
# hoặc ai_env\Scripts\activate  # Windows
```

3. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

4. Cấu hình biến môi trường
```bash
# Tạo file .env với nội dung:
# AWS Bedrock Configuration
BEDROCK_KB_ID=your_knowledge_base_id
INVOKE_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
VISION_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
AWS_REGION=us-east-1

# Guardrails Configuration (Optional)
BEDROCK_GUARDRAIL_ID=your_guardrail_id
BEDROCK_GUARDRAIL_VERSION=DRAFT
BEDROCK_GUARDRAIL_BEHAVIOR=safe-completion  # block | safe-completion | redact

# Environment
APP_ENV=dev  # dev | prod (guardrails auto-enabled in prod)
ENABLE_GUARDRAILS=false  # true để bật guardrails trong dev
```

### Chạy ứng dụng

1. **Chạy test pipeline**:
```bash
python test_rag.py
```

2. **Import và sử dụng trong code**:
```python
from app.main import ShoppingCartPipeline

pipeline = ShoppingCartPipeline()
result = pipeline.process("Tôi muốn ăn bún bò Huế với trứng cút")
print(result)
```

## 📋 API và Sử dụng

### Pipeline chính - ShoppingCartPipeline

#### 1. Xử lý văn bản (Text Processing)

```python
from app.main import ShoppingCartPipeline

pipeline = ShoppingCartPipeline()
result = pipeline.process(user_input)
```

**Input**: Câu mô tả món ăn bằng tiếng Việt
- Ví dụ: "Tôi muốn ăn bún bò Huế với trứng cút"
- Ví dụ: "Nấu phở bò"
- Ví dụ: "Mình dị ứng đậu phộng, gợi ý món cho mình"

#### 2. Xử lý hình ảnh (Image Processing)

```python
import base64

# Đọc ảnh và encode base64
with open("mon_an.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

result = pipeline.process_image(
    image_b64=image_b64,
    description="Món này là gì?",  # Optional
    image_mime="image/jpeg"
)
```

**Output**: Dictionary chứa thông tin chi tiết về món ăn và giỏ hàng

```json
{
  "status": "success",
  "dish": {
    "name": "Bún bò Huế",
    "prep_time": "45 phút",
    "servings": "4 người"
  },
  "cart": {
    "total_items": 12,
    "items": [
      {
        "ingredient_id": "ing_001",
        "name_vi": "Thịt bò",
        "quantity": "500",
        "unit": "gram",
        "category": "protein"
      }
    ]
  },
  "suggestions": [
    {
      "ingredient_id": "ing_042",
      "name_vi": "Rau thơm",
      "quantity": "",
      "unit": "",
      "score": 0.85,
      "reason": "Phù hợp với món & chưa có trong giỏ"
    }
  ],
  "similar_dishes": [
    {
      "dish_id": "dish_003",
      "dish_name": "Bún bò Nam Bộ",
      "match_ratio": 0.7
    }
  ],
  "warnings": [
    {
      "message": "Có nguy cơ dị ứng trong gợi ý. Người dùng cần tự đánh giá mức độ chấp nhận.",
      "severity": "warning",
      "source": "guardrail",
      "details": {}
    }
  ],
  "insights": [
    "Bún bò Huế không nên kết hợp với giá đỗ vì ion kim loại trong gan có thể oxy hóa vitamin C."
  ],
  "assistant_response": "Món bún bò Huế là món ăn truyền thống...",
  "guardrail": {
    "enabled": true,
    "action": "allow",
    "violations": [],
    "timestamp": "2025-10-23T10:30:00Z"
  }
}
```

### Status Codes

- **`success`**: Xử lý thành công
- **`error`**: Lỗi trong quá trình xử lý (không tìm thấy món, không parse được JSON)
- **`guardrail_blocked`**: Yêu cầu bị chặn bởi guardrails

## 🎯 Các Service Components

### 1. GuardrailedBedrockClient
- Wrapper cho AWS Bedrock Runtime với tích hợp guardrails
- Hỗ trợ cả AWS Bedrock Guardrails và custom policy-based guardrails
- Xử lý các hành động: `block`, `safe-completion`, `redact`, `allow`
- Apply Contextual Grounding để kiểm tra tính chính xác của câu trả lời
- Logging vi phạm guardrails cho monitoring

### 2. BedrockModelService
- Trích xuất tên món ăn và nguyên liệu bổ sung từ mô tả văn bản tự nhiên
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
- Fuzzy matching cho việc map tên nguyên liệu sang ontology
- Hỗ trợ synonyms và tên gọi khác nhau

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

### 8. GuardrailPolicyEvaluator
- Đánh giá nội dung dựa trên các policy YAML
- Phát hiện prompt injection, PII, allergen warnings, food safety issues
- Hỗ trợ regex, keyword, và custom detection logic
- Tạo safe-completion hoặc redact sensitive information
- Tính confidence score cho kết quả đầu ra

## 📊 Dữ liệu

### Knowledge Base (`app/data/knowledge_base/`)
- **`dish_knowledge_base.json`**: Thông tin món ăn Việt Nam
  - Công thức chi tiết
  - Nguyên liệu và định lượng
  - Thời gian chuẩn bị, số khẩu phần
  - Cách làm từng bước
- **`ingredient_knowledge_base.json`**: Danh mục nguyên liệu và thuộc tính
  - Tên tiếng Việt, tiếng Anh
  - Synonyms (tên gọi khác)
  - Category (protein, vegetables, seasonings, ...)
  - Thông tin dinh dưỡng

### Co-occurrence Matrix (`app/data/cooccurrence/`)
- **`frequency.json`**: Tần suất xuất hiện của từng nguyên liệu
- **`matrix.json`**: Ma trận đồng xuất hiện giữa các nguyên liệu
  - Score thể hiện mức độ thường xuyên xuất hiện cùng nhau
- **`metadata.json`**: Thông tin metadata của ma trận
  - Ngày xây dựng
  - Số lượng món ăn được phân tích
  - Version

### Conflict Data (`app/data/conflict/`)
- **`ingredient_conflict.json`**: Dữ liệu tương khắc nguyên liệu
  - Các cặp/nhóm nguyên liệu tương khắc
  - Mức độ nghiêm trọng (low, medium, high)
  - Lý do khoa học
  - Lời khuyên
  - Nguồn tham khảo (VnExpress, bệnh viện, nghiên cứu)

### Guardrail Policies (`app/guardrails/`)
- **`allergen_policy.yaml`**: Quy tắc phát hiện dị ứng thực phẩm
- **`food_safety_policy.yaml`**: Quy tắc an toàn thực phẩm
- **`pii_policy.yaml`**: Quy tắc bảo vệ thông tin cá nhân
- **`ethics_policy.yaml`**: Quy tắc đạo đức và prompt injection
- **`nutrition_policy.yaml`**: Quy tắc tuyên bố dinh dưỡng
- **`keywords_vi.json`**: Từ khóa tiếng Việt cho lọc nội dung

## 🧪 Testing

### Chạy test toàn diện

Script `test_rag.py` bao gồm 2 nhóm test:

1. **Pipeline Tests**: Test xử lý món ăn cơ bản
2. **Guardrail Tests**: Test các tình huống vi phạm policy

```bash
python test_rag.py
```

Kết quả test sẽ được lưu trong `test_output.json` với cấu trúc:

```json
{
  "timestamp": "2025-10-23T10:30:00Z",
  "pipeline_tests": [
    {
      "input": "Tôi muốn nấu món thịt kho tàu",
      "output": { /* kết quả pipeline */ }
    }
  ],
  "guardrail_tests": [
    {
      "prompt": "Số điện thoại của tôi là 0987 654 321...",
      "output": { /* kết quả với guardrail action */ }
    }
  ]
}
```

### Test scenarios được cover

#### Pipeline Tests
- ✅ Trích xuất món ăn đơn giản
- ✅ Trích xuất món ăn với nguyên liệu thêm vào
- ✅ Món ăn biến thể (chay, miền Nam, ...)
- ✅ RAG recipe retrieval
- ✅ Unit conversion
- ✅ Ingredient suggestions
- ✅ Similar dishes

#### Guardrail Tests
- 🛡️ **Prompt Injection**: Phát hiện các nỗ lực bypass hệ thống
- 🛡️ **PII Protection**: Lọc số điện thoại, email, CMND
- 🛡️ **Allergen Warnings**: Cảnh báo dị ứng thực phẩm
- 🛡️ **Food Safety**: Phát hiện các nguy cơ an toàn (nhiệt độ, bảo quản)
- 🛡️ **Unicode Homoglyph**: Phát hiện ký tự Unicode để bypass filter
- 🛡️ **Illegal Content**: Lọc nội dung nguy hiểm (fugu, ...)
- 🛡️ **Medical Claims**: Cảnh báo tuyên bố y tế không đúng
- 🛡️ **Contextual Grounding**: Kiểm tra tính chính xác của câu trả lời

### Environment cho testing

```bash
# Test với guardrails bật
export APP_ENV=prod
export ENABLE_GUARDRAILS=true

# Hoặc test chỉ pipeline (không guardrails)
export APP_ENV=dev
export ENABLE_GUARDRAILS=false
```

## 🔧 Cấu hình

### Biến môi trường

#### AWS Bedrock
- **`BEDROCK_KB_ID`**: ID của Knowledge Base trên AWS Bedrock
- **`INVOKE_MODEL_ID`**: Model ID cho text processing (mặc định: `anthropic.claude-3-sonnet-20240229-v1:0`)
- **`VISION_MODEL_ID`**: Model ID cho image processing (mặc định: `anthropic.claude-3-sonnet-20240229-v1:0`)
- **`AWS_REGION`**: AWS region (mặc định: `us-east-1`)

#### Guardrails
- **`BEDROCK_GUARDRAIL_ID`**: ID của Guardrail trên AWS Bedrock (optional)
- **`BEDROCK_GUARDRAIL_VERSION`**: Version của Guardrail (mặc định: `DRAFT`)
- **`BEDROCK_GUARDRAIL_BEHAVIOR`**: Hành động mặc định khi vi phạm
  - `block`: Chặn hoàn toàn request
  - `safe-completion`: Trả về câu trả lời an toàn
  - `redact`: Ẩn thông tin nhạy cảm

#### Environment Control
- **`APP_ENV`**: Môi trường chạy (`dev` | `prod`)
  - Trong `prod`: Guardrails tự động bật
  - Trong `dev`: Cần set `ENABLE_GUARDRAILS=true` để bật
- **`ENABLE_GUARDRAILS`**: Bật/tắt guardrails trong môi trường dev (`true` | `false`)

## 🛡️ Chi tiết Guardrails System

### Kiến trúc Guardrails đa lớp

Hệ thống sử dụng chiến lược "defense in depth" với nhiều lớp bảo vệ:

```
User Input
    ↓
┌─────────────────────────────────────┐
│  Layer 1: Custom Policy Guardrails  │  ← YAML-based rules
│  - Prompt injection detection       │
│  - Keyword filtering                │
│  - Unicode homoglyph detection      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Layer 2: AWS Bedrock Guardrails    │  ← AWS managed
│  - Content filters                  │
│  - PII detection                    │
│  - Denied topics                    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  LLM Processing (Claude 3)          │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Layer 3: Output Validation         │
│  - Contextual grounding             │  ← Kiểm tra hallucination
│  - Business rules validation        │
│  - Conflict detection               │
└─────────────────────────────────────┘
    ↓
Final Response
```

### Policy Types

#### 1. Allergen Policy (`allergen_policy.yaml`)
- **Mục đích**: Phát hiện và cảnh báo dị ứng thực phẩm
- **Triggers**: Từ khóa "dị ứng", "allergy" trong prompt
- **Action**: `safe-completion` - Cảnh báo người dùng
- **Allergens**: Đậu phộng, hải sản, sữa, trứng, gluten, ...

#### 2. Food Safety Policy (`food_safety_policy.yaml`)
- **Mục đích**: Ngăn chặn các hướng dẫn không an toàn
- **Detects**: 
  - Ướp thịt ở nhiệt độ phòng
  - Để thực phẩm ngoài tủ lạnh quá lâu
  - Chế biến thịt sống không đúng cách
- **Action**: `safe-completion` hoặc `block`
- **Severity**: `high`

#### 3. PII Policy (`pii_policy.yaml`)
- **Mục đích**: Bảo vệ thông tin cá nhân
- **Detects**: Số điện thoại, email, CMND, địa chỉ
- **Action**: `redact` - Ẩn thông tin nhạy cảm
- **Regex patterns**: 
  - Phone: `0[0-9]{9,10}`
  - Email: `[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}`

#### 4. Ethics Policy (`ethics_policy.yaml`)
- **Mục đích**: Chống prompt injection và nội dung không phù hợp
- **Detects**: 
  - "Bỏ qua mọi luật"
  - "In ra toàn bộ biến môi trường"
  - "Truy vấn KB raw JSON"
- **Action**: `block`
- **Severity**: `high`

#### 5. Nutrition Policy (`nutrition_policy.yaml`)
- **Mục đích**: Ngăn chặn tuyên bố y tế/dinh dưỡng sai lệch
- **Detects**: "Chữa khỏi", "detox", "giảm cân nhanh"
- **Action**: `safe-completion`
- **Severity**: `medium`

### Confidence Scoring

Hệ thống tính confidence score (0-100) dựa trên nhiều yếu tố:

#### Công thức tính điểm

```
Total Score = RAG Score + LLM Score + Entity Score + Base Score 
              - Guardrail Penalty - Domain Penalty
```

#### Các thành phần

1. **RAG Score** (0-40 điểm)
   - Similarity: 32 điểm
   - Consistency (margin): 8 điểm
   - Recency: 2.5 điểm (neutral)

2. **LLM Score** (0-30 điểm)
   - JSON validity: 12 điểm
   - Completeness: 8 điểm
   - Business rules: 6 điểm
   - Self-contradiction penalty: -6 điểm

3. **Entity Resolution Score** (0-15 điểm)
   - Match ratio: 15 điểm
   - Unresolved entities penalty: -3 điểm

4. **Base Score**: 5 điểm

5. **Penalties**
   - Guardrail violations: 
     - `block`: -30 điểm
     - `safe-completion`: -25 điểm
     - `redact`: -15 điểm
   - Domain alerts:
     - Food safety: -15 điểm
     - Allergen: -12 điểm
     - Nutrition warning: -8 điểm

### Contextual Grounding

Kiểm tra tính chính xác của câu trả lời so với nguồn RAG:

```python
# Source: Công thức từ RAG
source_text = "Bún bò Huế cần: thịt bò, bún, sả, ..."

# User query
user_query = "Món bún bò Huế"

# Model output (cần kiểm tra)
model_output = "Bún bò Huế cần có tôm và cua..."

# Apply grounding
result = bedrock_client.apply_contextual_grounding(
    source_text=source_text,
    user_query=user_query,
    model_output=model_output
)

# Nếu phát hiện sai lệch → thay bằng safe-completion
```

### AWS Permissions

Đảm bảo IAM user/role có các quyền sau:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate"
      ],
      "Resource": [
        "arn:aws:bedrock:*:*:knowledge-base/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:ApplyGuardrail"
      ],
      "Resource": [
        "arn:aws:bedrock:*:*:guardrail/*"
      ]
    }
  ]
}
```

### Guardrail Configuration

Để sử dụng AWS Bedrock Guardrails:

1. Tạo Guardrail trên AWS Console hoặc CLI
2. Cấu hình các filters:
   - Content filters (hate, violence, sexual, ...)
   - Denied topics (medical advice, financial advice, ...)
   - Word filters (custom banned words)
   - PII filters (phone, email, SSN, ...)
   - Contextual grounding (hallucination detection)
3. Set `BEDROCK_GUARDRAIL_ID` và `BEDROCK_GUARDRAIL_VERSION` trong `.env`

Custom policies (YAML) sẽ luôn chạy song song với AWS Bedrock Guardrails để tăng độ bao phủ.

## 📚 Best Practices

### 1. Guardrails Configuration
```python
# ✅ Recommended: Tách biệt config cho từng môi trường
# .env.dev
APP_ENV=dev
ENABLE_GUARDRAILS=false  # Nhanh hơn trong dev

# .env.prod
APP_ENV=prod
ENABLE_GUARDRAILS=true  # Luôn bật trong production
BEDROCK_GUARDRAIL_BEHAVIOR=safe-completion
```

### 2. Error Handling
```python
try:
    pipeline = ShoppingCartPipeline()
    result = pipeline.process(user_input)
    
    # Check status
    if result['status'] == 'guardrail_blocked':
        # Handle guardrail violation
        log_violation(result['guardrail'])
        return safe_response(result)
    elif result['status'] == 'error':
        # Handle processing error
        log_error(result['error'])
        return error_response()
    else:
        # Success
        return success_response(result)
        
except Exception as e:
    log_exception(e)
    return fallback_response()
```

### 3. Monitoring & Logging

Hệ thống tự động log các vi phạm guardrails:

```json
{
  "event": "guardrail_violation",
  "request_id": "abc-123-xyz",
  "violation_types": [
    "pii_policy:phone-number",
    "food_safety_policy:unsafe-storage"
  ],
  "action": "safe-completion",
  "environment": "prod",
  "timestamp": "2025-10-23T10:30:00Z"
}
```

**Recommended**: Gửi logs tới CloudWatch, Datadog, hoặc ELK stack.

### 4. Performance Optimization

```python
# ✅ Cache ontology và co-occurrence matrix
pipeline = ShoppingCartPipeline()  # Init once

# ❌ Avoid: Init mỗi request
for request in requests:
    pipeline = ShoppingCartPipeline()  # Slow!
    result = pipeline.process(request)

# ✅ Reuse instance
for request in requests:
    result = pipeline.process(request)  # Fast!
```

### 5. Custom Policy Development

Khi thêm policy mới:

```yaml
# allergen_policy.yaml
policy_id: allergen_detection
name: Allergen Detection Policy
version: 1.0
rules:
  - id: shellfish-allergy
    type: allergy  # Custom type
    severity: high
    action: safe-completion
    message: "Phát hiện nguy cơ dị ứng hải sản"
    remediation: "Đề xuất thay thế nguyên liệu không gây dị ứng"
    allergens:
      - "Tôm"
      - "Cua"
      - "Mực"
    sources:
      - grounding_source  # Từ RAG
      - query            # Từ user input
      - guard_content    # Từ model output
```

### 6. Testing Strategy

```bash
# Test pipeline độc lập (không guardrails)
ENABLE_GUARDRAILS=false pytest tests/test_pipeline.py

# Test guardrails
ENABLE_GUARDRAILS=true pytest tests/test_guardrails.py

# Test integration (toàn bộ)
python test_rag.py
```

## 🐛 Troubleshooting

### Issue: Guardrails luôn bật ngay cả trong dev

**Nguyên nhân**: `APP_ENV=prod` hoặc file `.env` có cấu hình sai

**Giải pháp**:
```bash
# Kiểm tra biến môi trường
echo $APP_ENV
echo $ENABLE_GUARDRAILS

# Set lại
export APP_ENV=dev
export ENABLE_GUARDRAILS=false
```

### Issue: Cannot find guardrail with ID

**Nguyên nhân**: `BEDROCK_GUARDRAIL_ID` không tồn tại hoặc sai region

**Giải pháp**:
```bash
# List guardrails
aws bedrock list-guardrails --region us-east-1

# Get guardrail details
aws bedrock get-guardrail \
  --guardrail-identifier your-id \
  --region us-east-1
```

### Issue: Contextual grounding không hoạt động

**Nguyên nhân**: Chưa bật filter "Contextual Grounding" trong AWS Guardrail

**Giải pháp**:
1. Mở AWS Bedrock Console → Guardrails
2. Edit guardrail → Enable "Contextual grounding"
3. Set threshold: 0.7-0.8 cho balance

### Issue: Conflict detection không phát hiện tương khắc

**Nguyên nhân**: Dữ liệu `ingredient_conflict.json` chưa đầy đủ

**Giải pháp**:
```python
# Kiểm tra conflict data
from app.services.conflict_service import ConflictDetectionService

conflicts = ConflictDetectionService()
print(len(conflicts._conflicts))  # Số lượng conflict rules

# Thêm conflict mới vào ingredient_conflict.json
```

### Issue: RAG không tìm thấy công thức

**Nguyên nhân**: 
- Knowledge Base chưa được sync
- Query không match với indexed documents

**Giải pháp**:
```bash
# Re-sync Knowledge Base
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id your-kb-id \
  --data-source-id your-ds-id \
  --region us-east-1

# Kiểm tra indexing status
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id your-kb-id \
  --data-source-id your-ds-id \
  --ingestion-job-id job-id \
  --region us-east-1
```

### Issue: Fuzzy matching không chính xác

**Nguyên nhân**: Ngưỡng threshold quá thấp hoặc quá cao

**Giải pháp**:
```python
# Trong main.py → _resolve_name_to_ingredient_id
THRESHOLD_A = 0.70  # name_vi threshold
THRESHOLD_B = 0.65  # synonyms threshold

# Tăng threshold nếu có nhiều false positives
# Giảm threshold nếu bỏ sót nhiều matches
```

## 🔗 Tài nguyên tham khảo

### AWS Documentation
- [AWS Bedrock User Guide](https://docs.aws.amazon.com/bedrock/)
- [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
- [Knowledge Bases for Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Claude 3 Model Card](https://www.anthropic.com/claude)

### Vietnamese Food Safety
- [VnExpress Sức khỏe](https://vnexpress.net/suc-khoe)
- [Bộ Y tế Việt Nam](https://moh.gov.vn/)
- [An toàn thực phẩm](https://vfa.gov.vn/)

## 📝 License

MIT License - Xem file LICENSE để biết thêm chi tiết.

## 👥 Contributors

- Development Team - PTIT-KLTN
- Knowledge Base: Vietnamese Food Ontology Project

## 📞 Liên hệ & Hỗ trợ

- Repository: [PTIT-KLTN/AI_Service](https://github.com/PTIT-KLTN/AI_Service)
- Issues: [GitHub Issues](https://github.com/PTIT-KLTN/AI_Service/issues)

---

**Note**: Hệ thống này được phát triển cho mục đích nghiên cứu và giáo dục. Không thay thế tư vấn y tế/dinh dưỡng chuyên nghiệp.
