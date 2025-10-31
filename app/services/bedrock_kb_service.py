import boto3
import os
import json
from typing import Dict, List, Any
from dotenv import load_dotenv

from app.utils.string_utils import norm_text
from app.utils.number_utils import parse_number

load_dotenv()


class BedrockKBService:
    def __init__(self, region: str = 'us-east-1'):
        self.bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=region)
        self.kb_id = os.getenv('BEDROCK_KB_ID')
        self.model_id = os.getenv('MODEL_ID')

    def _extract_ingredients_from_json(self, j: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Any] = []
        if isinstance(j.get('ingredients'), list):
            candidates.append(j['ingredients'])
        if isinstance(j.get('data'), dict) and isinstance(j['data'].get('ingredients'), list):
            candidates.append(j['data']['ingredients'])
        if isinstance(j.get('recipe'), dict) and isinstance(j['recipe'].get('ingredients'), list):
            candidates.append(j['recipe']['ingredients'])

        if not candidates:
            return []

        items: List[Dict[str, Any]] = []
        for arr in candidates:
            for it in arr:
                if not isinstance(it, dict):
                    continue
                name = it.get('name_vi') or it.get('name') or it.get('name_en')
                qty = it.get('quantity', it.get('qty'))
                unit = it.get('unit') or it.get('unit_vi') or it.get('unit_en')
                if name is None:
                    continue
                items.append({
                    'name': str(name).strip(),
                    'quantity': parse_number(qty),
                    'unit': unit
                })

        seen = set()
        uniq = []
        for ing in items:
            k = (norm_text(ing['name']), norm_text(ing.get('unit') or ''), str(ing.get('quantity')))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(ing)
        return uniq

    def get_dish_recipe(self, dish_name: str) -> dict:
        query = (
            f"Tìm đúng món: {dish_name}\n"
            "Trả về JSON với dạng:\n"
            "{ \"dish_name\": \"...\", \"ingredients\": [{\"name\":\"...\",\"quantity\":...,\"unit\":\"...\"}] }\n"
        )

        try:
            # Retrieve and generate 
            resp = self.bedrock_agent.retrieve_and_generate(
                input={'text': query},
                retrieveAndGenerateConfiguration={
                    'type': 'KNOWLEDGE_BASE',
                    'knowledgeBaseConfiguration': {
                        'knowledgeBaseId': self.kb_id,
                        'modelArn': self.model_id,
                        'retrievalConfiguration': {
                            'vectorSearchConfiguration': {
                                'overrideSearchType': 'SEMANTIC',  
                                'numberOfResults': 20
                            }
                        },
                    },
                },
            )

            # Parse response 
            answer = resp.get('output', {}).get('text', '').strip()
            
            if not answer:
                return {'dish_name': dish_name, 'ingredients': []}

            # Remove markdown code blocks if present
            if '```' in answer:
                buf, in_code = [], False
                for line in answer.splitlines():
                    if '```' in line:
                        in_code = not in_code
                        continue
                    if in_code:
                        buf.append(line)
                answer = "\n".join(buf).strip()
            
            # Extract JSON from text (LLM may add explanation before/after JSON)
            json_start = answer.find('{')
            json_end = answer.rfind('}')
            
            if json_start >= 0 and json_end > json_start:
                answer = answer[json_start:json_end + 1]
            
            parsed = json.loads(answer) if answer else {}
            if isinstance(parsed, dict) and 'ingredients' in parsed:
                cleaned = []
                for it in parsed.get('ingredients', []):
                    if not isinstance(it, dict):
                        continue
                    
                    # Extract name from various fields
                    name = it.get('name') or it.get('name_vi') or it.get('name_en')
                    
                    # Skip if no valid name
                    if not name or not str(name).strip():
                        continue
                    
                    # Parse quantity 
                    qty_raw = it.get('quantity')
                    qty_str = ''
                    if qty_raw is not None:
                        qty_num = parse_number(qty_raw)
                        if qty_num is not None:
                            qty_str = str(qty_num) if isinstance(qty_num, int) else str(float(qty_num)).rstrip('0').rstrip('.')
                    
                    cleaned.append({
                        'name': str(name).strip(),
                        'quantity': qty_str,
                        'unit': it.get('unit') or it.get('unit_vi') or it.get('unit_en') or ''
                    })
                
                parsed['ingredients'] = cleaned
                if not parsed.get('dish_name'):
                    parsed['dish_name'] = dish_name
                return parsed

            return {'dish_name': dish_name, 'ingredients': []}

        except Exception:
            return {'dish_name': dish_name, 'ingredients': []}