"""
Policy Handler for custom guardrail policies.
Handles OUTPUT validation using custom policy evaluation.
"""
import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.guardrails import GuardrailPolicyEvaluator
from app.utils.json_utils import extract_textual_content


class PolicyHandler:
    """Handles custom policy evaluation and content sanitization."""
    
    def __init__(
        self,
        policy_evaluator: GuardrailPolicyEvaluator,
        safe_completion_generator: Any,
        behavior_override: str = '',
        logger: Optional[logging.Logger] = None
    ):
        self.policy_evaluator = policy_evaluator
        self.safe_completion_generator = safe_completion_generator
        self.behavior_override = behavior_override
        self.logger = logger or logging.getLogger('ai_service.guardrails')
    
    def apply_policies(
        self,
        prompt_text: str,
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply custom policies to model response.
        
        Args:
            prompt_text: Original user prompt
            response: Model response dict
            
        Returns:
            Modified response with guardrail metadata
        """
        body_obj = response.get('body')
        if hasattr(body_obj, 'read'):
            raw_bytes = body_obj.read()
        else:
            raw_bytes = body_obj
        
        raw_text = raw_bytes.decode('utf-8') if isinstance(raw_bytes, bytes) else str(raw_bytes or '')
        
        analysis_text = extract_textual_content(raw_text)
        violations = self.policy_evaluator.evaluate(prompt_text, analysis_text)
        action = self._resolve_action(violations)
        
        sanitized_content = self._sanitize_content(
            raw_text, 
            violations, 
            action,
            user_query=prompt_text
        )
        
        guardrail_info = self._build_guardrail_metadata(violations, action, response)
        
        if violations:
            self._log_violations(guardrail_info)
        
        response['body'] = io.BytesIO(sanitized_content.encode('utf-8'))
        response['guardrail'] = guardrail_info
        
        if violations:
            response['guardrail_messages'] = self._format_violation_messages(violations)
        
        return response
    
    def _sanitize_content(
        self,
        raw_text: str,
        violations: List[Any],
        action: str,
        user_query: str = ""
    ) -> str:
        """Sanitize content based on violations and action."""
        if "Sorry, the model cannot answer this question" in raw_text:
            safe_text = self.safe_completion_generator.generate_aws_blocked_completion(user_query)
            return json.dumps({
                "content": [{"type": "text", "text": safe_text}]
            }, ensure_ascii=False)
        
        if not violations:
            return raw_text
        
        if action in {'block', 'safe-completion'}:
            safe_text = self.safe_completion_generator.generate_for_violations(
                user_query, violations, action
            )
            
            if not safe_text:
                safe_text = self.policy_evaluator.build_safe_completion(violations)
            
            return json.dumps({
                "content": [{"type": "text", "text": safe_text}]
            }, ensure_ascii=False)
        
        elif action == 'redact':
            redacted_text = self.policy_evaluator.redact_text(raw_text, violations)
            return json.dumps({
                "content": [{"type": "text", "text": redacted_text}]
            }, ensure_ascii=False)
        
        else:
            return raw_text
    
    def _resolve_action(self, violations: Optional[Any]) -> str:
        """Resolve action to take based on violations."""
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
    
    def _build_guardrail_metadata(
        self,
        violations: List[Any],
        action: str,
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build guardrail metadata for response."""
        violation_codes = []
        for violation in violations or []:
            policy_id = violation.policy_id or 'guardrail'
            rule_id = violation.rule_id or ''
            code = f"{policy_id}:{rule_id}".rstrip(':')
            violation_codes.append(code)
        
        metadata = {
            'triggered': bool(violations),
            'action': action,
            'violation_count': len(violations) if violations else 0,
            'violation_codes': violation_codes,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        
        request_id = self._extract_request_id(response)
        if request_id:
            metadata['request_id'] = request_id
        
        return metadata
    
    def _format_violation_messages(self, violations: List[Any]) -> List[Dict[str, Any]]:
        """Format violations for client response."""
        messages = []
        for violation in violations:
            messages.append({
                'message': violation.message,
                'severity': violation.severity or 'warning',
                'policy_id': violation.policy_id or 'guardrail',
            })
        return messages
    
    def _log_violations(self, guardrail_info: Dict[str, Any]) -> None:
        """Log guardrail violations."""
        environment = os.getenv('APP_ENV', 'dev').lower()
        log_payload = {
            'event': 'guardrail_violation',
            'request_id': guardrail_info.get('request_id'),
            'violation_types': guardrail_info.get('violation_codes', []),
            'action': guardrail_info.get('action'),
            'environment': environment,
            'timestamp': guardrail_info.get('timestamp'),
        }
        self.logger.warning(json.dumps(log_payload, ensure_ascii=False))
    
    def _extract_request_id(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract request ID from response metadata."""
        metadata = response.get('ResponseMetadata') or {}
        
        request_id = metadata.get('RequestId')
        if request_id:
            return str(request_id)
        
        headers = metadata.get('HTTPHeaders')
        if isinstance(headers, dict):
            request_id = headers.get('x-amzn-requestid') or headers.get('x-amz-request-id')
            if request_id:
                return str(request_id)
        
        return None
