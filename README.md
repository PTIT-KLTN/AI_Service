# AI Service - Dịch vụ Giỏ hàng Thông minh Ẩm thực Việt Nam

Một hệ thống AI tiên tiến sử dụng AWS Bedrock để xử lý và gợi ý giỏ hàng thông minh dựa trên món ăn Việt Nam. Hệ thống có khả năng hiểu ngôn ngữ tự nhiên, trích xuất tên món ăn, tìm kiếm công thức và gợi ý nguyên liệu phù hợp.

## 🌟 Tính năng chính

- **Trích xuất món ăn thông minh**: Sử dụng AWS Bedrock để hiểu yêu cầu người dùng và trích xuất tên món ăn chính cùng nguyên liệu bổ sung
- **Tìm kiếm công thức**: Tích hợp RAG (Retrieval-Augmented Generation) với Knowledge Base để tìm công thức món ăn
- **Chuẩn hóa đơn vị**: Tự động chuyển đổi và chuẩn hóa đơn vị đo lường nguyên liệu
- **Gợi ý thông minh**: Dựa trên ma trận đồng xuất hiện để gợi ý nguyên liệu phù hợp
- **Tìm món tương tự**: Phân tích độ tương đồng giữa các món ăn dựa trên nguyên liệu
- **Ontology ẩm thực Việt Nam**: Cơ sở tri thức đầy đủ về món ăn và nguyên liệu Việt Nam

## 🏗️ Kiến trúc hệ thống

```
AI_service/
├── app/
│   ├── main.py                           # Pipeline xử lý chính
│   ├── services/
│   │   ├── bedrock_kb_service.py         # Dịch vụ AWS Bedrock Knowledge Base
│   │   ├── invoke_model_service.py       # Dịch vụ gọi AWS Bedrock Model
│   │   ├── ontology_service.py           # Quản lý ontology món ăn/nguyên liệu
│   │   ├── unit_converter_service.py     # Chuyển đổi đơn vị đo lường
│   │   └── validation_service.py         # Validation và gợi ý dựa trên co-occurrence
│   ├── data/
│   │   ├── knowledge_base/               # Cơ sở tri thức món ăn và nguyên liệu
│   │   └── cooccurrence/                 # Ma trận đồng xuất hiện
│   └── scripts/
│       └── build_cooccurrence.py         # Script xây dựng ma trận co-occurrence
├── requirements.txt
├── test_rag.py                          # Script test pipeline
└── README.md
```

## 🛠️ Công nghệ sử dụng

- **Framework**: Python 3.9
- **AI Services**: AWS Bedrock (Claude 3, Knowledge Base)
- **SDK**: Boto3 cho AWS integration
- **Utilities**: python-dotenv cho quản lý environment
- **Data Format**: JSON cho knowledge base và co-occurrence matrix

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
BEDROCK_KB_ID=your_knowledge_base_id
MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
AWS_REGION=us-east-1
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

```python
pipeline = ShoppingCartPipeline()
result = pipeline.process(user_input)
```

**Input**: Câu mô tả món ăn bằng tiếng Việt
- Ví dụ: "Tôi muốn ăn bún bò Huế với trứng cút"
- Ví dụ: "Nấu phở bò"

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
      "score": 0.85,
      "reason": "Thường đi kèm với món này"
    }
  ],
  "similar_dishes": [
    {
      "dish_id": "dish_003",
      "dish_name": "Bún bò Nam Bộ",
      "match_ratio": 0.7
    }
  ]
}
```

## 🎯 Các Service Components

### 1. BedrockModelService
- Trích xuất tên món ăn và nguyên liệu bổ sung từ mô tả tự nhiên
- Sử dụng Claude 3 Sonnet cho NLP tasks

### 2. BedrockKBService  
- Tìm kiếm công thức món ăn từ AWS Bedrock Knowledge Base
- RAG-based recipe retrieval

### 3. OntologyService
- Quản lý cơ sở tri thức món ăn và nguyên liệu Việt Nam
- Tìm kiếm món ăn tương tự dựa trên nguyên liệu

### 4. UnitConverterService
- Chuẩn hóa đơn vị đo lường (kg, gram, thìa, chén, ...)
- Chuyển đổi về đơn vị tiêu chuẩn

### 5. ValidationService
- Kiểm tra tính hợp lý của nguyên liệu
- Gợi ý nguyên liệu dựa trên co-occurrence matrix

## 📊 Dữ liệu

### Knowledge Base
- `dish_knowledge_base.json`: Thông tin món ăn Việt Nam
- `ingredient_knowledge_base.json`: Danh mục nguyên liệu và thuộc tính

### Co-occurrence Matrix
- `frequency.json`: Tần suất xuất hiện của nguyên liệu
- `matrix.json`: Ma trận đồng xuất hiện giữa các nguyên liệu
- `metadata.json`: Thông tin metadata của ma trận

## 🧪 Testing

Chạy test với dữ liệu mẫu:
```bash
python test_rag.py
```

Kết quả test sẽ được lưu trong `test_output.json`

## 🔧 Cấu hình

### Biến môi trường quan trọng

- `BEDROCK_KB_ID`: ID của Knowledge Base trên AWS Bedrock
- `MODEL_ID`: Model ID cho Claude 3 (mặc định: anthropic.claude-3-sonnet-20240229-v1:0)
- `AWS_REGION`: AWS region (mặc định: us-east-1)

### AWS Permissions

Đảm bảo IAM user/role có các quyền:
- `bedrock:InvokeModel`
- `bedrock:RetrieveAndGenerate`
- `bedrock-agent-runtime:RetrieveAndGenerate`
