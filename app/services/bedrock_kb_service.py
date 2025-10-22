import boto3
import os
import json
import unicodedata
from difflib import SequenceMatcher
from collections import Counter
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client('s3')


class BedrockKBService:
    def __init__(self, region: str = 'us-east-1'):
        self.bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=region)
        self.kb_id = os.getenv('BEDROCK_KB_ID')
        self.model_id = os.getenv('MODEL_ID')

    # --------------------------- Utils ---------------------------

    @staticmethod
    def _read_json_from_s3_uri(s3_uri: str) -> Dict[str, Any]:
        assert s3_uri.startswith('s3://'), f"Invalid S3 URI: {s3_uri}"
        _, _, path = s3_uri.partition('s3://')
        bucket, _, key = path.partition('/')
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj['Body'].read().decode('utf-8')
        return json.loads(body)

    @staticmethod
    def _strip_accents(s: str) -> str:
        if not isinstance(s, str):
            s = str(s)
        nfkd = unicodedata.normalize("NFKD", s)
        return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    @staticmethod
    def _norm(s: Optional[str]) -> str:
        if s is None:
            return ""
        return BedrockKBService._strip_accents(s).lower().strip()

    @staticmethod
    def _similar(a: str, b: str) -> float:
        return SequenceMatcher(None, BedrockKBService._norm(a), BedrockKBService._norm(b)).ratio()

    @staticmethod
    def _num(v):
        try:
            return float(v)
        except Exception:
            return v

    # ----------------- Citations / URI picking -------------------

    @staticmethod
    def _uris_with_counts(resp: Dict[str, Any]) -> List[Tuple[str, int]]:
        counts = Counter()
        for c in resp.get('citations', []):
            for ref in c.get('retrievedReferences', []):
                md = ref.get('metadata') or {}
                uri = (
                    md.get('x-amz-bedrock-kb-source-uri')
                    or (((ref.get('location') or {}).get('s3Location') or {}).get('uri'))
                )
                if uri:
                    counts[uri] += 1
        return list(counts.items())

    def _pick_best_uri(self, dish_name: str, uri_counts: List[Tuple[str, int]]) -> Optional[str]:
        if not uri_counts:
            return None

        # sắp theo count giảm dần
        uri_counts = sorted(uri_counts, key=lambda x: (-x[1], x[0]))

        best_fallback = uri_counts[0][0]
        for uri, _cnt in uri_counts:
            try:
                j = self._read_json_from_s3_uri(uri)
            except Exception:
                continue

            title = (
                j.get('dish_name')
                or j.get('name_vi')
                or j.get('name')
                or j.get('title')
            )
            if not title:
                # không có tiêu đề để so, thử ứng viên khác
                continue

            if self._similar(dish_name, title) >= 0.6:
                return uri

        # không tìm được match đủ ngưỡng → fallback URI có count cao nhất
        return best_fallback

    # --------------------- Ingredient extract --------------------

    def _extract_ingredients_from_json(self, j: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Any] = []
        if isinstance(j.get('ingredients'), list):
            candidates.append(j['ingredients'])
        if isinstance(j.get('data'), dict) and isinstance(j['data'].get('ingredients'), list):
            candidates.append(j['data']['ingredients'])
        if isinstance(j.get('recipe'), dict) and isinstance(j['recipe'].get('ingredients'), list):
            candidates.append(j['recipe']['ingredients'])

        # nếu vẫn chưa có gì, đừng vét cạn toàn JSON để tránh lẫn
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
                    'quantity': self._num(qty),
                    'unit': unit
                })

        # lọc trùng theo tên đã normalize + đơn vị + quantity
        seen = set()
        uniq = []
        for ing in items:
            k = (self._norm(ing['name']), self._norm(ing.get('unit') or ''), str(ing.get('quantity')))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(ing)
        return uniq

    # ------------------------ Public API -------------------------

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
                                'numberOfResults': 24  # đủ để gom chunk của 1 file
                            }
                        },
                    },
                },
            )

            uri_counts = self._uris_with_counts(resp)
            best_uri = self._pick_best_uri(dish_name, uri_counts)

            if best_uri:
                try:
                    j = self._read_json_from_s3_uri(best_uri)
                    title = j.get('dish_name') or j.get('name_vi') or j.get('name') or dish_name
                    ings = self._extract_ingredients_from_json(j)
                    if ings:
                        return {'dish_name': title, 'ingredients': ings}
                except Exception:
                    pass  # nếu đọc lỗi, tiếp tục fallback

            # --- Fallback: parse text output của LLM ---
            answer = resp.get('output', {}).get('text', '').strip()

            # bóc codeblock nếu có
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
                            'quantity': self._num(it.get('quantity')),
                            'unit': it.get('unit')
                        })
                parsed['ingredients'] = cleaned
                if not parsed.get('dish_name'):
                    parsed['dish_name'] = dish_name
                return parsed

            return {'dish_name': dish_name, 'ingredients': []}

        except Exception:
            return {'dish_name': dish_name, 'ingredients': []}