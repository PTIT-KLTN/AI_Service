import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, List

import boto3

from app.guardrails import GuardrailPolicyEvaluator
from app.utils.json_utils import extract_prompt_from_body, extract_textual_content


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
        self.policy_evaluator = policy_evaluator or GuardrailPolicyEvaluator()
        
        # Guardrail configuration from environment
        self.guardrail_config = self._load_guardrail_config()
        self.behavior_override = (os.getenv('BEDROCK_GUARDRAIL_BEHAVIOR') or '').lower()

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

    def invoke_model(
        self,
        *,
        model_id: str,
        body: str,
        guardrail_id: Optional[str] = None,
        guardrail_version: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:

        # Build guardrail configuration
        guardrail_params = self._build_guardrail_params(guardrail_id, guardrail_version)
        
        # Merge with invoke kwargs
        invoke_kwargs = {**kwargs, **guardrail_params}
        
        # Invoke model
        response = self.runtime.invoke_model(
            modelId=model_id, 
            body=body, 
            **invoke_kwargs
        )
        
        # Apply custom policy checks and process response
        prompt_text = extract_prompt_from_body(body)
        processed = self._apply_custom_policies(prompt_text, response)

        return processed

    def _build_guardrail_params(
        self, 
        guardrail_id: Optional[str] = None, 
        guardrail_version: Optional[str] = None
    ) -> Dict[str, str]:

        if not self._should_enable_guardrails():
            return {}
        
        # Use provided values or defaults from config
        params = {}
        gid = guardrail_id or self.guardrail_config.get('guardrailIdentifier')
        gver = guardrail_version or self.guardrail_config.get('guardrailVersion')
        
        if gid and gver:
            params['guardrailIdentifier'] = gid
            params['guardrailVersion'] = gver
            params['trace'] = 'ENABLED'
        
        return params

    def _should_enable_guardrails(self) -> bool:
        # Always enable in production
        if self.environment in {'prod', 'production'}:
            return True
        
        # Check explicit flag in non-prod environments
        enabled_flag = os.getenv('ENABLE_GUARDRAILS', '').lower()
        return enabled_flag in {'1', 'true', 'yes'}

    def _apply_custom_policies(self, prompt_text: str, response: Dict[str, Any]) -> Dict[str, Any]:

        # Extract response body
        body_obj = response.get('body')
        if hasattr(body_obj, 'read'):
            raw_bytes = body_obj.read()
        else:
            raw_bytes = body_obj
        
        raw_text = raw_bytes.decode('utf-8') if isinstance(raw_bytes, bytes) else str(raw_bytes or '')
        
        # Evaluate content against custom policies
        analysis_text = extract_textual_content(raw_text)
        violations = self.policy_evaluator.evaluate(prompt_text, analysis_text)
        action = self._resolve_action(violations)

        # Apply content modifications based on violations
        sanitized_content = self._sanitize_content(
            raw_text, 
            violations, 
            action,
            user_query=prompt_text
        )
        
        # Build guardrail metadata
        guardrail_info = self._build_guardrail_metadata(violations, action, response)
        
        # Log violations if any
        if violations:
            self._log_violations(guardrail_info)
        
        # Reconstruct response with sanitized content
        response['body'] = io.BytesIO(sanitized_content.encode('utf-8'))
        response['guardrail'] = guardrail_info
        
        # Add violation details for client
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

        # Check if AWS Guardrails blocked this request
        if "Sorry, the model cannot answer this question" in raw_text:
            safe_text = self._generate_aws_blocked_completion(user_query)
            return json.dumps({
                "content": [{"type": "text", "text": safe_text}]
            }, ensure_ascii=False)
        
        # Handle local policy violations
        if not violations:
            return raw_text
        
        if action in {'block', 'safe-completion'}:
            # Safe-completion message
            safe_text = self._generate_safe_completion_llm(user_query, violations, action)
            
            # Default
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

    def _build_guardrail_metadata(
        self, 
        violations: List[Any], 
        action: str, 
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        
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
        messages = []
        for violation in violations:
            messages.append({
                'message': violation.message,
                'severity': violation.severity or 'warning',
                'policy_id': violation.policy_id or 'guardrail',
            })
        return messages

    def _log_violations(self, guardrail_info: Dict[str, Any]) -> None:
        log_payload = {
            'event': 'guardrail_violation',
            'request_id': guardrail_info.get('request_id'),
            'violation_types': guardrail_info.get('violation_codes', []),
            'action': guardrail_info.get('action'),
            'environment': self.environment,
            'timestamp': guardrail_info.get('timestamp'),
        }
        self.logger.warning(json.dumps(log_payload, ensure_ascii=False))

    def _resolve_action(self, violations: Optional[Any]) -> str:
        if not violations:
            return 'allow'

        actions = {violation.action for violation in violations}
        
        # Check for behavior override
        if self.behavior_override in {'block', 'redact', 'safe-completion'}:
            override = self.behavior_override

            if override == 'redact' and 'redact' not in actions:
                return 'safe-completion'
            return override

        # Resolve based on violation actions (priority order)
        if 'block' in actions:
            return 'block'
        if 'safe-completion' in actions:
            return 'safe-completion'
        if 'redact' in actions:
            return 'redact'
        
        return 'safe-completion'

    def _extract_request_id(self, response: Dict[str, Any]) -> Optional[str]:
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
    
    def _generate_safe_completion_llm(
        self, 
        user_query: str, 
        violations: List[Any], 
        action: str
    ) -> Optional[str]:

        if not self._is_llm_safe_completion_enabled():
            return None
        
        try:
            violation_context = self._build_violation_context(violations)
            model_id = os.getenv('SAFE_COMPLETION_MODEL', 'anthropic.claude-3-haiku-20240307-v1:0')
            
            system_prompt = """Bạn là trợ lý an toàn thực phẩm thân thiện và chuyên nghiệp.
                            Nhiệm vụ: Giải thích tại sao câu hỏi của người dùng vi phạm chính sách an toàn, và đề xuất cách tiếp cận an toàn hơn.

                            Quy tắc:
                            - Giọng điệu: Lịch sự, thấu hiểu, không phán xét
                            - Độ dài: 2-3 câu ngắn gọn
                            - Cấu trúc: (1) Giải thích ngắn gọn vấn đề an toàn, (2) Đề xuất thay thế nếu có
                            - KHÔNG lặp lại nội dung nguy hiểm
                            - Tập trung vào giáo dục, không đe dọa"""

            user_prompt = f"""Câu hỏi của người dùng: {user_query}

                            Vi phạm phát hiện:
                            {violation_context}

                            Hãy tạo câu trả lời an toàn, giúp người dùng hiểu vấn đề và đề xuất giải pháp thay thế."""

            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": user_prompt}],
                "system": system_prompt
            }
            
            response = self.runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body, ensure_ascii=False).encode('utf-8')
            )
            
            response_body = response.get('body')
            if hasattr(response_body, 'read'):
                response_bytes = response_body.read()
            else:
                response_bytes = response_body
            
            response_json = json.loads(response_bytes)
            content_blocks = response_json.get('content', [])
            
            if content_blocks and len(content_blocks) > 0:
                safe_text = content_blocks[0].get('text', '').strip()
                if safe_text:
                    self.logger.info(f"LLM safe completion generated ({len(safe_text)} chars)")
                    return safe_text
            
            return None
            
        except Exception as e:
            self.logger.warning(f"LLM safe completion failed: {str(e)}")
            return None
    
    def _is_llm_safe_completion_enabled(self) -> bool:
        enabled = os.getenv('ENABLE_LLM_SAFE_COMPLETION', '').lower()
        return enabled in {'1', 'true', 'yes'}
    
    def _build_violation_context(self, violations: List[Any]) -> str:
        if not violations:
            return "Không có vi phạm cụ thể"
        
        context_lines = []
        for i, violation in enumerate(violations, 1):
            policy = violation.policy_id or "chính sách chung"
            rule = violation.rule_id or "quy tắc chung"
            severity = violation.severity or "medium"
            message = violation.message or "Vi phạm không xác định"
            
            context_lines.append(
                f"{i}. [{policy}/{rule}] ({severity}): {message}"
            )
        
        return "\n".join(context_lines)
    
    def _generate_aws_blocked_completion(self, user_query: str) -> str:

        if not self._is_llm_safe_completion_enabled():
            return "Xin lỗi, câu hỏi của bạn vi phạm chính sách an toàn. Vui lòng đặt câu hỏi khác."
        
        try:
            model_id = os.getenv('SAFE_COMPLETION_MODEL', 'anthropic.claude-3-haiku-20240307-v1:0')

            system_prompt = """Bạn là chuyên gia an toàn thực phẩm và dinh dưỡng.

                            Nhiệm vụ: Giải thích ngắn gọn TẠI SAO câu hỏi vi phạm chính sách an toàn, và đề xuất thay thế an toàn.

                            QUY TẮC QUAN TRỌNG:
                            1. Độ dài: TỐI ĐA 2-3 câu ngắn gọn, đi thẳng vào vấn đề
                            2. Cấu trúc: (1) Giải thích ngắn vấn đề an toàn, (2) Đề xuất thay thế/giải pháp an toàn
                            3. PHẢI có trích dẫn nguồn tin cậy (WHO, Bộ Y tế, FDA, CDC, Mayo Clinic, nghiên cứu khoa học)
                            4. Giọng điệu: Lịch sự, thấu hiểu, giáo dục, KHÔNG phán xét
                            5. TRÁNH: Lặp lại nội dung nguy hiểm, chi tiết không cần thiết, giải thích dài dòng

                            Ví dụ tốt:
                            "Việc sử dụng javel trong nấu ăn cực kỳ nguy hiểm vì có thể gây ngộ độc nghiêm trọng (theo CDC). Thay vào đó, bạn nên dùng các phương pháp khử trùng thực phẩm an toàn như luộc sôi hoặc ngâm nước muối theo hướng dẫn của Bộ Y tế. Tham khảo: https://www.cdc.gov/foodsafety"

                            Ví dụ XẤU (quá dài, không có nguồn):
                            "Xin lỗi bạn nhưng việc sử dụng javel trong nấu ăn là một ý tưởng rất nguy hiểm. Javel chứa sodium hypochlorite là hóa chất tẩy rửa công nghiệp, không phải thực phẩm. Nếu ăn vào có thể gây..."
                            """

            user_prompt = f"""Câu hỏi của người dùng: "{user_query}"

                            AWS Bedrock Guardrails đã chặn câu hỏi này vì vi phạm chính sách an toàn.

                            Hãy giải thích NGẮN GỌN (2-3 câu) tại sao câu hỏi này không an toàn, đề xuất thay thế, và PHẢI có trích dẫn nguồn tin cậy."""

            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 250, 
                "temperature": 0.7,
                "messages": [{"role": "user", "content": user_prompt}],
                "system": system_prompt
            }
            
            response = self.runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body, ensure_ascii=False).encode('utf-8')
            )
            
            response_body = response.get('body')
            if hasattr(response_body, 'read'):
                response_bytes = response_body.read()
            else:
                response_bytes = response_body
            
            response_json = json.loads(response_bytes)
            content_blocks = response_json.get('content', [])
            
            if content_blocks and len(content_blocks) > 0:
                safe_text = content_blocks[0].get('text', '').strip()
                if safe_text:
                    self.logger.info(f"AWS blocked - LLM safe completion generated ({len(safe_text)} chars)")
                    return safe_text
            
            return "Câu hỏi của bạn vi phạm chính sách an toàn thực phẩm. Vui lòng tham khảo hướng dẫn an toàn từ Bộ Y tế Việt Nam hoặc WHO."
            
        except Exception as e:
            self.logger.warning(f"AWS blocked completion generation failed: {str(e)}")
            return "Câu hỏi của bạn vi phạm chính sách an toàn. Vui lòng đặt câu hỏi khác hoặc tham khảo hướng dẫn từ các cơ quan y tế."
    
    def apply_contextual_grounding(
        self, 
        source_text: str, 
        user_query: str, 
        model_output: str
    ) -> Dict[str, Any]:
        
        # Check if guardrail is configured
        guardrail_id = self.guardrail_config.get('guardrailIdentifier')
        guardrail_version = self.guardrail_config.get('guardrailVersion')
        
        if not (guardrail_id and guardrail_version):
            return {
                "skipped": True, 
                "reason": "no-guardrail-config",
                "message": "Guardrail not configured. Set BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION."
            }

        # Build content blocks with qualifiers for contextual grounding
        content = [
            {
                "text": {
                    "text": source_text, 
                    "qualifiers": ["grounding_source"]
                }
            },
            {
                "text": {
                    "text": user_query,  
                    "qualifiers": ["query"]
                }
            },
            {
                "text": {
                    "text": model_output,
                    "qualifiers": ["guard_content"]
                }
            },
        ]
        
        try:
            response = self.runtime.apply_guardrail(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=guardrail_version,
                source="OUTPUT",
                content=content,
            )
            return response
        except Exception as e:
            self.logger.error(f"ApplyGuardrail API failed: {str(e)}")
            return {
                "error": True,
                "reason": "api-error",
                "message": str(e)
            }