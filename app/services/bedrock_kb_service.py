# bedrock_kb_service.py  (version: pinecone-only, cleaned)
import os
import json
import unicodedata
from difflib import SequenceMatcher
import boto3

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pinecone import Pinecone
from dotenv import load_dotenv
load_dotenv()

s3 = boto3.client("s3")


class BedrockKBService:
    """
    Pinecone-first (only) retrieval cho công thức:
      1) Nhúng truy vấn tên món bằng Bedrock Titan Embeddings
      2) Query Pinecone (top_k, filter theo namespace/metadata nếu cần)
      3) Chọn ứng viên tốt nhất bằng fuzzy title
      4) Đọc JSON gốc từ S3 (metadata.s3_uri) và trích 'ingredients'
    """

    def __init__(self, region: str = "us-east-1"):
        self.region = region

        # Pinecone
        api_key = os.environ["PINECONE_API_KEY"]
        index_name = os.environ["PINECONE_INDEX"]
        self.namespace = os.getenv("PINECONE_NAMESPACE", "vi")

        self.pc = Pinecone(api_key=api_key)
        self.index = self.pc.Index(index_name)

        # Bedrock runtime
        self.embedding_model_id = os.getenv(
            "EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1"
        )
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=region)

    # --------------------------- utils ---------------------------

    @staticmethod
    def _read_json_from_s3_uri(s3_uri: str) -> Dict[str, Any]:
        assert s3_uri.startswith("s3://"), f"Invalid S3 URI: {s3_uri}"
        _, _, path = s3_uri.partition("s3://")
        bucket, _, key = path.partition("/")
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read().decode("utf-8")
        return json.loads(body)

    @staticmethod
    def _strip_accents(s: str) -> str:
        if not isinstance(s, str):
            s = str(s)
        nfkd = unicodedata.normalize("NFKD", s)
        return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    @classmethod
    def _norm(cls, s: Optional[str]) -> str:
        if not s:
            return ""
        return cls._strip_accents(s).lower().strip()

    @classmethod
    def _similar(cls, a: str, b: str) -> float:
        return SequenceMatcher(None, cls._norm(a), cls._norm(b)).ratio()

    @staticmethod
    def _num(v):
        try:
            return float(v)
        except Exception:
            return v

    def _extract_ingredients_from_json(self, j: Dict[str, Any]) -> List[Dict[str, Any]]:

        paths = []
        if isinstance(j.get("ingredients"), list):
            paths.append(j["ingredients"])
        if isinstance(j.get("data"), dict) and isinstance(j["data"].get("ingredients"), list):
            paths.append(j["data"]["ingredients"])
        if isinstance(j.get("recipe"), dict) and isinstance(j["recipe"].get("ingredients"), list):
            paths.append(j["recipe"]["ingredients"])

        items: List[Dict[str, Any]] = []
        for arr in paths:
            for it in arr:
                if not isinstance(it, dict):
                    continue
                name = it.get("name_vi") or it.get("name") or it.get("name_en")
                qty = it.get("quantity", it.get("qty"))
                unit = it.get("unit") or it.get("unit_vi") or it.get("unit_en")
                if name is None:
                    continue
                items.append({
                    "name": str(name).strip(),
                    "quantity": self._num(qty),
                    "unit": unit,
                })

        # dedupe theo (name, unit, quantity) đã normalize
        seen, uniq = set(), []
        for ing in items:
            k = (self._norm(ing["name"]), self._norm(ing.get("unit") or ""), str(ing.get("quantity")))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(ing)
        return uniq

    # ---------------------- embedding & query ----------------------

    def _embed_text(self, text: str) -> List[float]:
        payload = {"inputText": text}
        resp = self.bedrock_runtime.invoke_model(
            modelId=self.embedding_model_id,
            body=json.dumps(payload),
        )
        body = resp["body"].read()
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        data = json.loads(body)
        emb = data.get("embedding") or data.get("vector") or []
        return emb if isinstance(emb, list) else []

    def _pinecone_query(self, dish_name: str) -> Optional[dict]:
        vec = self._embed_text(dish_name)
        if not vec:
            return None

        # nếu metadata đã index có 'type'/'lang' hãy bật filter dưới
        pine_filter = None
        # pine_filter = {"type": {"$eq": "recipe"}, "lang": {"$eq": "vi"}}

        res = self.index.query(
            namespace=self.namespace,
            vector=vec,
            top_k=8,
            include_metadata=True,
            filter=pine_filter,
        )
        matches = res.get("matches") or []
        if not matches:
            return None

        # chọn ứng viên có title giống nhất với dish_name; fallback lấy match đầu
        best, best_sim = None, -1.0
        fallback = None

        for m in matches:
            md = m.get("metadata") or {}
            title = md.get("dish_name") or md.get("name_vi") or md.get("name") or md.get("title")
            s3_uri = md.get("s3_uri") or md.get("uri")
            if not s3_uri:
                continue
            if fallback is None:
                fallback = (s3_uri, title)

            sim = self._similar(dish_name, title) if title else 0.0
            if sim > best_sim:
                best_sim = sim
                best = (s3_uri, title)

        target = best or fallback
        if not target:
            return None

        s3_uri, title = target
        j = self._read_json_from_s3_uri(s3_uri)
        display_title = j.get("dish_name") or j.get("name_vi") or j.get("name") or title or dish_name
        ings = self._extract_ingredients_from_json(j)
        if not ings:
            return None
        return {"dish_name": display_title, "ingredients": ings}

    # --------------------------- public ---------------------------

    def get_dish_recipe(self, dish_name: str) -> dict:
        """
        Trả về {'dish_name': str, 'ingredients': List[dict]}.
        Không merge nhiều món; chỉ đọc đúng JSON từ S3 ứng với vector match.
        """
        result = self._pinecone_query(dish_name)
        if result:
            return result
        # Không fallback KB nữa: trả rỗng nếu không tìm được
        return {"dish_name": dish_name, "ingredients": []}
