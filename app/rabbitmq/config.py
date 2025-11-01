"""
RabbitMQ configuration for AI Service with multi-threading support.
Không sử dụng async/await - chỉ dùng ThreadPoolExecutor.
"""
import os
from typing import Optional


class RabbitMQConfig:
    """RabbitMQ connection configuration cho worker với thread pool."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        virtual_host: Optional[str] = None,
        amqp_url: Optional[str] = None
    ):
        # Connection parameters
        if amqp_url:
            # Parse AMQP_URL nếu được cung cấp
            self.amqp_url = amqp_url
            # Pika sẽ parse URL này
        else:
            self.host = host or os.getenv("RABBITMQ_HOST", "localhost")
            self.port = port or int(os.getenv("RABBITMQ_PORT", "5672"))
            self.username = username or os.getenv("RABBITMQ_USERNAME", "guest")
            self.password = password or os.getenv("RABBITMQ_PASSWORD", "guest")
            self.virtual_host = virtual_host or os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
            self.amqp_url = None
        
        # Queue configuration
        self.request_queue = os.getenv("REQUEST_QUEUE", "recipe_analysis_request")
        
        # Worker configuration
        self.worker_concurrency = int(os.getenv("WORKER_CONCURRENCY", "3"))
        self.process_timeout_sec = int(os.getenv("PROCESS_TIMEOUT_SEC", "100"))
        
        # DLX/DLQ configuration
        self.results_dlx = os.getenv("RESULTS_DLX", "dlx.results")
        self.results_dlq = os.getenv("RESULTS_DLQ", "dlq.results")
        
        # Message TTL (optional, in milliseconds)
        self.message_ttl = int(os.getenv("MESSAGE_TTL_MS", "300000"))  # 5 minutes default
        
        # Connection parameters
        self.heartbeat = int(os.getenv("RABBITMQ_HEARTBEAT", "600"))
        self.blocked_connection_timeout = int(os.getenv("RABBITMQ_BLOCKED_TIMEOUT", "300"))
        self.connection_attempts = int(os.getenv("RABBITMQ_CONNECTION_ATTEMPTS", "3"))
        self.retry_delay = int(os.getenv("RABBITMQ_RETRY_DELAY", "2"))
        
    def get_connection_params(self) -> dict:
        """Get connection parameters for pika BlockingConnection."""
        import pika
        
        if self.amqp_url:
            # Parse từ URL
            params = pika.URLParameters(self.amqp_url)
            params.heartbeat = self.heartbeat
            params.blocked_connection_timeout = self.blocked_connection_timeout
            return params
        else:
            # Build từ individual parameters
            credentials = pika.PlainCredentials(self.username, self.password)
            
            return pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                virtual_host=self.virtual_host,
                credentials=credentials,
                heartbeat=self.heartbeat,
                blocked_connection_timeout=self.blocked_connection_timeout,
                connection_attempts=self.connection_attempts,
                retry_delay=self.retry_delay
            )
    
    def validate(self) -> None:
        """Validate configuration."""
        if self.worker_concurrency < 1:
            raise ValueError("WORKER_CONCURRENCY must be >= 1")
        
        if self.process_timeout_sec < 1:
            raise ValueError("PROCESS_TIMEOUT_SEC must be >= 1")
        
        if not self.request_queue:
            raise ValueError("REQUEST_QUEUE must be set")
    
    def __repr__(self) -> str:
        """String representation for logging."""
        if self.amqp_url:
            # Don't expose credentials
            return f"RabbitMQConfig(url=*****, queue={self.request_queue}, workers={self.worker_concurrency})"
        else:
            return (
                f"RabbitMQConfig(host={self.host}:{self.port}, "
                f"queue={self.request_queue}, workers={self.worker_concurrency}, "
                f"timeout={self.process_timeout_sec}s)"
            )
