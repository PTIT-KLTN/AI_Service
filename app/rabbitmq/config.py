"""
RabbitMQ configuration for AI Service.
"""
import os
from typing import Optional

class RabbitMQConfig:
    """RabbitMQ connection configuration."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        virtual_host: Optional[str] = None
    ):
        self.host = host or os.getenv("RABBITMQ_HOST", "localhost")
        self.port = port or int(os.getenv("RABBITMQ_PORT", "5672"))
        self.username = username or os.getenv("RABBITMQ_USERNAME", "guest")
        self.password = password or os.getenv("RABBITMQ_PASSWORD", "guest")
        self.virtual_host = virtual_host or os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
        
        # Queue names
        self.request_queue = "recipe_analysis_request"
        
    def get_connection_params(self) -> dict:
        """Get connection parameters for pika."""
        import pika
        
        credentials = pika.PlainCredentials(self.username, self.password)
        
        return {
            "host": self.host,
            "port": self.port,
            "virtual_host": self.virtual_host,
            "credentials": credentials,
            "heartbeat": 600,
            "blocked_connection_timeout": 300
        }
