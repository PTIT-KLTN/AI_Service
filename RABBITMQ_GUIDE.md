# RabbitMQ Integration Guide - AI Service

## Tổng Quan

AI Service sử dụng RabbitMQ để nhận và xử lý yêu cầu phân tích công thức nấu ăn từ Main Service. Kiến trúc sử dụng **RabbitMQ RPC Pattern** với correlation_id để match request/response.

## Kiến Trúc

```
Main Service (Client)                    AI Service (RPC Server)
      |                                           |
      | 1. Publish to 'recipe_analysis_request'  |
      |    - correlation_id: "unique-id"         |
      |    - reply_to: "callback_queue"          |
      |    - body: {"user_input": "..."}         |
      |------------------------------------------>|
      |                                           | 2. Process with ShoppingCartPipeline
      |                                           |    - Extract dish
      |                                           |    - Get recipe
      |                                           |    - Check conflicts
      |                                           |    - Build shopping cart
      |                                           |
      | 3. Consume from 'callback_queue'         |
      |    - correlation_id: "unique-id"         |
      |    - body: {"success": true, "result":{}}|
      |<------------------------------------------|
      |                                           |
```

## Cài Đặt

### 1. Cài Đặt RabbitMQ Server

#### Windows (với Chocolatey):
```powershell
# Install Erlang (required by RabbitMQ)
choco install erlang -y

# Install RabbitMQ
choco install rabbitmq -y

# Start RabbitMQ service
rabbitmq-service start

# Enable management plugin
rabbitmq-plugins enable rabbitmq_management
```

#### Docker (đơn giản hơn):
```bash
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=admin123 \
  rabbitmq:3-management
```

### 2. Cài Đặt Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Cấu Hình Environment Variables

Tạo file `.env` trong thư mục gốc:

```env
# RabbitMQ Configuration
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VIRTUAL_HOST=/

# AWS Bedrock Configuration (existing)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

## Chạy AI Service

### Khởi động RabbitMQ Worker

```bash
python run_rabbitmq_worker.py
```

Output mong đợi:
```
2024-01-15 10:00:00 - __main__ - INFO - ================================================================================
2024-01-15 10:00:00 - __main__ - INFO - Starting AI Service RabbitMQ Worker
2024-01-15 10:00:00 - __main__ - INFO - ================================================================================
2024-01-15 10:00:00 - __main__ - INFO - RabbitMQ Configuration:
2024-01-15 10:00:00 - __main__ - INFO -   Host: localhost:5672
2024-01-15 10:00:00 - __main__ - INFO -   Virtual Host: /
2024-01-15 10:00:00 - __main__ - INFO -   Request Queue: recipe_analysis_request
2024-01-15 10:00:00 - app.rabbitmq.consumer - INFO - Connected to RabbitMQ at localhost:5672
2024-01-15 10:00:00 - app.rabbitmq.consumer - INFO - Listening on queue: recipe_analysis_request
2024-01-15 10:00:00 - app.rabbitmq.consumer - INFO - AI Service RabbitMQ Consumer started. Waiting for requests...
```

## Message Format

### Request Format (từ Main Service)

```json
{
  "user_input": "Tôi muốn nấu món phở bò"
}
```

### Response Format (từ AI Service)

#### Success Response:
```json
{
  "success": true,
  "result": {
    "dish": "Phở bò",
    "recipe": {
      "name": "Phở bò",
      "ingredients": [
        {
          "name": "Thịt bò",
          "quantity": 500,
          "unit": "gram"
        }
      ]
    },
    "shopping_cart": {
      "items": [
        {
          "name": "Thịt bò",
          "quantity": 500,
          "unit": "gram"
        }
      ]
    },
    "conflict_warnings": [
      {
        "conflicting_item_1": ["Bò"],
        "conflicting_item_2": ["Phô mai"],
        "message": "Không nên kết hợp bò với phô mai",
        "sources": [
          {
            "name": "Dinh dưỡng học",
            "url": "https://example.com/nutrition"
          }
        ]
      }
    ]
  }
}
```

#### Error Response:
```json
{
  "success": false,
  "error": "Processing error: ..."
}
```

## Testing

### Test với RabbitMQ Management UI

1. Mở trình duyệt: http://localhost:15672
2. Đăng nhập: guest/guest (hoặc admin/admin123 nếu dùng Docker)
3. Vào tab "Queues" → chọn `recipe_analysis_request`
4. Trong "Publish message":
   - Properties: `{"correlation_id": "test-123", "reply_to": "test_reply_queue"}`
   - Payload: `{"user_input": "Tôi muốn nấu món phở bò"}`
5. Click "Publish message"
6. Kiểm tra queue `test_reply_queue` để xem response

### Test với Python Client (cho Main Service)

Tạo file `test_rabbitmq_client.py`:

```python
import pika
import json
import uuid

class RecipeAnalysisClient:
    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host='localhost')
        )
        self.channel = self.connection.channel()
        
        # Declare callback queue
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        
        self.response = None
        self.correlation_id = None
        
        # Start consuming responses
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True
        )
    
    def on_response(self, ch, method, props, body):
        if self.correlation_id == props.correlation_id:
            self.response = json.loads(body.decode('utf-8'))
    
    def call(self, user_input):
        self.response = None
        self.correlation_id = str(uuid.uuid4())
        
        request = {"user_input": user_input}
        
        self.channel.basic_publish(
            exchange='',
            routing_key='recipe_analysis_request',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.correlation_id,
                content_type='application/json'
            ),
            body=json.dumps(request, ensure_ascii=False).encode('utf-8')
        )
        
        # Wait for response
        while self.response is None:
            self.connection.process_data_events()
        
        return self.response

# Test
client = RecipeAnalysisClient()
response = client.call("Tôi muốn nấu món phở bò")
print(json.dumps(response, indent=2, ensure_ascii=False))
```

Chạy test:
```bash
python test_rabbitmq_client.py
```

## Monitoring và Troubleshooting

### Kiểm tra RabbitMQ Status

```bash
# Check RabbitMQ service status
rabbitmqctl status

# List queues
rabbitmqctl list_queues

# List connections
rabbitmqctl list_connections
```

### Logs

Worker logs được lưu tại:
- Console output (stdout)
- File: `rabbitmq_worker.log`

### Common Issues

#### 1. Connection Refused
```
pika.exceptions.AMQPConnectionError: Connection refused
```
**Solution**: Đảm bảo RabbitMQ server đang chạy:
```bash
rabbitmq-service status
# or
docker ps | grep rabbitmq
```

#### 2. Authentication Failed
```
pika.exceptions.ProbableAuthenticationError
```
**Solution**: Kiểm tra username/password trong `.env` file

#### 3. Queue Not Found
**Solution**: Worker tự động tạo queue khi khởi động. Đảm bảo worker đang chạy.

## Architecture Components

### Files Structure

```
app/
├── rabbitmq/
│   ├── __init__.py
│   ├── config.py          # RabbitMQ connection configuration
│   ├── consumer.py        # RPC Server - receives & processes requests
│   └── processor.py       # Integrates ShoppingCartPipeline
├── main.py                # ShoppingCartPipeline
├── services/
│   └── conflict_service.py # Returns new format with sources
└── schemas.py             # Pydantic models

run_rabbitmq_worker.py     # Main entry point
```

### Key Components

1. **RabbitMQConfig** (`config.py`): Connection parameters và queue names
2. **RecipeAnalysisConsumer** (`consumer.py`): RPC Server pattern implementation
3. **RecipeAnalysisProcessor** (`processor.py`): Bridge between RabbitMQ và ShoppingCartPipeline
4. **run_rabbitmq_worker.py**: Main script để khởi động worker

## Production Deployment

### Systemd Service (Linux)

Tạo file `/etc/systemd/system/ai-service-worker.service`:

```ini
[Unit]
Description=AI Service RabbitMQ Worker
After=network.target rabbitmq-server.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/AI_Service
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python run_rabbitmq_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Khởi động service:
```bash
sudo systemctl enable ai-service-worker
sudo systemctl start ai-service-worker
sudo systemctl status ai-service-worker
```

### Docker Compose (Recommended)

Tạo file `docker-compose.yml`:

```yaml
version: '3.8'

services:
  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: admin
      RABBITMQ_DEFAULT_PASS: admin123
    healthcheck:
      test: rabbitmq-diagnostics -q ping
      interval: 30s
      timeout: 10s
      retries: 5

  ai-service:
    build: .
    depends_on:
      rabbitmq:
        condition: service_healthy
    environment:
      RABBITMQ_HOST: rabbitmq
      RABBITMQ_PORT: 5672
      RABBITMQ_USERNAME: admin
      RABBITMQ_PASSWORD: admin123
      AWS_REGION: us-east-1
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
    command: python run_rabbitmq_worker.py
    restart: always
```

Chạy với Docker Compose:
```bash
docker-compose up -d
```

## Performance Tuning

### 1. Prefetch Count

Trong `consumer.py`, điều chỉnh QoS:
```python
# Process 1 message at a time (default)
self.channel.basic_qos(prefetch_count=1)

# Process up to 5 messages at a time (faster but more memory)
self.channel.basic_qos(prefetch_count=5)
```

### 2. Multiple Workers

Chạy nhiều worker instances để xử lý parallel:
```bash
# Terminal 1
python run_rabbitmq_worker.py

# Terminal 2
python run_rabbitmq_worker.py

# Terminal 3
python run_rabbitmq_worker.py
```

RabbitMQ sẽ tự động load balance messages giữa các workers.

### 3. Connection Pooling

Cho production, sử dụng connection pooling:
```python
# In config.py
params = {
    "heartbeat": 600,
    "blocked_connection_timeout": 300,
    "connection_attempts": 3,
    "retry_delay": 2
}
```

## Security Best Practices

1. **Không dùng default credentials** (guest/guest) trong production
2. **Sử dụng SSL/TLS** cho RabbitMQ connections
3. **Giới hạn permissions** cho RabbitMQ users
4. **Environment variables** cho sensitive data (không hardcode trong code)
5. **Firewall rules** để chỉ cho phép trusted IPs kết nối đến RabbitMQ

## Next Steps

1. ✅ AI Service đã implement RabbitMQ consumer
2. ⏭️ Main Service cần implement RabbitMQ client (RPC pattern)
3. ⏭️ Setup monitoring với RabbitMQ Management Plugin
4. ⏭️ Implement retry logic và error handling trong Main Service
5. ⏭️ Load testing để xác định optimal prefetch_count

## Support

Để biết thêm chi tiết:
- RabbitMQ Documentation: https://www.rabbitmq.com/documentation.html
- Pika Documentation: https://pika.readthedocs.io/
- RabbitMQ RPC Tutorial: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
