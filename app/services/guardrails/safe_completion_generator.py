"""
Safe Completion Generator.
Generates safe completion messages for blocked/unsafe content using LLM.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional


class SafeCompletionGenerator:
    """Generates safe completion messages for policy violations."""
    
    def __init__(
        self,
        runtime_client: Optional[Any] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.runtime = runtime_client
        self.logger = logger or logging.getLogger('ai_service.guardrails')
    
    def is_enabled(self) -> bool:
        """Check if LLM safe completion is enabled."""
        enabled = os.getenv('ENABLE_LLM_SAFE_COMPLETION', '').lower()
        return enabled in {'1', 'true', 'yes'}
    
    def generate_for_violations(
        self,
        user_query: str,
        violations: List[Any],
        action: str
    ) -> Optional[str]:
        """
        Generate safe completion message for custom policy violations.
        
        Args:
            user_query: Original user query
            violations: List of policy violations
            action: Action to take (block, redact, safe-completion)
            
        Returns:
            Safe completion message or None if generation fails
        """
        if not self.is_enabled() or not self.runtime:
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
    
    def generate_aws_blocked_completion(self, user_query: str) -> str:
        """
        Generate safe completion message for AWS guardrail blocked content.
        
        Args:
            user_query: Original user query
            
        Returns:
            Safe completion message
        """
        if not self.is_enabled() or not self.runtime:
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
            
            return "Xin lỗi, câu hỏi của bạn vi phạm chính sách an toàn. Vui lòng đặt câu hỏi khác."
            
        except Exception as e:
            self.logger.warning(f"AWS blocked safe completion failed: {str(e)}")
            return "Xin lỗi, câu hỏi của bạn vi phạm chính sách an toàn. Vui lòng đặt câu hỏi khác."
    
    def _build_violation_context(self, violations: List[Any]) -> str:
        """Build violation context string for prompt."""
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
