"""
RabbitMQ Request Processor - Business logic handler.
KHÔNG dùng async - chỉ synchronous processing.
Supports both original and optimized pipelines.
"""
import json
import logging
import time
import os
from typing import Dict, Any

from app.main import ShoppingCartPipeline
from app.schemas import RecipeAnalysisRequest, RecipeAnalysisResponse
from app.services.s3_image_service import get_s3_image_service

logger = logging.getLogger(__name__)


class RecipeAnalysisProcessor:
    
    def __init__(self, use_optimized: bool = False):
        """Initialize processor với pipeline và services."""
        try:
            self.use_optimized = use_optimized
            
            if use_optimized:
                # Import optimized pipeline
                try:
                    from app.main_optimized import OptimizedShoppingCartPipeline
                    
                    cache_ttl = int(os.getenv('RECIPE_CACHE_TTL', '3600'))
                    cache_maxsize = int(os.getenv('RECIPE_CACHE_MAXSIZE', '1000'))
                    max_workers = int(os.getenv('OPTIMIZED_MAX_WORKERS', '3'))
                    
                    self.pipeline = OptimizedShoppingCartPipeline(
                        max_workers=max_workers,
                        recipe_cache_ttl=cache_ttl
                    )
                    logger.info(f"✅ Optimized pipeline initialized (TTL={cache_ttl}s, MaxSize={cache_maxsize}, Workers={max_workers})")
                except ImportError as e:
                    logger.error(f"Failed to import OptimizedShoppingCartPipeline: {e}")
                    logger.info("Falling back to original pipeline")
                    self.pipeline = ShoppingCartPipeline()
                    self.use_optimized = False
            else:
                self.pipeline = ShoppingCartPipeline()
                logger.info("✅ Original pipeline initialized")
            
            self.s3_service = get_s3_image_service()
            logger.info("RecipeAnalysisProcessor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RecipeAnalysisProcessor: {e}", exc_info=True)
            raise
    
    def process_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Xử lý request và trả về response.
        
        Args:
            request_data: Request payload từ RabbitMQ
            
        Returns:
            Response dict với format:
            {
                'success': bool,
                'result': dict,  # nếu success
                'error': str,    # nếu fail
            }
        """
        start_time = time.time()
        start_time = time.time()
        
        logger.info(f"Processing request: {json.dumps(request_data, ensure_ascii=False)[:200]}")
        
        try:
            # Parse và validate request
            # Handle nested JSON string in user_input
            if 'user_input' in request_data and isinstance(request_data['user_input'], str):
                user_input_str = request_data['user_input'].strip()
                if user_input_str.startswith('{') and 's3_url' in user_input_str:
                    try:
                        parsed = json.loads(user_input_str)
                        request_data.update(parsed)
                        request_data['user_input'] = None
                    except json.JSONDecodeError:
                        pass
            
            # Validate với Pydantic
            try:
                request = RecipeAnalysisRequest(**request_data)
            except Exception as e:
                logger.error(f"Request validation error: {e}")
                return {
                    "success": False,
                    "error": f"Invalid request format: {str(e)}",
                    "error_type": "validation_error"
                }
            
            # Extract parameters
            s3_url = request.s3_url or request.image_s3_url
            description = request.description or request.image_description or ""
            user_input = request.user_input
            
            # Process based on input type
            if s3_url:
                # Image processing
                logger.info(f"Processing image from S3: {s3_url}")
                result = self._process_image(s3_url, description)
            
            elif user_input:
                # Text processing
                logger.info(f"Processing text input: {user_input[:100]}...")
                result = self._process_text(user_input)
            
            else:
                logger.error("No input provided (neither s3_url nor user_input)")
                return {
                    "success": False,
                    "error": "Vui lòng cung cấp s3_url hoặc user_input",
                    "error_type": "missing_input"
                }
            
            # Validate response
            try:
                response = RecipeAnalysisResponse(**result)
                response_dict = response.model_dump()
            except Exception as e:
                logger.error(f"Response validation error: {e}")
                return {
                    "success": False,
                    "error": f"Response validation error: {str(e)}",
                    "error_type": "response_validation_error",
                    "result": result  # Include raw result for debugging
                }
            
            # Check status
            status = response_dict.get('status', 'error')
            
            # Calculate processing time
            elapsed_ms = int((time.time() - start_time) * 1000)
            response_dict['processing_time_ms'] = elapsed_ms
            
            if status == 'success':
                logger.info(f"Request processed successfully in {elapsed_ms}ms")
                return {
                    "success": True,
                    "result": response_dict
                }
            else:
                error_msg = response_dict.get('error', f"Processing failed with status: {status}")
                logger.warning(f"Request processing failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": status,
                    "result": response_dict
                }
        
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Unexpected error in process_request: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected processing error: {str(e)}",
                "error_type": "unexpected_error",
                "processing_time_ms": elapsed_ms
            }
    
    def _process_image(self, s3_url: str, description: str = "") -> Dict[str, Any]:
        """
        Process image từ S3.
        
        Args:
            s3_url: S3 URL của ảnh
            description: Mô tả bổ sung (optional)
            
        Returns:
            Result dict từ pipeline
        """
        try:
            # Download image từ S3
            image_data = self.s3_service.download_image_as_base64(s3_url)
            
            if not image_data:
                logger.error(f"Failed to download image from S3: {s3_url}")
                return {
                    'status': 'error',
                    'error': 'Không thể tải ảnh từ S3',
                    'error_type': 'image_download_failed',
                    'dish': {'name': ''},
                    'cart': None,
                    'suggestions': [],
                    'similar_dishes': [],
                    'excluded_ingredients': [],
                    'warnings': [],
                    'insights': [],
                    'guardrail': None,
                }
            
            # Process với pipeline
            logger.info(f"Image downloaded successfully, processing with pipeline...")
            result = self.pipeline.process_image(
                s3_url=s3_url,
                description=description
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in _process_image: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': f'Image processing error: {str(e)}',
                'error_type': 'image_processing_error',
                'dish': {'name': ''},
                'cart': None,
                'suggestions': [],
                'similar_dishes': [],
                'excluded_ingredients': [],
                'warnings': [],
                'insights': [],
                'guardrail': None,
            }
    
    def _process_text(self, user_input: str) -> Dict[str, Any]:
        """
        Process text input.
        
        Args:
            user_input: User input text
            
        Returns:
            Result dict từ pipeline
        """
        try:
            logger.info(f"Processing text with pipeline...")
            result = self.pipeline.process(user_input)
            return result
            
        except Exception as e:
            logger.error(f"Error in _process_text: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': f'Text processing error: {str(e)}',
                'error_type': 'text_processing_error',
                'dish': {'name': ''},
                'cart': None,
                'suggestions': [],
                'similar_dishes': [],
                'excluded_ingredients': [],
                'warnings': [],
                'insights': [],
                'guardrail': None,
            }

