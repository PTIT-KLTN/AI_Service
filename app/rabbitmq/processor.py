"""
RabbitMQ Request Processor - Integrates ShoppingCartPipeline with RabbitMQ Consumer.
"""
import logging
from typing import Dict, Any

from app.main import ShoppingCartPipeline
from app.schemas import RecipeAnalysisRequest, RecipeAnalysisResponse

logger = logging.getLogger(__name__)


class RecipeAnalysisProcessor:
    """
    Processes recipe analysis requests from RabbitMQ.
    Integrates ShoppingCartPipeline with the RabbitMQ consumer.
    """
    
    def __init__(self):
        """Initialize the processor with ShoppingCartPipeline."""
        self.pipeline = ShoppingCartPipeline()
        logger.info("RecipeAnalysisProcessor initialized")
    
    def process_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a recipe analysis request.
        
        Args:
            request_data: Dictionary containing 'user_input' field
            
        Returns:
            Dictionary wrapped in Main Service expected format:
            {
                "success": true/false,
                "result": { RecipeAnalysisResponse } or "error": "message"
            }
        """
        try:
            request = RecipeAnalysisRequest(**request_data)
            logger.info(f"Processing request: {request.user_input}")
            
            result = self.pipeline.process(request.user_input)
            
            response = RecipeAnalysisResponse(**result)
            response_dict = response.model_dump()
            
            status = response_dict.get('status', 'error')
            is_success = status == 'success'
            
            if is_success:
                logger.info(f"Successfully processed request")
                return {
                    "success": True,
                    "result": response_dict
                }
            else:
                error_msg = response_dict.get('error', f"Processing failed with status: {status}")
                logger.warning(f"Processing not successful: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "result": response_dict  # Include full result for debugging
                }
            
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return {
                "success": False,
                "error": f"Validation error: {str(e)}"
            }
        
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing error: {str(e)}"
            }
