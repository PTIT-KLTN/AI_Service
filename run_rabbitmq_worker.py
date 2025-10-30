"""
RabbitMQ Worker - Main entry point for AI Service RabbitMQ consumer.
Run this script to start the AI Service as a RabbitMQ consumer.
"""
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.rabbitmq.config import RabbitMQConfig
from app.rabbitmq.consumer import RecipeAnalysisConsumer
from app.rabbitmq.processor import RecipeAnalysisProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rabbitmq_worker.log')
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for RabbitMQ worker."""
    logger.info("=" * 80)
    logger.info("Starting AI Service RabbitMQ Worker")
    logger.info("=" * 80)
    
    try:
        # Initialize configuration
        config = RabbitMQConfig()
        logger.info(f"RabbitMQ Configuration:")
        logger.info(f"  Host: {config.host}:{config.port}")
        logger.info(f"  Virtual Host: {config.virtual_host}")
        logger.info(f"  Request Queue: {config.request_queue}")
        
        # Initialize processor
        processor = RecipeAnalysisProcessor()
        
        # Initialize and run consumer
        consumer = RecipeAnalysisConsumer(
            config=config,
            process_callback=processor.process_request
        )
        
        logger.info("Starting consumer...")
        consumer.run()
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user (Ctrl+C)")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"Fatal error in worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
