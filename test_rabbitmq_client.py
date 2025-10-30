"""
Test RabbitMQ Client for AI Service.
This simulates Main Service sending requests to AI Service via RabbitMQ.
"""
import pika
import json
import uuid
import sys


class RecipeAnalysisClient:
    """
    RabbitMQ RPC Client for testing AI Service.
    Simulates Main Service behavior.
    """
    
    def __init__(self, host='localhost', port=5672, username='guest', password='guest'):
        """Initialize RabbitMQ client connection."""
        credentials = pika.PlainCredentials(username, password)
        params = pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=credentials
        )
        
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        
        # Declare exclusive callback queue for responses
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
        
        print(f"✓ Connected to RabbitMQ at {host}:{port}")
        print(f"✓ Callback queue: {self.callback_queue}")
    
    def on_response(self, ch, method, props, body):
        """Callback when response is received."""
        if self.correlation_id == props.correlation_id:
            self.response = json.loads(body.decode('utf-8'))
    
    def call(self, user_input: str, timeout: int = 30):
        """
        Send RPC request and wait for response.
        
        Args:
            user_input: User's recipe request
            timeout: Timeout in seconds (default: 30)
            
        Returns:
            Response dictionary from AI Service
        """
        self.response = None
        self.correlation_id = str(uuid.uuid4())
        
        request = {"user_input": user_input}
        
        print(f"\n📤 Sending request:")
        print(f"   Correlation ID: {self.correlation_id}")
        print(f"   User Input: {user_input}")
        
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
        
        print(f"⏳ Waiting for response (timeout: {timeout}s)...")
        
        # Wait for response with timeout
        import time
        start_time = time.time()
        while self.response is None:
            self.connection.process_data_events()
            if time.time() - start_time > timeout:
                raise TimeoutError(f"No response received within {timeout} seconds")
        
        print(f"✓ Response received!")
        return self.response
    
    def close(self):
        """Close RabbitMQ connection."""
        self.connection.close()
        print("✓ Connection closed")


def test_basic_request():
    """Test basic recipe analysis request."""
    print("=" * 80)
    print("TEST 1: Basic Recipe Request")
    print("=" * 80)
    
    client = RecipeAnalysisClient()
    
    try:
        response = client.call("Tôi muốn nấu món phở bò")
        print("\n📥 Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if response.get("success"):
            print("\n✅ TEST PASSED: Request processed successfully")
        else:
            print(f"\n❌ TEST FAILED: {response.get('error')}")
    
    finally:
        client.close()


def test_conflict_detection():
    """Test recipe with conflicting ingredients."""
    print("\n" + "=" * 80)
    print("TEST 2: Conflict Detection")
    print("=" * 80)
    
    client = RecipeAnalysisClient()
    
    try:
        # Request recipe with potentially conflicting ingredients
        response = client.call("Tôi muốn nấu món bò nấu với phô mai")
        print("\n📥 Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if response.get("success"):
            result = response.get("result", {})
            conflicts = result.get("conflict_warnings", [])
            
            if conflicts:
                print(f"\n✅ TEST PASSED: Found {len(conflicts)} conflict(s)")
                for i, conflict in enumerate(conflicts, 1):
                    print(f"\n   Conflict {i}:")
                    print(f"   - Item 1: {conflict.get('conflicting_item_1')}")
                    print(f"   - Item 2: {conflict.get('conflicting_item_2')}")
                    print(f"   - Message: {conflict.get('message')}")
                    print(f"   - Sources: {len(conflict.get('sources', []))} source(s)")
            else:
                print("\n⚠️  No conflicts detected (might be expected)")
        else:
            print(f"\n❌ TEST FAILED: {response.get('error')}")
    
    finally:
        client.close()


def test_invalid_request():
    """Test invalid request handling."""
    print("\n" + "=" * 80)
    print("TEST 3: Invalid Request Handling")
    print("=" * 80)
    
    client = RecipeAnalysisClient()
    
    try:
        # Send invalid/empty request
        response = client.call("")
        print("\n📥 Response:")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        
        if not response.get("success"):
            print("\n✅ TEST PASSED: Invalid request properly rejected")
            print(f"   Error: {response.get('error')}")
        else:
            print("\n⚠️  TEST WARNING: Empty request was accepted")
    
    finally:
        client.close()


def interactive_mode():
    """Interactive mode for manual testing."""
    print("\n" + "=" * 80)
    print("INTERACTIVE MODE")
    print("=" * 80)
    print("Enter recipe requests (or 'quit' to exit)")
    
    client = RecipeAnalysisClient()
    
    try:
        while True:
            user_input = input("\n🍳 Your request: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            if not user_input:
                print("⚠️  Please enter a request")
                continue
            
            try:
                response = client.call(user_input)
                print("\n📥 Response:")
                print(json.dumps(response, indent=2, ensure_ascii=False))
            
            except TimeoutError as e:
                print(f"\n❌ {e}")
            except Exception as e:
                print(f"\n❌ Error: {e}")
    
    finally:
        client.close()


def main():
    """Main test runner."""
    print("\n" + "=" * 80)
    print("AI SERVICE RABBITMQ CLIENT TEST")
    print("=" * 80)
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_mode()
    else:
        # Run automated tests
        try:
            test_basic_request()
            test_conflict_detection()
            test_invalid_request()
            
            print("\n" + "=" * 80)
            print("ALL TESTS COMPLETED")
            print("=" * 80)
        
        except Exception as e:
            print(f"\n❌ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
