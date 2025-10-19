import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import boto3

from app.guardrails import GuardrailPolicyEvaluator


class GuardrailViolationError(RuntimeError):
    """Raised when guardrail policy blocks a request."""


class GuardrailedBedrockClient:
    """Wrapper around the Bedrock runtime client with guardrail enforcement."""

    def __init__(
        self,
        region: str = 'us-east-1',
        runtime_client: Optional[Any] = None,
        policy_evaluator: Optional[GuardrailPolicyEvaluator] = None,
        logger: Optional[logging.Logger] = None,
        environment: Optional[str] = None,
    ) -> None:
        self.environment = environment or os.getenv('APP_ENV', 'dev').lower()
        self.logger = logger or logging.getLogger('ai_service.guardrails')
        self.runtime = runtime_client or boto3.client('bedrock-runtime', region_name=region)
        self.policy_evaluator = policy_evaluator or GuardrailPolicyEvaluator()
        self.default_guardrail_id = os.getenv('BEDROCK_GUARDRAIL_ID')
        self.default_guardrail_version = os.getenv('BEDROCK_GUARDRAIL_VERSION')
        self.behavior_override = (os.getenv('BEDROCK_GUARDRAIL_BEHAVIOR') or '').lower()

    def invoke_model(
        self,
        *,
        model_id: str,
        body: str,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        guardrail_id = guardrail_id or self.default_guardrail_id
        guardrail_version = guardrail_version or self.default_guardrail_version
        enabled = self._guardrails_enabled(guardrail_id, guardrail_version)

        invoke_kwargs = dict(kwargs)
        if enabled:
            invoke_kwargs.setdefault('guardrailIdentifier', guardrail_id)
            invoke_kwargs.setdefault('guardrailVersion', guardrail_version)

        response = self.runtime.invoke_model(modelId=model_id, body=body, **invoke_kwargs)
        prompt_text = self._extract_prompt_from_body(body)
        processed = self._apply_guardrails(prompt_text, response)

        return processed

    def _guardrails_enabled(self, guardrail_id: Optional[str], guardrail_version: Optional[str]) -> bool:
        if not guardrail_id or not guardrail_version:
            return False
        if self.environment in {'prod', 'production'}:
            return True
        enabled_flag = os.getenv('ENABLE_GUARDRAILS')
        return enabled_flag == '1' or (enabled_flag or '').lower() in {'true', 'yes'}

    def _extract_prompt_from_body(self, body: str) -> str:
        if not body:
            return ''
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return ''

        prompt_parts = []
        if isinstance(payload, dict):
            if isinstance(payload.get('prompt'), str):
                prompt_parts.append(payload['prompt'])
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

    def _apply_guardrails(self, prompt_text: str, response: Dict[str, Any]) -> Dict[str, Any]:
        body_obj = response.get('body')
        if hasattr(body_obj, 'read'):
            raw = body_obj.read()
        else:
            raw = body_obj
        if isinstance(raw, bytes):
            raw_text = raw.decode('utf-8')
        else:
            raw_text = str(raw or '')

        analysis_text = self._extract_textual_content(raw_text)
        violations = self.policy_evaluator.evaluate(prompt_text, analysis_text)
        action = self._resolve_action(violations)
        sanitized_text = raw_text

        if violations:
            if action in {'block', 'safe-completion'}:
                sanitized_text = self.policy_evaluator.build_safe_completion(violations)
            elif action == 'redact':
                sanitized_text = self.policy_evaluator.redact_text(raw_text, violations)

        guardrail_info = {
            'enabled': bool(violations),
            'action': action,
            'violations': [violation.to_dict() for violation in violations],
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }

        request_id = self._request_id_from_response(response)
        if violations:
            log_payload = {
                'event': 'guardrail_violation',
                'request_id': request_id,
                'violation_types': [f"{v.policy_id}:{v.rule_id}" for v in violations],
                'action': action,
                'environment': self.environment,
                'timestamp': guardrail_info['timestamp'],
            }
            self.logger.warning(json.dumps(log_payload, ensure_ascii=False))

        response['body'] = io.BytesIO(sanitized_text.encode('utf-8'))
        response['guardrail'] = guardrail_info
        if request_id:
            response['guardrail']['request_id'] = request_id

        return response

    def _extract_textual_content(self, raw_text: str) -> str:
        try:
            data = json.loads(raw_text)
        except (TypeError, json.JSONDecodeError):
            return raw_text

        texts: list[str] = []

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

    def _resolve_action(self, violations: Optional[Any]) -> str:
        if not violations:
            return 'allow'

        actions = {violation.action for violation in violations}
        if self.behavior_override in {'block', 'redact', 'safe-completion'}:
            override = self.behavior_override
            if override == 'redact' and 'redact' not in actions:
                return 'safe-completion'
            return override

        if 'block' in actions:
            return 'block'
        if 'safe-completion' in actions:
            return 'safe-completion'
        if 'redact' in actions:
            return 'redact'
        return 'safe-completion'

    def _request_id_from_response(self, response: Dict[str, Any]) -> Optional[str]:
        metadata = response.get('ResponseMetadata') or {}
        request_id = metadata.get('RequestId')
        if request_id:
            return str(request_id)
        headers = metadata.get('HTTPHeaders') if isinstance(metadata, dict) else None
        if headers:
            request_id = headers.get('x-amzn-requestid') or headers.get('x-amz-request-id')
            if request_id:
                return str(request_id)
        return None