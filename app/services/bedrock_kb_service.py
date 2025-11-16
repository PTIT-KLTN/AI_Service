import boto3
import os
import json
import logging
from typing import Dict, List, Any
from dotenv import load_dotenv

from app.utils.string_utils import norm_text
from app.utils.number_utils import parse_number
from app.services.invoke_model_service import BedrockModelService

load_dotenv()

logger = logging.getLogger(__name__)


class BedrockKBService:
    def __init__(self, region: str = 'us-east-1'):
        self.bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=region)
        self.kb_id = os.getenv('BEDROCK_KB_ID')
        self.bedrock_model_id = os.getenv('BEDROCK_MODEL_ID') 
        self.bedrock_model_service = BedrockModelService(region=region)

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
                unit = it.get('unit', '')
                if name is None:
                    continue
                items.append({
                    'name': str(name).strip(),
                    'unit': unit
                })

        seen = set()
        uniq = []
        for ing in items:
            k = (norm_text(ing['name']), norm_text(ing.get('unit') or ''))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(ing)
        return uniq

    def get_dish_recipe(self, dish_name: str) -> dict:

        query = f"Tìm đúng món: {dish_name}"

        try:
            # Retrieve relevant documents từ KB
            retrieve_response = self.bedrock_agent.retrieve(
                knowledgeBaseId=self.kb_id,
                retrievalQuery={'text': query},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'overrideSearchType': 'SEMANTIC',  
                        'numberOfResults': 20,
                        'filter': {
                            'equals': {
                                'key': 'type',
                                'value': 'dish'
                            }
                        }
                    }
                }
            )

            # Extract context từ retrieved documents
            retrieval_results = retrieve_response.get('retrievalResults', [])
            
            if not retrieval_results:
                return {'dish_name': dish_name, 'ingredients': []}
            
            # Build context từ các documents được retrieve
            context_parts = []
            for idx, result in enumerate(retrieval_results[:20], 1):  # Lấy top 10 results
                content = result.get('content', {}).get('text', '')
                if content:
                    context_parts.append(f"[Tài liệu {idx}]:\n{content}")
            
            context = "\n\n".join(context_parts)
            
            # Step 2: Sử dụng Nova model để generate response
            system_prompt = """Bạn là chuyên gia ẩm thực Việt Nam. Nhiệm vụ của bạn là trích xuất thông tin công thức món ăn từ tài liệu được cung cấp.

                                QUAN TRỌNG:
                                - Chỉ trả về JSON hợp lệ, KHÔNG giải thích thêm
                                - Trích xuất TỐI ĐA 25 nguyên liệu CHÍNH từ tài liệu
                                - Ưu tiên nguyên liệu theo thứ tự importance:
                                  * importance=3: Nguyên liệu CHÍNH tạo nên đặc trưng món (BẮT BUỘC phải có)
                                  * importance=2: Nguyên liệu QUAN TRỌNG (gia vị chính, nước sốt) (ưu tiên cao)
                                  * importance=1: Nguyên liệu phụ (chỉ lấy nếu còn slot trong 25 nguyên liệu)
                                - TUYỆT ĐỐI không bỏ sót nguyên liệu có importance >= 2
                                - Nếu có nhiều hơn 25 nguyên liệu, chỉ giữ lại 25 nguyên liệu quan trọng nhất
                                - vietnamese_name: tên tiếng Việt của món ăn hoặc nguyên liệu
                                - name: tên tiếng Anh của món ăn hoặc nguyên liệu
                                - unit: kết hợp số lượng và đơn vị (VD: "500 g", "2 củ", "1 muỗng canh"), để rỗng nếu không có
                                - danh sách nguyên liệu không được trùng lặp
                                """

            user_prompt = f"""Dựa trên các tài liệu sau, hãy trích xuất công thức cho món: {dish_name}

                                {context}

                                Trả về JSON với format (tối đa 25 nguyên liệu quan trọng nhất):
                                {{"vietnamese_name": "tên món tiếng Việt", "name": "tên món tiếng Anh", "ingredients": [{{"vietnamese_name": "tên nguyên liệu tiếng Việt", "name": "tên nguyên liệu tiếng Anh", "unit": "số lượng và đơn vị"}}]}}"""

            # Gọi Nova model với max_tokens đủ lớn
            answer = self.bedrock_model_service.invoke_nova_for_rag(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,  
                max_tokens=4096 
            )
            
            if not answer:
                return {'vietnamese_name': dish_name, 'name': '', 'ingredients': []}

            # Parse JSON response
            if '```' in answer:
                buf, in_code = [], False
                for line in answer.splitlines():
                    if '```' in line:
                        in_code = not in_code
                        continue
                    if in_code: 
                        buf.append(line)
                answer = "\n".join(buf).strip()
            
            # Extract JSON from text
            json_start = answer.find('{')
            json_end = answer.rfind('}')
            
            if json_start >= 0 and json_end > json_start:
                answer = answer[json_start:json_end + 1]
            else:
                if json_start >= 0:
                    answer = answer[json_start:]
                    open_braces = answer.count('{')
                    close_braces = answer.count('}')
                    open_brackets = answer.count('[')
                    close_brackets = answer.count(']')
                    
                    # Add missing closing brackets/braces
                    if open_brackets > close_brackets:
                        answer += '\n' + (']' * (open_brackets - close_brackets))
                    if open_braces > close_braces:
                        answer += '\n' + ('}' * (open_braces - close_braces))
            
            # Clean trailing commas
            import re
            answer = re.sub(r',(\s*[}\]])', r'\1', answer)
            
            parsed = json.loads(answer) if answer else {}
            
            if isinstance(parsed, dict) and 'ingredients' in parsed:
                cleaned = []
                for it in parsed.get('ingredients', []):
                    if not isinstance(it, dict):
                        continue
                    
                    # Extract name
                    vietnamese_name = it.get('vietnamese_name') or it.get('name_vi')
                    name_en = it.get('name') or it.get('name_en', '')
                    
                    if not vietnamese_name or not str(vietnamese_name).strip():
                        continue
                    
                    cleaned.append({
                        'vietnamese_name': str(vietnamese_name).strip(),
                        'name': str(name_en).strip() if name_en else '',
                        'unit': it.get('unit', '')
                    })
                
                parsed['ingredients'] = cleaned
                
                # Handle dish names
                if not parsed.get('vietnamese_name'):
                    parsed['vietnamese_name'] = dish_name
                if not parsed.get('name'):
                    parsed['name'] = ''
                    
                return parsed

            return {'vietnamese_name': dish_name, 'name': '', 'ingredients': []}

        except Exception as e:
            logger.error(f"Error in get_dish_recipe for '{dish_name}': {str(e)}")
            return {'vietnamese_name': dish_name, 'name': '', 'ingredients': []}