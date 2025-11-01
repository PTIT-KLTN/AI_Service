"""
RabbitMQ Consumer for AI Service.
Implements RPC Server pattern - receives requests, processes them, and sends responses.
"""
import json
import logging
import pika
from typing import Callable, Dict, Any
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from app.rabbitmq.config import RabbitMQConfig

logger = logging.getLogger(__name__)


class RecipeAnalysisConsumer:
    
    def __init__(
        self,
        config: RabbitMQConfig,
        process_callback: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Initialize RabbitMQ consumer."""
        self.config = config
        self.process_callback = process_callback
        self.connection = None
        self.channel = None
        
    def connect(self) -> None:
        """Establish connection to RabbitMQ."""
        try:
            params = pika.ConnectionParameters(**self.config.get_connection_params())
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Declare the request queue
            self.channel.queue_declare(queue=self.config.request_queue, durable=True)
            
            # Set QoS to process one message at a time
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info(f"Connected to RabbitMQ at {self.config.host}:{self.config.port}")
            logger.info(f"Listening on queue: {self.config.request_queue}")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def on_request(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes
    ) -> None:
        """Handle incoming RPC requests."""
        correlation_id = properties.correlation_id
        reply_to = properties.reply_to
        
        logger.info(f"Received request with correlation_id: {correlation_id}")
        
        try:
            # Parse request
            request_data = json.loads(body.decode('utf-8'))
            logger.debug(f"Request data: {request_data}")
            
            # Process request using callback
            response_data = self.process_callback(request_data)
            logger.debug(f"Response data: {response_data}")
            
            # Prepare response
            response_body = json.dumps(response_data, ensure_ascii=False)
            
            # Send response back to reply_to queue with same correlation_id
            channel.basic_publish(
                exchange='',
                routing_key=reply_to,
                properties=BasicProperties(
                    correlation_id=correlation_id,
                    content_type='application/json'
                ),
                body=response_body.encode('utf-8')
            )
            
            logger.info(f"Sent response for correlation_id: {correlation_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            # Send error response
            error_response = {
                "success": False,
                "error": f"Invalid JSON: {str(e)}"
            }
            channel.basic_publish(
                exchange='',
                routing_key=reply_to,
                properties=BasicProperties(
                    correlation_id=correlation_id,
                    content_type='application/json'
                ),
                body=json.dumps(error_response).encode('utf-8')
            )
            
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            # Send error response
            error_response = {
                "success": False,
                "error": str(e)
            }
            channel.basic_publish(
                exchange='',
                routing_key=reply_to,
                properties=BasicProperties(
                    correlation_id=correlation_id,
                    content_type='application/json'
                ),
                body=json.dumps(error_response).encode('utf-8')
            )
        
        finally:
            # Acknowledge message
            channel.basic_ack(delivery_tag=method.delivery_tag)
    
    def start_consuming(self) -> None:
        """Start consuming messages from the queue."""
        try:
            self.channel.basic_consume(
                queue=self.config.request_queue,
                on_message_callback=self.on_request
            )
            
            logger.info("AI Service RabbitMQ Consumer started. Waiting for requests...")
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            self.stop()
        except Exception as e:
            logger.error(f"Error in consuming: {e}", exc_info=True)
            raise
    
    def stop(self) -> None:
        """Stop consuming and close connection."""
        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()
            self.channel.close()
        
        if self.connection and self.connection.is_open:
            self.connection.close()
        
        logger.info("RabbitMQ connection closed")
    
    def run(self) -> None:
        """Connect and start consuming (main entry point)."""
        self.connect()
        self.start_consuming()
