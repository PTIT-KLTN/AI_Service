import json
import boto3
import os
from dotenv import load_dotenv
import base64
from typing import Optional

from app.services.bedrock_client import GuardrailedBedrockClient
from app.utils.json_utils import parse_json_content

load_dotenv()

class BedrockModelService:
    def __init__(self, region: str | None = None, bedrock_client: Optional[GuardrailedBedrockClient] = None):
        self.bedrock_client = bedrock_client or GuardrailedBedrockClient(region=region)
        self.model_id = os.getenv('INVOKE_MODEL_ID')  
        self.vision_model_id = os.getenv('VISION_MODEL_ID')
        self.bedrock_model_id = os.getenv('BEDROCK_MODEL_ID')  

    def extract_dish_name(self, description: str) -> dict:

        # Guardrails check
        raw_input_check = self.bedrock_client.check_raw_input(description)
        if raw_input_check:
            return {
                'dish_name': None,
                'ingredients': [],
                'excluded_ingredients': [],
                'guardrail': raw_input_check.get('guardrail'),
                'guardrail_messages': raw_input_check.get('guardrail_messages', [])
            }
        
        prompt = f"""Trích xuất tên món ăn CHÍNH, nguyên liệu THÊM VÀO (hoặc ăn/uống KÈM), và nguyên liệu cần LOẠI TRỪ.

                    QUY TẮC QUAN TRỌNG:
                    1. dish_name: Tên món ăn chính người dùng muốn nấu/gọi
                    2. ingredients: Nguyên liệu THÊM VÀO món ăn, hoặc đồ ăn/uống KÈM THEO (như "ăn kèm", "uống kèm", "chấm với", "vắt vào", "rưới lên")
                    3. excluded_ingredients: Nguyên liệu cần LOẠI BỎ (dị ứng, không thích, yêu cầu "bỏ", "không có")

                    Ví dụ:
                    - "Tôi muốn ăn bún bò Huế với trứng cút" 
                    → {{"dish_name": "Bún bò Huế", "ingredients": [{{"name": "Trứng cút"}}], "excluded_ingredients": []}}

                    - "Hướng dẫn nấu món canh cua chua với cam vắt vào"
                    → {{"dish_name": "Canh cua chua", "ingredients": [{{"name": "Cam"}}], "excluded_ingredients": []}}

                    - "Công thức món sầu riêng ăn kèm với rượu"
                    → {{"dish_name": NULL, "ingredients": [{{"name": "Rượu", "Sầu riêng"}}], "excluded_ingredients": []}}

                    - "Làm món trứng chiên ăn kèm sữa đậu nành cho bữa sáng"
                    → {{"dish_name": "Trứng chiên", "ingredients": [{{"name": "Sữa đậu nành"}}], "excluded_ingredients": []}}

                    - "Nấu phở bò"
                    → {{"dish_name": "Phở bò", "ingredients": [], "excluded_ingredients": []}}

                    - "Mình dị ứng đậu phộng, gợi ý topping KHÔNG có hành lá cho phở bò"
                    → {{"dish_name": "Phở bò", "ingredients": [], "excluded_ingredients": [{{"name": "Đậu phộng", "reason": "dị ứng"}}, {{"name": "Hành lá", "reason": "người dùng không muốn"}}]}}

                    - "Cho tôi món phở chay, bỏ hành lá và ngò rí"
                    → {{"dish_name": "Phở chay", "ingredients": [], "excluded_ingredients": [{{"name": "Hành lá"}}, {{"name": "Ngò rí"}}]}}

                    Mô tả: "{description}"

                    Trả về JSON (chỉ JSON, không giải thích):
                    {{
                        "dish_name": "tên món ăn chính",
                        "ingredients": [{{"name": "nguyên liệu thêm/ăn kèm/uống kèm", "quantity": "", "unit": ""}}],
                        "excluded_ingredients": [{{"name": "nguyên liệu cần loại trừ", "reason": "lý do (dị ứng/không thích/...)"}}]
                    }}"""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.1,
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": prompt}]
            }]
        })

        response = self.bedrock_client.invoke_model(model_id=self.model_id, body=body)
        resp_json = json.loads(response['body'].read() or b'{}')

        text = ""
        content_arr = resp_json.get('content') or []
        if isinstance(content_arr, list) and content_arr:
            first = content_arr[0] or {}
            if isinstance(first, dict):
                text = (first.get('text') or "").strip()

        if not text:
            text = json.dumps(resp_json, ensure_ascii=False)

        parsed = parse_json_content(text)
        guardrail_info = response.get('guardrail')
        if guardrail_info:
            parsed['guardrail'] = guardrail_info

        guardrail_messages = response.get('guardrail_messages')
        if guardrail_messages:
            parsed['guardrail_messages'] = guardrail_messages
        return parsed
    
    def extract_dish_from_image(self, image_data, description: str = "", image_mime: str = "image/png") -> dict:
        if not self.vision_model_id:
            raise ValueError('VISION_MODEL_ID environment variable is not configured')

        if not image_data:
            return {"dish_name": None, "ingredients": []}

        # Guardrails check
        if description:
            raw_input_check = self.bedrock_client.check_raw_input(description)
            if raw_input_check:
                return {
                    'dish_name': None,
                    'ingredients': [],
                    'excluded_ingredients': [],
                    'guardrail': raw_input_check.get('guardrail'),
                    'guardrail_messages': raw_input_check.get('guardrail_messages', [])
                }

        image_b64 = self._ensure_base64(image_data)
        body = json.dumps(_build_vision_request_nova(description, image_b64, image_mime))

        response = self.bedrock_client.invoke_model(model_id=self.vision_model_id, body=body)
        resp_json = json.loads(response['body'].read() or b'{}')
        
        # Parse response theo format của Nova
        text = ""
        output = resp_json.get('output', {})
        message = output.get('message', {})
        content = message.get('content', [])
        
        if isinstance(content, list) and content:
            first_content = content[0]
            if isinstance(first_content, dict):
                text = first_content.get('text', '').strip()

        if not text:
            text = json.dumps(resp_json, ensure_ascii=False)

        parsed = parse_json_content(text)
        guardrail_info = response.get('guardrail')
        if guardrail_info:
            parsed['guardrail'] = guardrail_info

        guardrail_messages = response.get('guardrail_messages')
        if guardrail_messages:
            parsed['guardrail_messages'] = guardrail_messages
        return parsed
        
        
    def _ensure_base64(self, image_data) -> str:
        if isinstance(image_data, str):
            return image_data
        if isinstance(image_data, (bytes, bytearray)):
            return base64.b64encode(image_data).decode('utf-8')
        raise TypeError('image_data must be base64 string or bytes-like object')
    
    def invoke_nova_for_rag(self, prompt: str, system_prompt: str = None, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        if not self.bedrock_model_id:
            raise ValueError('BEDROCK_MODEL_ID environment variable is not configured')
        
        # Xây dựng request body theo format của Amazon Nova
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "inferenceConfig": {
                "maxTokens": max_tokens, 
                "temperature": temperature,
                "topP": 0.9
            }
        }
        
        # Thêm system prompt 
        if system_prompt:
            request_body["system"] = [
                {
                    "text": system_prompt
                }
            ]
        
        body = json.dumps(request_body)
        
        # Gọi model
        response = self.bedrock_client.invoke_model(
            model_id=self.bedrock_model_id, 
            body=body
        )
        
        # Parse response
        resp_json = json.loads(response['body'].read() or b'{}')
        
        text = ""
        output = resp_json.get('output', {})
        message = output.get('message', {})
        content = message.get('content', [])
        
        if isinstance(content, list) and content:
            first_content = content[0]
            if isinstance(first_content, dict):
                text = first_content.get('text', '').strip()
        
        if not text:
            text = json.dumps(resp_json, ensure_ascii=False)
        
        return text
    

VISION_SYSTEM_PROMPT = (
    "Bạn là trợ lý ẩm thực chuyên trích xuất thông tin món ăn từ hình ảnh. "
    "Chỉ trả về DUY NHẤT một JSON hợp lệ với cấu trúc: {\"dish_name\": <string|null>, \"ingredients\": [{\"name\": <string>, \"quantity\": \"\", \"unit\": \"\"}]}. "
    "Phân loại ảnh thành một trong ba trường hợp: none | ingredient | dish và áp dụng quy tắc sau: "
    "- none: dish_name = null, ingredients = [] "
    "- ingredient: dish_name = null, ingredients liệt kê từng nguyên liệu nhận diện được "
    "- dish: dish_name bắt buộc, liệt kê các ingredients chính "
    "Luôn dùng tiếng Việt cho tên nguyên liệu. quantity và unit là chuỗi; để chuỗi rỗng nếu không xác định được."
    "Danh sách nguyên liệu trong ingredients KHÔNG được trùng tên nhau."
)


def _build_vision_request_nova(description: str, image_b64: str, image_mime: str) -> dict:

    # Build prompt
    prompt = "Phân tích ảnh và trích xuất JSON theo hướng dẫn. Không giải thích, không thêm văn bản ngoài JSON."
    if description:
        prompt += f'\nMô tả bổ sung: """{description}"""'

    # Map mime type to Nova format
    format_map = {
        "image/jpeg": "jpeg",
        "image/jpg": "jpeg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif"
    }
    image_format = format_map.get(image_mime.lower(), "png")

    return {
        "schemaVersion": "messages-v1",
        "system": [
            {
                "text": VISION_SYSTEM_PROMPT
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": image_format,
                            "source": {
                                "bytes": image_b64  # Base64-encoded string for Invoke API
                            }
                        }
                    },
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "inferenceConfig": {
            "maxTokens": 1024,
            "temperature": 0.1,
            "topP": 0.9
        }
    }