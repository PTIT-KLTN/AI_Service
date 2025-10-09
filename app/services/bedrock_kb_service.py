import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

class BedrockKBService:
    def __init__(self, region: str = 'us-east-1'):
        self.bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=region)
        self.kb_id = os.getenv('BEDROCK_KB_ID')
        self.model_id = os.getenv('MODEL_ID')
    
    def get_dish_recipe(self, dish_name: str) -> dict:
        query = f"""Món: {dish_name}

        Trả về JSON công thức:
        {{
        "dish_name": "tên",
        "ingredients": [{{"name": "tên", "quantity": "số", "unit": "đơn vị"}}],
        }}

        QUAN TRỌNG: ingredients PHẢI có đầy đủ quantity và unit.
        Nếu không tìm thấy món, trả về ingredients = [].
        Chỉ trả JSON."""
        
        try:
            response = self.bedrock_agent.retrieve_and_generate(
                input={'text': query},
                retrieveAndGenerateConfiguration={
                    'type': 'KNOWLEDGE_BASE',
                    'knowledgeBaseConfiguration': {
                        'knowledgeBaseId': self.kb_id,
                        'modelArn': self.model_id
                    }
                }
            )
            
            answer = response['output']['text']
            
            # Parse JSON
            if '```' in answer:
                lines = []
                in_code = False
                for line in answer.split('\n'):
                    if '```' in line:
                        in_code = not in_code
                        continue
                    if in_code:
                        lines.append(line)
                answer = '\n'.join(lines)
            
            return json.loads(answer.strip())
        except:
            return {'dish_name': dish_name, 'ingredients': []}