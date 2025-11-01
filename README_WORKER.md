# AI Service - RabbitMQ Worker với Multi-Threading

## Tổng quan

AI Service Worker xử lý yêu cầu phân tích recipe qua RabbitMQ theo mô hình **RPC (Request-Reply)** sử dụng **ThreadPoolExecutor** (multi-threading) - **KHÔNG dùng async/await**.

### Đặc điểm kỹ thuật

✅ **Đã implement:**
- ✅ Python 3.10+ với pika BlockingConnection (KHÔNG dùng async/asyncio)
- ✅ ThreadPoolExecutor cho xử lý song song I/O-bound
- ✅ Publisher confirms & mandatory routing (phát hiện unroutable messages)
- ✅ Thread-safe callbacks với `connection.add_callback_threadsafe`
- ✅ Timeout xử lý (configurable)
- ✅ Dead Letter Exchange (DLX) và Dead Letter Queue (DLQ)
- ✅ Prefetch QoS cho fairness
- ✅ Manual ACK/NACK an toàn
- ✅ Logging đầy đủ (correlation_id, delivery_tag, elapsed time)
- ✅ Graceful shutdown
- ✅ Docker Compose ready

## Kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Main Thread (Pika IOLoop)                   │
│  - BlockingConnection.start_consuming()                             │
│  - Nhận messages từ queue                                           │
│  - Publisher confirms & returned message callbacks                  │
│  - ACK/NACK (chỉ từ main thread hoặc via add_callback_threadsafe)  │
└────────────┬────────────────────────────────────────────────────────┘
             │
             │ Submit job
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              ThreadPoolExecutor (max_workers=WORKER_CONCURRENCY)    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │  Worker #1  │  │  Worker #2  │  │  Worker #3  │  ...           │
│  │             │  │             │  │             │                 │
│  │ - Parse req │  │ - Parse req │  │ - Parse req │                 │
│  │ - Call ML   │  │ - Call ML   │  │ - Call ML   │                 │
│  │ - Call RAG  │  │ - Call RAG  │  │ - Call RAG  │                 │
│  │ - Build res │  │ - Build res │  │ - Build res │                 │
│  │             │  │             │  │             │                 │
│  │ Callback ─┐ │  │ Callback ─┐ │  │ Callback ─┐ │                 │
│  └───────────┼─┘  └───────────┼─┘  └───────────┼─┘                 │
│              │                │                │                   │
└──────────────┼────────────────┼────────────────┼───────────────────┘
               │                │                │
               │ add_callback_threadsafe          │
               ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Pika Thread (publish & ack)                      │
│  - basic_publish(reply_to, body, mandatory=True)                    │
│  - basic_ack(delivery_tag) hoặc basic_nack(delivery_tag)            │
└─────────────────────────────────────────────────────────────────────┘
```

### Luồng xử lý

1. **Main thread** nhận message từ queue `recipe_analysis_request`
2. **Submit** job vào ThreadPoolExecutor
3. **Worker thread** xử lý:
   - Parse request
   - Gọi ShoppingCartPipeline (I/O-bound: Bedrock, S3, KB)
   - Có timeout nội bộ
4. **Callback** về main thread qua `add_callback_threadsafe`:
   - Publish response với `mandatory=True`
   - ACK nếu publish thành công
   - NACK nếu publish thất bại

## Cài đặt

### Requirements

- Python 3.10+
- RabbitMQ Server 3.12+
- Docker & Docker Compose (optional)

### 1. Clone và cài đặt dependencies

```bash
# Clone repository
git clone <repo-url>
cd AI_Service

# Tạo virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc
venv\Scripts\activate     # Windows

# Cài đặt dependencies
pip install -r requirements.txt
```

### 2. Cấu hình environment

```bash
# Copy file example
cp .env.example .env

# Chỉnh sửa .env
nano .env
```

**Cấu hình quan trọng:**

```env
# RabbitMQ
AMQP_URL=amqp://guest:guest@localhost:5672/
REQUEST_QUEUE=recipe_analysis_request
WORKER_CONCURRENCY=3          # Cho máy yếu: 2-4
PROCESS_TIMEOUT_SEC=30        # Timeout cho mỗi job

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
```

### 3. Chạy RabbitMQ Server

#### Option A: Docker (khuyến nghị)

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=admin123 \
  rabbitmq:3.12-management
```

#### Option B: Local installation

**Windows (Chocolatey):**
```powershell
choco install erlang rabbitmq -y
rabbitmq-service start
rabbitmq-plugins enable rabbitmq_management
```

**Linux (Ubuntu):**
```bash
sudo apt-get install rabbitmq-server -y
sudo systemctl start rabbitmq-server
sudo rabbitmq-plugins enable rabbitmq_management
```

**Kiểm tra:**
- AMQP: `telnet localhost 5672`
- Management UI: http://localhost:15672 (admin/admin123)

## Chạy Worker

### Development (local)

```bash
# Activate venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Run worker
python run_rabbitmq_worker.py
```

**Output mong đợi:**

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║                    AI Service RabbitMQ Worker                             ║
║                    Multi-Threading (No Async)                             ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

2024-01-15 10:00:00 - __main__ - INFO - ================================================================================
2024-01-15 10:00:00 - __main__ - INFO - Starting AI Service RabbitMQ Worker (ThreadPoolExecutor)
2024-01-15 10:00:00 - __main__ - INFO - ================================================================================
2024-01-15 10:00:00 - __main__ - INFO - RabbitMQ Configuration:
2024-01-15 10:00:00 - __main__ - INFO -   RabbitMQConfig(host=localhost:5672, queue=recipe_analysis_request, workers=3, timeout=30s)
2024-01-15 10:00:00 - __main__ - INFO -   Queue: recipe_analysis_request
2024-01-15 10:00:00 - __main__ - INFO -   Worker Concurrency: 3
2024-01-15 10:00:00 - __main__ - INFO -   Process Timeout: 30s
2024-01-15 10:00:00 - app.rabbitmq.worker_threaded - INFO - Connected to RabbitMQ: ...
2024-01-15 10:00:00 - app.rabbitmq.worker_threaded - INFO - ThreadPoolExecutor started with 3 workers
2024-01-15 10:00:00 - app.rabbitmq.worker_threaded - INFO - ================================================================================
2024-01-15 10:00:00 - app.rabbitmq.worker_threaded - INFO - AI Service Worker READY - Waiting for requests...
2024-01-15 10:00:00 - app.rabbitmq.worker_threaded - INFO - ================================================================================
```

### Production (Docker Compose)

```bash
# Tạo .env với production values
cp .env.example .env
nano .env

# Start services
docker-compose up -d

# View logs
docker-compose logs -f ai_service_worker

# Stop services
docker-compose down
```

**Scaling workers:**

```bash
# Scale to 3 worker instances
docker-compose up -d --scale ai_service_worker=3
```

## Testing

### Test Client (Python)

Tạo file `test_client.py`:

```python
import pika
import json
import uuid
import sys

class RecipeAnalysisRPCClient:
    def __init__(self, amqp_url='amqp://guest:guest@localhost:5672/'):
        params = pika.URLParameters(amqp_url)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        
        # Declare exclusive callback queue
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        
        self.response = None
        self.corr_id = None
        
        # Start consuming from callback queue
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True
        )
    
    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body.decode('utf-8'))
    
    def call(self, request_data):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        
        self.channel.basic_publish(
            exchange='',
            routing_key='recipe_analysis_request',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
                content_type='application/json',
                delivery_mode=2  # persistent
            ),
            body=json.dumps(request_data, ensure_ascii=False).encode('utf-8')
        )
        
        print(f"[x] Sent request with correlation_id: {self.corr_id}")
        
        # Wait for response
        while self.response is None:
            self.connection.process_data_events(time_limit=1)
        
        return self.response
    
    def close(self):
        self.connection.close()


# Test
if __name__ == '__main__':
    client = RecipeAnalysisRPCClient()
    
    # Test request
    request = {
        "user_input": "Tôi muốn nấu món phở bò"
    }
    
    print(f"[.] Requesting recipe analysis...")
    response = client.call(request)
    
    print(f"[✓] Response received:")
    print(json.dumps(response, indent=2, ensure_ascii=False))
    
    client.close()
```

**Chạy test:**

```bash
python test_client.py
```

### Load Testing

**Test với nhiều requests đồng thời:**

```python
import concurrent.futures
import time

def send_request(i):
    client = RecipeAnalysisRPCClient()
    request = {"user_input": f"Món ăn #{i}"}
    
    start = time.time()
    response = client.call(request)
    elapsed = time.time() - start
    
    client.close()
    return elapsed, response['success']

# Send 10 concurrent requests
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(send_request, i) for i in range(10)]
    
    for i, future in enumerate(concurrent.futures.as_completed(futures)):
        elapsed, success = future.result()
        print(f"Request {i+1}: {elapsed:.2f}s - {'✓' if success else '✗'}")
```

## Monitoring

### RabbitMQ Management UI

- URL: http://localhost:15672
- Login: admin/admin123 (hoặc guest/guest)
- **Queues** tab: xem `recipe_analysis_request`, message rates
- **Connections** tab: xem worker connections
- **Exchanges** tab: xem DLX

### Logs

Worker logs:
- Console: `docker-compose logs -f ai_service_worker`
- File: `rabbitmq_worker.log`

**Log format:**

```
2024-01-15 10:05:23 - app.rabbitmq.worker_threaded - INFO - [RabbitMQ-Worker-1] - Received message - correlation_id=abc-123, delivery_tag=1, reply_to=amq.gen-xyz
2024-01-15 10:05:23 - app.rabbitmq.processor - INFO - [RabbitMQ-Worker-1] - Processing text input: Tôi muốn nấu món phở bò
2024-01-15 10:05:25 - app.rabbitmq.worker_threaded - INFO - [MainThread] - Published response - correlation_id=abc-123, reply_to=amq.gen-xyz, elapsed_ms=2340
2024-01-15 10:05:25 - app.rabbitmq.worker_threaded - DEBUG - [MainThread] - ACK - delivery_tag=1
```

### Statistics

Worker tự động log statistics khi shutdown:

```
================================================================================
Worker Statistics:
  Received: 150
  Processed: 145
  Errors: 3
  Timeouts: 2
  Unroutable: 0
================================================================================
```

## Troubleshooting

### 1. Connection Refused

**Lỗi:**
```
pika.exceptions.AMQPConnectionError: Connection refused
```

**Giải pháp:**
```bash
# Kiểm tra RabbitMQ đang chạy
docker ps | grep rabbitmq
# hoặc
rabbitmqctl status

# Restart RabbitMQ
docker restart rabbitmq
```

### 2. Timeout khi xử lý

**Lỗi trong log:**
```
Job TIMEOUT - correlation_id=xxx, timeout=30s
```

**Giải pháp:**
- Tăng `PROCESS_TIMEOUT_SEC` trong `.env`
- Kiểm tra AWS Bedrock response time
- Tối ưu pipeline code

### 3. Unroutable messages

**Cảnh báo:**
```
Message UNROUTABLE - correlation_id=xxx, reply_to=amq.gen-yyy, reply_code=312, reply_text=NO_ROUTE
```

**Nguyên nhân:** Client timeout/disconnect trước khi worker reply

**Giải pháp:**
- Messages được tự động lưu vào DLQ
- Kiểm tra `dlq.results` queue trong RabbitMQ UI
- Tăng client timeout

### 4. High memory usage

**Giải pháp:**
- Giảm `WORKER_CONCURRENCY` (vd: từ 5 về 2)
- Set resource limits trong Docker Compose
- Monitor với `docker stats`

### 5. Deadlock hoặc worker không phản hồi

**Kiểm tra:**
```bash
# View worker logs
docker-compose logs --tail=100 ai_service_worker

# View thread activity
docker exec -it ai_service_worker python -c "import sys, threading; print(threading.enumerate())"
```

## Performance Tuning

### Cho máy yếu (RAM < 4GB)

```env
WORKER_CONCURRENCY=2
PROCESS_TIMEOUT_SEC=45
```

### Cho máy trung bình (RAM 4-8GB)

```env
WORKER_CONCURRENCY=3
PROCESS_TIMEOUT_SEC=30
```

### Cho máy mạnh (RAM > 8GB)

```env
WORKER_CONCURRENCY=5
PROCESS_TIMEOUT_SEC=20
```

### Prefetch Count

Trong code (`worker_threaded.py`):
```python
self.channel.basic_qos(prefetch_count=self.config.worker_concurrency)
```

**Quy tắc:** `prefetch_count = WORKER_CONCURRENCY` để fairness

## Architecture Decisions

### Tại sao KHÔNG dùng async/await?

1. **Máy yếu:** ThreadPoolExecutor dùng ít RAM hơn asyncio event loop
2. **I/O-bound:** Các tác vụ chính (Bedrock API, S3, HTTP) đã async ở network layer
3. **Đơn giản:** Sync code dễ debug, maintain hơn
4. **Pika compatibility:** BlockingConnection ổn định hơn aio-pika

### Tại sao dùng ThreadPoolExecutor?

1. **Song song I/O:** Nhiều requests đồng thời không block nhau
2. **Fairness:** Kết hợp prefetch_count để distribute messages đều
3. **Timeout:** Dễ implement timeout với `future.result(timeout=...)`
4. **Thread-safe:** Pika callbacks an toàn với `add_callback_threadsafe`

### Xử lý unroutable messages

Khi client timeout/disconnect, `reply_to` queue bị xóa → message unroutable

**Flow:**
1. Worker publish với `mandatory=True`
2. RabbitMQ gọi `on_return_callback` nếu unroutable
3. Worker log warning và push vào DLQ
4. Admin có thể xem/replay từ DLQ

## Production Checklist

- [ ] Environment variables đã set đúng
- [ ] RabbitMQ có authentication (không dùng guest/guest)
- [ ] SSL/TLS enabled cho RabbitMQ (production)
- [ ] Monitoring setup (Prometheus + Grafana)
- [ ] Alerting cho errors/timeouts
- [ ] Log aggregation (ELK stack hoặc CloudWatch)
- [ ] Resource limits trong Docker/K8s
- [ ] Health checks configured
- [ ] DLQ monitoring & alerting
- [ ] Backup strategy cho RabbitMQ data

## License

MIT

## Support

Để biết thêm chi tiết:
- [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
- [Pika Documentation](https://pika.readthedocs.io/)
- [Python ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html)
