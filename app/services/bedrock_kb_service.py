import boto3
import os
import json
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

from app.utils.json_utils import read_json_from_s3_uri
from app.utils.string_utils import norm_text
from app.utils.number_utils import parse_number

load_dotenv()


class BedrockKBService:
    def __init__(self, region: str = 'us-east-1'):
        self.bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=region)
        self.kb_id = os.getenv('BEDROCK_KB_ID')
        self.model_id = os.getenv('MODEL_ID')

    @staticmethod
    def _extract_first_uri(resp: Dict[str, Any]) -> Optional[str]:
        for c in resp.get('citations', []):
            for ref in c.get('retrievedReferences', []):
                md = ref.get('metadata') or {}
                uri = (
                    md.get('x-amz-bedrock-kb-source-uri')
                    or (((ref.get('location') or {}).get('s3Location') or {}).get('uri'))
                )
                if uri:
                    return uri
        return None

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
            "Bắt buộc kèm citations nguồn để tôi lấy URI file gốc."
        )

        try:
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
                                'numberOfResults': 36
                            }
                        },
                    },
                },
            )

            first_uri = self._extract_first_uri(resp)
            
            if first_uri:
                try:
                    j = read_json_from_s3_uri(first_uri)
                    title = j.get('dish_name') or j.get('name_vi') or j.get('name') or dish_name
                    ings = self._extract_ingredients_from_json(j)
                    if ings:
                        return {'dish_name': title, 'ingredients': ings}
                except Exception:
                    pass  

            answer = resp.get('output', {}).get('text', '').strip()

            if '```' in answer:
                buf, in_code = [], False
                for line in answer.splitlines():
                    if '```' in line:
                        in_code = not in_code
                        continue
                    if in_code:
                        buf.append(line)
                answer = "\n".join(buf).strip()

            parsed = json.loads(answer) if answer else {}
            if isinstance(parsed, dict) and 'ingredients' in parsed:
                cleaned = []
                for it in parsed['ingredients']:
                    if isinstance(it, dict):
                        cleaned.append({
                            'name': it.get('name') or it.get('name_vi') or it.get('name_en'),
                            'quantity': parse_number(it.get('quantity')),
                            'unit': it.get('unit')
                        })
                parsed['ingredients'] = cleaned
                if not parsed.get('dish_name'):
                    parsed['dish_name'] = dish_name
                return parsed

            return {'dish_name': dish_name, 'ingredients': []}

        except Exception:
            return {'dish_name': dish_name, 'ingredients': []}