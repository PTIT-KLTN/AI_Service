"""
AWS Bedrock Guardrails Handler.
Handles INPUT validation using AWS Bedrock apply_guardrail() API.
"""
import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from app.utils.json_utils import extract_prompt_from_body


class AWSGuardrailHandler:
    """Handles AWS Bedrock Guardrail INPUT validation."""
    
    def __init__(
        self,
        runtime_client: Any,
        guardrail_config: Dict[str, str],
        environment: str,
        logger: Optional[logging.Logger] = None
    ):
        self.runtime = runtime_client
        self.guardrail_config = guardrail_config
        self.environment = environment
        self.logger = logger or logging.getLogger('ai_service.guardrails')
    
    def should_enable(self) -> bool:
        """Check if guardrails should be enabled."""
        if self.environment in {'prod', 'production'}:
            return True
        
        enabled_flag = os.getenv('ENABLE_GUARDRAILS', '').lower()
        return enabled_flag in {'1', 'true', 'yes'}
    
    def apply_input_guardrail(
        self,
        prompt_text: str,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Apply AWS guardrail to INPUT.
        
        Returns:
            None if guardrail passed
            Blocked response dict if guardrail blocked
        """
        if not self.should_enable():
            return None
        
        gid = guardrail_id or self.guardrail_config.get('guardrailIdentifier')
        gver = guardrail_version or self.guardrail_config.get('guardrailVersion')
        
        if not (gid and gver):
            return None
        
        try:
            self.logger.info(f"Applying guardrail to INPUT: {gid}:{gver}")
            
            guardrail_response = self.runtime.apply_guardrail(
                guardrailIdentifier=gid,
                guardrailVersion=gver,
                source='INPUT',
                content=[{
                    'text': {
                        'text': prompt_text
                    }
                }]
            )
            
            action = guardrail_response.get('action', 'NONE')
            
            # Check if truly blocked (not just ANONYMIZED for PII)
            assessments = guardrail_response.get('assessments', [])
            is_pii_only = self._is_pii_only_intervention(assessments)
            
            # Only block if it's a real dangerous content block, not just PII anonymization
            if action == 'GUARDRAIL_INTERVENED' and not is_pii_only:
                self.logger.warning(f"Guardrail blocked INPUT: {gid}:{gver}")
                return self._create_blocked_response(guardrail_response, prompt_text)
            
            if is_pii_only:
                self.logger.debug(f"Guardrail detected PII but allowing (anonymization only)")
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Guardrail INPUT check failed: {e}")
            return None
    
    def _is_pii_only_intervention(self, assessments: list) -> bool:
        """
        Check if guardrail intervention is ONLY for PII (not dangerous content).
        
        Returns:
            True if only PII detected (safe to allow)
            False if has other violations (should block)
        """
        if not assessments:
            return False
        
        has_pii = False
        has_other_violations = False
        
        for assessment in assessments:
            # Check for PII
            if 'sensitiveInformationPolicy' in assessment:
                pii_entities = assessment.get('sensitiveInformationPolicy', {}).get('piiEntities', [])
                if pii_entities:
                    # Check if all PII are just ANONYMIZED (not BLOCKED)
                    all_anonymized = all(
                        entity.get('action') == 'ANONYMIZED' 
                        for entity in pii_entities
                    )
                    if all_anonymized:
                        has_pii = True
                    else:
                        has_other_violations = True
            
            # Check for dangerous content
            if 'contentPolicy' in assessment:
                filters = assessment.get('contentPolicy', {}).get('filters', [])
                if filters:
                    has_other_violations = True
            
            # Check for denied topics
            if 'topicPolicy' in assessment:
                topics = assessment.get('topicPolicy', {}).get('topics', [])
                if topics:
                    has_other_violations = True
            
            # Check for word policy (profanity, custom words)
            if 'wordPolicy' in assessment:
                custom_words = assessment.get('wordPolicy', {}).get('customWords', [])
                managed_words = assessment.get('wordPolicy', {}).get('managedWordLists', [])
                if custom_words or managed_words:
                    has_other_violations = True
        
        # Only allow if ONLY PII detected (no other violations)
        return has_pii and not has_other_violations
    
    def _create_blocked_response(
        self,
        guardrail_response: Dict[str, Any],
        user_query: str
    ) -> Dict[str, Any]:
        """Create a response when AWS Guardrail blocks the input."""
        from .safe_completion_generator import SafeCompletionGenerator
        
        generator = SafeCompletionGenerator(logger=self.logger)
        safe_text = generator.generate_aws_blocked_completion(user_query)
        
        mock_response = {
            'body': io.BytesIO(json.dumps({
                "content": [{"type": "text", "text": safe_text}]
            }, ensure_ascii=False).encode('utf-8')),
            'ResponseMetadata': {
                'RequestId': guardrail_response.get('usage', {}).get('topicPolicyUnits', 'guardrail-blocked')
            },
            'guardrail': {
                'triggered': True,
                'action': 'block',
                'violation_count': 1,
                'violation_codes': ['aws_guardrail:input_blocked'],
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'source': 'AWS_BEDROCK_GUARDRAIL'
            }
        }
        
        return mock_response
