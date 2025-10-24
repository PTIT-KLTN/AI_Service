"""
JSON utility functions for parsing and extracting data from various sources.
"""
import json
import boto3
from typing import Dict, Any, Optional

__all__ = [
    "read_json_from_s3_uri",
    "parse_json_content",
    "extract_textual_content",
    "extract_prompt_from_body",
]

# Initialize S3 client
s3 = boto3.client('s3')


def read_json_from_s3_uri(s3_uri: str) -> Dict[str, Any]:
    assert s3_uri.startswith('s3://'), f"Invalid S3 URI: {s3_uri}"
    _, _, path = s3_uri.partition('s3://')
    bucket, _, key = path.partition('/')
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj['Body'].read().decode('utf-8')
    return json.loads(body)


def parse_json_content(content: str) -> dict:
    # Remove code block markers if present
    if content.startswith('```'):
        content = '\n'.join(content.split('\n')[1:-1]).lstrip('json')
    
    try:
        data = json.loads(content)
    except Exception:
        fallback_warning = 'Kết quả mô hình không phải JSON hợp lệ.'
        return {
            "dish_name": None,
            "ingredients": [],
            "warnings": [fallback_warning],
            "response": content.strip() if isinstance(content, str) else None,
        }
    
    # Extract dish_name and ingredients
    dish_name = data.get('dish_name')
    ingredients = data.get('ingredients', []) if isinstance(data.get('ingredients', []), list) else []

    # Extract warnings
    warnings = data.get('warnings', []) if isinstance(data.get('warnings'), list) else []
    response_text = data.get('response') if isinstance(data.get('response'), str) else None
    
    return {
        "dish_name": dish_name,
        "ingredients": ingredients,
        "warnings": warnings,
        "response": response_text,
        "violations": data.get('violations') if isinstance(data.get('violations'), list) else [],
    }


def extract_textual_content(raw_text: str) -> str:
    try:
        data = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        return raw_text

    texts = []

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            texts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    _walk(data)
    return '\n'.join(texts) if texts else raw_text


def extract_prompt_from_body(body: str) -> str:
    if not body:
        return ''
    
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return ''

    prompt_parts = []
    if isinstance(payload, dict):
        # Direct prompt field
        if isinstance(payload.get('prompt'), str):
            prompt_parts.append(payload['prompt'])
        
        # Messages format
        messages = payload.get('messages')
        if isinstance(messages, list):
            for message in messages:
                content = message.get('content') if isinstance(message, dict) else None
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get('type') == 'text':
                            text = part.get('text')
                            if text:
                                prompt_parts.append(str(text))
                elif isinstance(content, str):
                    prompt_parts.append(content)
    
    return '\n'.join(prompt_parts)
