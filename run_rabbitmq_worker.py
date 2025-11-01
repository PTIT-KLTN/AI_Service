"""
RabbitMQ Worker - Main entry point for AI Service RabbitMQ consumer.
Sử dụng ThreadPoolExecutor (multi-threading) - KHÔNG dùng async/await.
Run this script to start the AI Service as a RabbitMQ worker.
"""
import logging
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.rabbitmq.config import RabbitMQConfig
from app.rabbitmq.worker_threaded import ThreadedRabbitMQWorker
from app.rabbitmq.processor import RecipeAnalysisProcessor

# Configure logging with JSON format for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rabbitmq_worker.log', encoding='utf-8')
    ]
)

# Fix console encoding for Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

logger = logging.getLogger(__name__)


def print_banner():
    """Print startup banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║                    AI Service RabbitMQ Worker                             ║
║                    Multi-Threading (No Async)                             ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def main():
    """Main entry point for RabbitMQ worker."""
    print_banner()
    
    logger.info("=" * 80)
    logger.info("Starting AI Service RabbitMQ Worker (ThreadPoolExecutor)")
    logger.info("=" * 80)
    
    try:
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()
        
        # Initialize configuration
        config = RabbitMQConfig(
            amqp_url=os.getenv("AMQP_URL")  # Support AMQP_URL or individual params
        )
        
        # Validate configuration
        config.validate()
        
        # Log configuration
        logger.info("RabbitMQ Configuration:")
        logger.info(f"  {config}")
        logger.info(f"  Queue: {config.request_queue}")
        logger.info(f"  Worker Concurrency: {config.worker_concurrency}")
        logger.info(f"  Process Timeout: {config.process_timeout_sec}s")
        logger.info(f"  Message TTL: {config.message_ttl}ms")
        logger.info(f"  DLX: {config.results_dlx}")
        logger.info(f"  DLQ: {config.results_dlq}")
        logger.info("")
        
        # Initialize processor
        logger.info("Initializing RecipeAnalysisProcessor...")
        processor = RecipeAnalysisProcessor()
        logger.info("Processor initialized successfully")
        logger.info("")
        
        # Initialize and run worker
        logger.info("Initializing ThreadedRabbitMQWorker...")
        worker = ThreadedRabbitMQWorker(
            config=config,
            process_callback=processor.process_request
        )
        
        logger.info("Starting worker...")
        worker.run()
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Worker stopped by user (Ctrl+C)")
        sys.exit(0)
    
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"FATAL ERROR: {e}", exc_info=True)
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
