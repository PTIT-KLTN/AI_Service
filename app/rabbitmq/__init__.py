"""
RabbitMQ integration module for AI Service.
Multi-threaded RPC worker (KHÔNG dùng async/await).
"""
from app.rabbitmq.config import RabbitMQConfig
from app.rabbitmq.worker_threaded import ThreadedRabbitMQWorker
from app.rabbitmq.processor import RecipeAnalysisProcessor

# Legacy imports (backward compatibility)
from app.rabbitmq.consumer import RecipeAnalysisConsumer

__all__ = [
    'RabbitMQConfig',
    'ThreadedRabbitMQWorker',
    'RecipeAnalysisProcessor',
    'RecipeAnalysisConsumer',  # Legacy
]

