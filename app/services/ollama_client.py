import os
import requests
from typing import Any, Dict, List, Optional

class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api").rstrip("/")
        self.text_model = os.getenv("OLLAMA_TEXT_MODEL", "qwen2.5:7b")
        self.vision_model = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "300"))

    def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model or self.text_model,
            "messages": [],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})

        # Ollama supports format="json" or a JSON schema in "format"
        if json_schema is not None:
            payload["format"] = json_schema

        r = requests.post(f"{self.base_url}/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content") or ""

    def chat_with_image_b64(
        self,
        prompt: str,
        image_b64: str,
        system: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.vision_model,
            "messages": [],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append(
            {"role": "user", "content": prompt, "images": [image_b64]}
        )

        if json_schema is not None:
            payload["format"] = json_schema

        r = requests.post(f"{self.base_url}/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content") or ""