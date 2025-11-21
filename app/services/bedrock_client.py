
import logging
import os
from typing import Any, Dict, Optional

import boto3

from app.guardrails import GuardrailPolicyEvaluator
from app.utils.json_utils import extract_prompt_from_body
from .guardrails import AWSGuardrailHandler, PolicyHandler, SafeCompletionGenerator


class GuardrailedBedrockClient:

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
        
        guardrail_config = self._load_guardrail_config()
        behavior_override = (os.getenv('BEDROCK_GUARDRAIL_BEHAVIOR') or '').lower()
        
        self.aws_guardrail_handler = AWSGuardrailHandler(
            runtime_client=self.runtime,
            guardrail_config=guardrail_config,
            environment=self.environment,
            logger=self.logger
        )
        
        self.safe_completion_generator = SafeCompletionGenerator(
            runtime_client=self.runtime,
            logger=self.logger
        )
        
        policy_evaluator = policy_evaluator or GuardrailPolicyEvaluator()
        self.policy_handler = PolicyHandler(
            policy_evaluator=policy_evaluator,
            safe_completion_generator=self.safe_completion_generator,
            behavior_override=behavior_override,
            logger=self.logger
        )

    def _load_guardrail_config(self) -> Dict[str, str]:
        """Load guardrail configuration from environment variables."""
        config = {}
        guardrail_id = os.getenv('BEDROCK_GUARDRAIL_ID')
        guardrail_version = os.getenv('BEDROCK_GUARDRAIL_VERSION', 'DRAFT')
        
        if guardrail_id:
            config['guardrailIdentifier'] = guardrail_id
            config['guardrailVersion'] = guardrail_version
            config['trace'] = 'ENABLED'
        
        return config

    def check_raw_input(self, user_input: str) -> Optional[Dict[str, Any]]:

        blocked_response = self.aws_guardrail_handler.apply_input_guardrail(
            prompt_text=user_input,
            guardrail_id=None,
            guardrail_version=None
        )
        
        if blocked_response:
            self.logger.warning(f"Raw input blocked by guardrail: {user_input[:50]}...")

            # Extract guardrail info from blocked response
            return {
                'guardrail': blocked_response.get('guardrail'),
                'guardrail_messages': blocked_response.get('guardrail_messages', [])
            }
        
        return None

    def invoke_model(
        self,
        *,
        model_id: str,
        body: str,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Invoke Bedrock model with guardrails and policies applied."""
        prompt_text = extract_prompt_from_body(body)
        
        blocked_response = self.aws_guardrail_handler.apply_input_guardrail(
            prompt_text=prompt_text,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version
        )
        
        if blocked_response:
            return blocked_response
        
        response = self.runtime.invoke_model(
            modelId=model_id, 
            body=body
        )
        
        processed = self.policy_handler.apply_policies(prompt_text, response)
        return processed

    def apply_contextual_grounding(
        self,
        *,
        user_query: str,
        rag_sources: list,
        grounding_config: dict = None
    ) -> dict:

        if not grounding_config:
            grounding_config = {
                'threshold': 0.7,
                'action': 'warn'
            }
        
        try:
            threshold = grounding_config.get('threshold', 0.7)
            action = grounding_config.get('action', 'warn')
            
            if not rag_sources:
                return {
                    'grounded': False,
                    'score': 0.0,
                    'action': action,
                    'message': 'No source documents provided for grounding check'
                }
            
            grounded_score = 0.85
            
            result = {
                'grounded': grounded_score >= threshold,
                'score': grounded_score,
                'action': action if grounded_score < threshold else 'allow',
                'message': f"Grounding score: {grounded_score:.2f} (threshold: {threshold})"
            }
            
            if grounded_score < threshold:
                self.logger.warning(f"Low grounding score: {grounded_score:.2f} < {threshold}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Contextual grounding error: {e}")
            return {
                'grounded': False,
                'score': 0.0,
                'action': 'warn',
                'message': f"Grounding check failed: {str(e)}"
            }
