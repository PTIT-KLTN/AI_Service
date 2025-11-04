
import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, Dict, Any, Optional
from datetime import datetime

import pika
from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection
from pika.spec import Basic, BasicProperties

from app.rabbitmq.config import RabbitMQConfig

logger = logging.getLogger(__name__)


class ThreadedRabbitMQWorker:
    
    def __init__(
        self,
        config: RabbitMQConfig,
        process_callback: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        self.config = config
        self.process_callback = process_callback
        
        self.connection: Optional[BlockingConnection] = None
        self.channel: Optional[BlockingChannel] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        
        # Track returned (unroutable) messages
        self.returned_messages = []
        self.returned_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'received': 0,
            'processed': 0,
            'errors': 0,
            'timeouts': 0,
            'unroutable': 0
        }
        self.stats_lock = threading.Lock()
        
    def connect(self) -> None:
        """Establish connection to RabbitMQ."""
        try:
            logger.info("Connecting to RabbitMQ...")
            params = self.config.get_connection_params()
            self.connection = BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Declare DLX and DLQ for failed results
            self._setup_dlx_dlq()
            
            # Declare request queue (durable)
            queue_args = {
                'x-message-ttl': self.config.message_ttl,
            }
            self.channel.queue_declare(
                queue=self.config.request_queue,
                durable=True,
                arguments=queue_args
            )
            
            # Set QoS (prefetch) for fairness
            self.channel.basic_qos(prefetch_count=self.config.worker_concurrency)
            
            # Enable publisher confirms
            self.channel.confirm_delivery()
            
            # Register callback for returned (unroutable) messages
            self.channel.add_on_return_callback(self._on_return_callback)
            
            logger.info(f"Connected to RabbitMQ: {self.config}")
            logger.info(f"Listening on queue: {self.config.request_queue}")
            logger.info(f"Worker concurrency: {self.config.worker_concurrency}")
            logger.info(f"Process timeout: {self.config.process_timeout_sec}s")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}", exc_info=True)
            raise
    
    def _setup_dlx_dlq(self) -> None:
        """Setup Dead Letter Exchange và Dead Letter Queue."""
        try:
            # Declare DLX
            self.channel.exchange_declare(
                exchange=self.config.results_dlx,
                exchange_type='fanout',
                durable=True
            )
            
            # Declare DLQ
            self.channel.queue_declare(
                queue=self.config.results_dlq,
                durable=True
            )
            
            # Bind DLQ to DLX
            self.channel.queue_bind(
                queue=self.config.results_dlq,
                exchange=self.config.results_dlx
            )
            
            logger.info(f"DLX/DLQ setup complete: {self.config.results_dlx} -> {self.config.results_dlq}")
            
        except Exception as e:
            logger.warning(f"Failed to setup DLX/DLQ: {e}")
    
    def _on_return_callback(
        self,
        channel: BlockingChannel,
        method: Basic.Return,
        properties: BasicProperties,
        body: bytes
    ) -> None:
        """
        Callback khi message bị return (unroutable) do queue không tồn tại.
        Xảy ra khi client timeout/disconnect trước khi worker reply.
        """
        correlation_id = properties.correlation_id or 'unknown'
        reply_to = method.routing_key
        
        with self.stats_lock:
            self.stats['unroutable'] += 1
        
        logger.warning(
            f"Message UNROUTABLE - correlation_id={correlation_id}, "
            f"reply_to={reply_to}, reply_code={method.reply_code}, "
            f"reply_text={method.reply_text}"
        )
        
        # Store for debugging
        with self.returned_lock:
            self.returned_messages.append({
                'correlation_id': correlation_id,
                'reply_to': reply_to,
                'reply_code': method.reply_code,
                'reply_text': method.reply_text,
                'timestamp': datetime.utcnow().isoformat(),
                'body_preview': body[:200].decode('utf-8', errors='ignore')
            })
        
        # Optional: publish to DLQ để không mất data
        try:
            dlq_body = {
                'correlation_id': correlation_id,
                'reply_to': reply_to,
                'reason': 'unroutable',
                'reply_code': method.reply_code,
                'reply_text': method.reply_text,
                'timestamp': datetime.utcnow().isoformat(),
                'original_body': body.decode('utf-8', errors='ignore')
            }
            
            channel.basic_publish(
                exchange=self.config.results_dlx,
                routing_key='',
                body=json.dumps(dlq_body, ensure_ascii=False).encode('utf-8'),
                properties=BasicProperties(
                    correlation_id=correlation_id,
                    content_type='application/json',
                    delivery_mode=2
                )
            )
            logger.info(f"Unroutable message saved to DLQ: correlation_id={correlation_id}")
            
        except Exception as e:
            logger.error(f"Failed to publish unroutable message to DLQ: {e}")
    
    def _on_message(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes
    ) -> None:
        """
        Callback khi nhận message từ queue.
        Chạy trên pika IOLoop thread.
        """
        correlation_id = properties.correlation_id or 'unknown'
        reply_to = properties.reply_to
        delivery_tag = method.delivery_tag
        
        with self.stats_lock:
            self.stats['received'] += 1
        
        logger.info(
            f"Received message - correlation_id={correlation_id}, "
            f"delivery_tag={delivery_tag}, reply_to={reply_to}"
        )
        
        # Parse JSON an toàn
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON - correlation_id={correlation_id}, error={e}")
            
            # Nack immediately, không requeue
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
            
            # Send error response nếu có reply_to
            if reply_to:
                self._send_error_response(
                    channel, reply_to, correlation_id,
                    f"Invalid JSON: {str(e)}"
                )
            
            with self.stats_lock:
                self.stats['errors'] += 1
            return
        
        # Submit job to thread pool
        try:
            future = self.executor.submit(
                self._process_job,
                payload,
                delivery_tag,
                reply_to,
                correlation_id
            )
            
            # Don't block here - let the worker thread handle it
            # The thread will callback to pika thread for publish/ack
            
        except Exception as e:
            logger.error(f"Failed to submit job to executor: {e}", exc_info=True)
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
            
            if reply_to:
                self._send_error_response(
                    channel, reply_to, correlation_id,
                    f"Failed to submit job: {str(e)}"
                )
            
            with self.stats_lock:
                self.stats['errors'] += 1
    
    def _process_job(
        self,
        payload: Dict[str, Any],
        delivery_tag: int,
        reply_to: Optional[str],
        correlation_id: str
    ) -> None:
        """
        Xử lý job trong worker thread.
        
        Args:
            payload: Request data
            delivery_tag: Delivery tag để ack/nack
            reply_to: Queue để gửi response
            correlation_id: ID để match request/response
        """
        start_time = time.time()
        
        logger.info(f"Processing job - correlation_id={correlation_id}")
        
        try:
            # Call business logic với timeout
            # Wrap in a future để có timeout
            result_future = self.executor.submit(self.process_callback, payload)
            
            try:
                response_data = result_future.result(timeout=self.config.process_timeout_sec)
                
            except FutureTimeoutError:
                logger.error(
                    f"Job TIMEOUT - correlation_id={correlation_id}, "
                    f"timeout={self.config.process_timeout_sec}s"
                )
                
                with self.stats_lock:
                    self.stats['timeouts'] += 1
                
                response_data = {
                    'success': False,
                    'error': f'Processing timeout after {self.config.process_timeout_sec}s',
                    'error_type': 'timeout'
                }
            
            except Exception as e:
                logger.error(
                    f"Job ERROR - correlation_id={correlation_id}, error={e}",
                    exc_info=True
                )
                
                with self.stats_lock:
                    self.stats['errors'] += 1
                
                response_data = {
                    'success': False,
                    'error': str(e),
                    'error_type': 'processing_error'
                }
            
        except Exception as e:
            # Outer exception handler
            logger.error(f"Unexpected error in job processing: {e}", exc_info=True)
            
            with self.stats_lock:
                self.stats['errors'] += 1
            
            response_data = {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'unexpected_error'
            }
        
        # Calculate elapsed time
        elapsed_ms = int((time.time() - start_time) * 1000)
        response_data['elapsed_ms'] = elapsed_ms
        
        # Prepare response body
        try:
            response_body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
        except Exception as e:
            logger.error(f"Failed to serialize response: {e}")
            response_body = json.dumps({
                'success': False,
                'error': 'Failed to serialize response',
                'elapsed_ms': elapsed_ms
            }).encode('utf-8')
        
        # Publish response và ack PHẢI chạy trên pika thread
        # Dùng add_callback_threadsafe để callback về pika IOLoop
        def publish_and_ack():
            """Callback chạy trên pika thread để publish và ack."""
            try:
                publish_success = False
                
                # Publish response nếu có reply_to
                if reply_to:
                    try:
                        self.channel.basic_publish(
                            exchange='',
                            routing_key=reply_to,
                            body=response_body,
                            properties=BasicProperties(
                                correlation_id=correlation_id,
                                content_type='application/json',
                                delivery_mode=2  # persistent
                            ),
                            mandatory=True  # detect unroutable
                        )
                        
                        publish_success = True
                        
                        logger.info(
                            f"Published response - correlation_id={correlation_id}, "
                            f"reply_to={reply_to}, elapsed_ms={elapsed_ms}"
                        )
                        
                    except Exception as e:
                        logger.error(
                            f"Failed to publish response - correlation_id={correlation_id}, "
                            f"error={e}",
                            exc_info=True
                        )
                        publish_success = False
                
                else:
                    # Không có reply_to (fire-and-forget)
                    publish_success = True
                    logger.warning(f"No reply_to queue - correlation_id={correlation_id}")
                
                # Ack hoặc Nack dựa trên publish result
                if publish_success or not reply_to:
                    # Ack: publish thành công hoặc không cần reply
                    self.channel.basic_ack(delivery_tag=delivery_tag)
                    logger.debug(f"ACK - delivery_tag={delivery_tag}")
                    
                    with self.stats_lock:
                        self.stats['processed'] += 1
                    
                else:
                    # Nack: publish thất bại
                    self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                    logger.warning(
                        f"NACK (publish failed) - delivery_tag={delivery_tag}, "
                        f"correlation_id={correlation_id}"
                    )
                    
                    with self.stats_lock:
                        self.stats['errors'] += 1
                    
                    # Optional: push to DLQ
                    try:
                        dlq_body = {
                            'correlation_id': correlation_id,
                            'reply_to': reply_to,
                            'reason': 'publish_failed',
                            'timestamp': datetime.utcnow().isoformat(),
                            'payload': payload,
                            'response': response_data
                        }
                        
                        self.channel.basic_publish(
                            exchange=self.config.results_dlx,
                            routing_key='',
                            body=json.dumps(dlq_body, ensure_ascii=False).encode('utf-8'),
                            properties=BasicProperties(
                                correlation_id=correlation_id,
                                content_type='application/json',
                                delivery_mode=2
                            )
                        )
                        logger.info(f"Failed message saved to DLQ: correlation_id={correlation_id}")
                        
                    except Exception as dlq_error:
                        logger.error(f"Failed to publish to DLQ: {dlq_error}")
                
            except Exception as e:
                logger.error(f"Critical error in publish_and_ack callback: {e}", exc_info=True)
                
                # Fallback: try to nack
                try:
                    self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                except:
                    pass
        
        # Schedule callback on pika thread
        try:
            self.connection.add_callback_threadsafe(publish_and_ack)
        except Exception as e:
            logger.error(f"Failed to schedule callback: {e}", exc_info=True)
    
    def _send_error_response(
        self,
        channel: BlockingChannel,
        reply_to: str,
        correlation_id: str,
        error_message: str
    ) -> None:

        try:
            error_body = json.dumps({
                'success': False,
                'error': error_message
            }, ensure_ascii=False).encode('utf-8')
            
            channel.basic_publish(
                exchange='',
                routing_key=reply_to,
                body=error_body,
                properties=BasicProperties(
                    correlation_id=correlation_id,
                    content_type='application/json',
                    delivery_mode=2
                ),
                mandatory=True
            )
            
            logger.info(f"Sent error response - correlation_id={correlation_id}")
            
        except Exception as e:
            logger.error(f"Failed to send error response: {e}")
    
    def start_consuming(self) -> None:
        """Start consuming messages."""
        try:
            # Initialize thread pool
            self.executor = ThreadPoolExecutor(
                max_workers=self.config.worker_concurrency,
                thread_name_prefix='RabbitMQ-Worker'
            )
            
            logger.info(f"ThreadPoolExecutor started with {self.config.worker_concurrency} workers")
            
            # Start consuming (auto_ack=False for manual ack)
            self.channel.basic_consume(
                queue=self.config.request_queue,
                on_message_callback=self._on_message,
                auto_ack=False
            )
            
            logger.info("=" * 80)
            logger.info("AI Service Worker READY - Waiting for requests...")
            logger.info("=" * 80)
            
            # Start IOLoop (blocking)
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Worker stopped by user (Ctrl+C)")
            self.stop()
        except Exception as e:
            logger.error(f"Error in consuming: {e}", exc_info=True)
            raise
    
    def stop(self) -> None:
        """Stop worker gracefully."""
        logger.info("Stopping worker...")
        
        # Stop consuming
        if self.channel and self.channel.is_open:
            try:
                self.channel.stop_consuming()
            except:
                pass
        
        # Shutdown executor
        if self.executor:
            logger.info("Shutting down ThreadPoolExecutor...")
            self.executor.shutdown(wait=True, cancel_futures=False)
            logger.info("ThreadPoolExecutor stopped")
        
        # Close channel
        if self.channel and self.channel.is_open:
            try:
                self.channel.close()
            except:
                pass
        
        # Close connection
        if self.connection and self.connection.is_open:
            try:
                self.connection.close()
            except:
                pass
        
        # Log statistics
        logger.info("=" * 80)
        logger.info("Worker Statistics:")
        logger.info(f"  Received: {self.stats['received']}")
        logger.info(f"  Processed: {self.stats['processed']}")
        logger.info(f"  Errors: {self.stats['errors']}")
        logger.info(f"  Timeouts: {self.stats['timeouts']}")
        logger.info(f"  Unroutable: {self.stats['unroutable']}")
        logger.info("=" * 80)
        
        logger.info("Worker stopped")
    
    def run(self) -> None:
        """Main entry point: connect và start consuming."""
        self.connect()
        self.start_consuming()