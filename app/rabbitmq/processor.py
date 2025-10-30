# RabbitMQ Request Processor
import json
import logging
from typing import Dict, Any

from app.main import ShoppingCartPipeline
from app.schemas import RecipeAnalysisRequest, RecipeAnalysisResponse
from app.services.s3_image_service import get_s3_image_service

logger = logging.getLogger(__name__)


class RecipeAnalysisProcessor:
    # Processes recipe analysis from RabbitMQ (supports text & image)
    
    def __init__(self):
        self.pipeline = ShoppingCartPipeline()
        self.s3_service = get_s3_image_service()
        logger.info("RecipeAnalysisProcessor initialized with S3 support")
    
    def process_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Parse JSON from user_input if needed
            if 'user_input' in request_data and isinstance(request_data['user_input'], str):
                user_input_str = request_data['user_input'].strip()
                if user_input_str.startswith('{') and 's3_url' in user_input_str:
                    try:
                        parsed = json.loads(user_input_str)
                        request_data.update(parsed)
                        request_data['user_input'] = None
                    except json.JSONDecodeError:
                        pass
            
            request = RecipeAnalysisRequest(**request_data)
            s3_url = request.s3_url or request.image_s3_url
            description = request.description or request.image_description or ""
            
            # Process image or text
            if s3_url:
                image_data = self.s3_service.download_image_as_base64(s3_url)
                if not image_data:
                    return {
                        "success": False,
                        "error": "Không thể tải ảnh từ S3",
                        "result": {"status": "error", "error": "Không thể tải ảnh từ S3", "error_type": "image_download_failed"}
                    }
                result = self.pipeline.process_image(s3_url=s3_url, description=description)
            elif request.user_input:
                result = self.pipeline.process(request.user_input)
            else:
                return {"success": False, "error": "Vui lòng cung cấp s3_url hoặc user_input"}
            
            response = RecipeAnalysisResponse(**result)
            response_dict = response.model_dump()
            status = response_dict.get('status', 'error')
            
            if status == 'success':
                return {"success": True, "result": response_dict}
            else:
                error_msg = response_dict.get('error', f"Processing failed: {status}")
                return {"success": False, "error": error_msg, "result": response_dict}
            
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return {"success": False, "error": f"Validation error: {str(e)}"}
        
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            return {"success": False, "error": f"Processing error: {str(e)}"}
