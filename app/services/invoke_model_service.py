import json
import boto3
import os
from dotenv import load_dotenv
import base64
from typing import Optional
from app.services.bedrock_client import GuardrailedBedrockClient

load_dotenv()

class BedrockModelService:
    def __init__(self, region: str = 'us-east-1', bedrock_client: Optional[GuardrailedBedrockClient] = None):
        self.bedrock_client = bedrock_client or GuardrailedBedrockClient(region=region)
        self.model_id = os.getenv('INVOKE_MODEL_ID')
        self.vision_model_id = os.getenv('VISION_MODEL_ID')
    
    def extract_dish_name(self, description: str) -> dict:
        prompt = f"""Trích xuất tên món ăn CHÍNH và nguyên liệu THÊM VÀO (không phải trong công thức gốc).

                    Ví dụ:
                    - "Tôi muốn ăn bún bò Huế với trứng cút" 
                    → dish_name: "Bún bò Huế", ingredients: [{{"name": "trứng cút"}}]
                    
                    - "Nấu phở bò"
                    → dish_name: "Phở bò", ingredients: []

                    Mô tả: "{description}"

                    Trả về JSON:
                    {{
                        "dish_name": "tên món chính",
                        "ingredients": [{{"name": "nguyên liệu thêm", "quantity": "", "unit": ""}}]
                    }}

                    Chỉ trả về JSON."""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        })
        
        response = self.bedrock_client.invoke_model(model_id=self.model_id, body=body)
        content = json.loads(response['body'].read())['content'][0]['text'].strip()

        parsed = self._parse_content(content)
        guardrail_info = response.get('guardrail')
        if guardrail_info:
            parsed['guardrail'] = guardrail_info
        return parsed
    
    def extract_dish_from_image(self, image_data, description: str = "", image_mime: str = "image/png") -> dict:
        """Extract dish information from an image (base64 string or raw bytes)."""
        if not self.vision_model_id:
            raise ValueError('VISION_MODEL_ID environment variable is not configured')

        if not image_data:
            return {"dish_name": None, "ingredients": []}

        image_b64 = self._ensure_base64(image_data)
        body = json.dumps(_build_vision_request(description, image_b64, image_mime))

        response = self.bedrock_client.invoke_model(model_id=self.vision_model_id, body=body)
        content = json.loads(response['body'].read())['content'][0]['text'].strip()
        parsed = self._parse_content(content)
        
        guardrail_info = response.get('guardrail')
        if guardrail_info:
            parsed['guardrail'] = guardrail_info
        return parsed
        
    def _parse_content(self, content: str) -> dict:
        if content.startswith('```'):
            content = '\n'.join(content.split('\n')[1:-1]).lstrip('json')
        
        try:
            data = json.loads(content)
        except Exception:
            return {"dish_name": None, "ingredients": []}
        
        dish_name = data.get('dish_name')
        ingredients = data.get('ingredients', []) if isinstance(data.get('ingredients', []), list) else []
        return {"dish_name": dish_name, "ingredients": ingredients}
    
    def _ensure_base64(self, image_data) -> str:
        if isinstance(image_data, str):
            return image_data
        if isinstance(image_data, (bytes, bytearray)):
            return base64.b64encode(image_data).decode('utf-8')
        raise TypeError('image_data must be base64 string or bytes-like object')
    

VISION_SYSTEM_PROMPT = (
    "Bạn là trợ lý ẩm thực chuyên trích xuất thông tin món ăn từ hình ảnh.\n"
    "Chỉ trả về DUY NHẤT một JSON hợp lệ với cấu trúc: {\"dish_name\": <string|null>, \"ingredients\": [{\"name\": <string>, \"quantity\": \"\", \"unit\": \"\"}]}.\n"
    "Phân loại ảnh thành một trong ba trường hợp: none | ingredient | dish và áp dụng quy tắc sau:\n"
    "- none: dish_name = null, ingredients = []\n"
    "- ingredient: dish_name = null, ingredients liệt kê từng nguyên liệu nhận diện được\n"
    "- dish: dish_name bắt buộc, liệt kê các ingredients chính\n"
    "Luôn dùng tiếng Việt cho tên nguyên liệu. quantity và unit là chuỗi; để chuỗi rỗng nếu không xác định được."
)


def _build_vision_request(description: str, image_b64: str, image_mime: str) -> dict:
    prompt = (
        "Phân tích ảnh và trích xuất JSON theo hướng dẫn.\n"
        "Không giải thích, không thêm văn bản ngoài JSON.\n"
    )
    if description:
        prompt += f'\nMô tả bổ sung: """{description}"""'

    return {
        "anthropic_version": "bedrock-2023-05-31",
        "system": VISION_SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_mime,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
        "temperature": 0.1,
        "max_tokens": 1000,
    }