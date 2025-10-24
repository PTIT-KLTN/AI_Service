import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, List

import boto3

from app.guardrails import GuardrailPolicyEvaluator
from app.utils.json_utils import extract_prompt_from_body, extract_textual_content


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
        prompt_text = extract_prompt_from_body(body)
        processed = self._apply_guardrails(prompt_text, response)

        return processed

    def _guardrails_enabled(self, guardrail_id: Optional[str], guardrail_version: Optional[str]) -> bool:
        if not guardrail_id or not guardrail_version:
            return False
        if self.environment in {'prod', 'production'}:
            return True
        enabled_flag = os.getenv('ENABLE_GUARDRAILS')
        return enabled_flag == '1' or (enabled_flag or '').lower() in {'true', 'yes'}

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

        analysis_text = extract_textual_content(raw_text)
        violations = self.policy_evaluator.evaluate(prompt_text, analysis_text)
        action = self._resolve_action(violations)

        try:
            original_json = json.loads(raw_text)
        except Exception:
            original_json = None

        if violations:
            if action in {'block', 'safe-completion'}:
                safe_text = self.policy_evaluator.build_safe_completion(violations)
                sanitized_json = {
                    "content": [
                        {"type": "text", "text": safe_text}
                    ]
                }
                sanitized_bytes = json.dumps(sanitized_json, ensure_ascii=False).encode("utf-8")
                sanitized_text = None 
            elif action == 'redact':
                redacted_text = self.policy_evaluator.redact_text(raw_text, violations)
                sanitized_json = {
                    "content": [
                        {"type": "text", "text": redacted_text}
                    ]
                }
                sanitized_bytes = json.dumps(sanitized_json, ensure_ascii=False).encode("utf-8")
                sanitized_text = None
            else:
                sanitized_json = original_json
                sanitized_bytes = None
        else:
            sanitized_json = original_json
            sanitized_bytes = None

        violation_codes: List[str] = []
        violation_messages: List[Dict[str, Any]] = []
        for violation in violations or []:
            policy_id = violation.policy_id or 'guardrail'
            rule_id = violation.rule_id or ''
            code = f"{policy_id}:{rule_id}".rstrip(':')
            violation_codes.append(code)
            violation_messages.append({
                'message': violation.message,
                'severity': violation.severity or 'warning',
                'policy_id': policy_id,
            })

        guardrail_info = {
            'triggered': bool(violations),
            'action': action,
            'violation_count': len(violations) if violations else 0,
            'violation_codes': violation_codes,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        request_id = self._request_id_from_response(response)
        if request_id:
            guardrail_info['request_id'] = request_id

        if violations:
            log_payload = {
                'event': 'guardrail_violation',
                'request_id': request_id,
                'violation_types': violation_codes,
                'action': action,
                'environment': self.environment,
                'timestamp': guardrail_info['timestamp'],
            }
            self.logger.warning(json.dumps(log_payload, ensure_ascii=False))

        # Build response
        if sanitized_bytes is not None:
            response['body'] = io.BytesIO(sanitized_bytes)
        elif sanitized_json is not None:
            response['body'] = io.BytesIO(json.dumps(sanitized_json, ensure_ascii=False).encode("utf-8"))
        else:
            response['body'] = io.BytesIO((raw_text or "").encode("utf-8"))

        response['guardrail'] = guardrail_info
        if violation_messages:
            response['guardrail_messages'] = violation_messages
        return response

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
    
    def apply_contextual_grounding(self, source_text: str, user_query: str, model_output: str) -> dict:

        g_id = os.getenv("BEDROCK_GUARDRAIL_ID")
        g_ver = os.getenv("BEDROCK_GUARDRAIL_VERSION")
        if not (g_id and g_ver):
            return {"skipped": True, "reason": "no-guardrail-config"}

        content = [
            {"text": {"text": source_text, "qualifiers": ["grounding_source"]}},
            {"text": {"text": user_query,  "qualifiers": ["query"]}},
            {"text": {"text": model_output,"qualifiers": ["guard_content"]}},
        ]
        return self.runtime.apply_guardrail(
            guardrailIdentifier=g_id,
            guardrailVersion=g_ver,
            source="OUTPUT",
            content=content,
            outputScope="INTERVENTIONS"
        )