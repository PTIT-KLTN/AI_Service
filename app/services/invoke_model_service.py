import json
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

class BedrockModelService:
    def __init__(self, region: str = 'us-east-1'):
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = os.getenv('MODEL_ID')
    
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
        
        response = self.bedrock_runtime.invoke_model(modelId=self.model_id, body=body)
        content = json.loads(response['body'].read())['content'][0]['text'].strip()
        
        if content.startswith('```'):
            content = '\n'.join(content.split('\n')[1:-1]).lstrip('json')
        
        try:
            return json.loads(content)
        except:
            return {"dish_name": None, "ingredients": []}