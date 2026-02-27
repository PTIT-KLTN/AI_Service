"""
Test script để kiểm tra quá trình trích xuất món ăn từ Knowledge Base
Chạy thật (không mock) với AWS Bedrock hoặc Ollama
"""
import json
import os
from dotenv import load_dotenv
from app.main_optimized import OptimizedShoppingCartPipeline

load_dotenv()

def test_extract_dish_from_kb():
    """Test trích xuất món 'chả giò khoai tây' từ KB"""
    
    # Testcase
    user_input = "tôi muốn ăn món chả giò khoai tây"
    
    print("=" * 80)
    print("TEST: Trích xuất món ăn từ Knowledge Base")
    print("=" * 80)
    print(f"Input: {user_input}")
    print()
    
    # Kiểm tra environment variables
    print("Environment Configuration:")
    print(f"  LLM_PROVIDER: {os.getenv('LLM_PROVIDER', 'bedrock')}")
    print(f"  KB_SOURCE: {os.getenv('KB_SOURCE', 'bedrock')}")
    print(f"  BEDROCK_KB_ID: {os.getenv('BEDROCK_KB_ID', 'Not set')}")
    print(f"  BEDROCK_MODEL_ID: {os.getenv('BEDROCK_MODEL_ID', 'Not set')}")
    
    if os.getenv('KB_SOURCE', '').lower() == 'pinecone':
        print(f"  PINECONE_INDEX_NAME: {os.getenv('PINECONE_INDEX_NAME', 'recipe-kb')}")
        print(f"  PINECONE_NAMESPACE: {os.getenv('PINECONE_NAMESPACE', 'dishes')}")
        print(f"  EMBEDDING_MODEL: {os.getenv('EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')}")
    
    if os.getenv('LLM_PROVIDER', '').lower() == 'ollama':
        print(f"  OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/api')}")
        print(f"  OLLAMA_TEXT_MODEL: {os.getenv('OLLAMA_TEXT_MODEL', 'qwen2.5:7b')}")
    print()
    
    # Initialize pipeline
    print("Initializing pipeline...")
    pipeline = OptimizedShoppingCartPipeline()
    print("Pipeline initialized.\n")
    
    # Process request
    print("Processing request...")
    print("-" * 80)
    
    try:
        result = pipeline.process(user_input)
        
        print("\n" + "=" * 80)
        print("RESULT")
        print("=" * 80)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print()
        
        # Phân tích kết quả
        print("=" * 80)
        print("ANALYSIS")
        print("=" * 80)
        
        if result.get('guardrail'):
            print("⚠️  GUARDRAIL TRIGGERED")
            print(f"   Messages: {result.get('guardrail_messages', [])}")
            return
        
        dish_name = result.get('dish_name') or result.get('vietnamese_name')
        ingredients = result.get('ingredients', [])
        
        print(f"✓ Món ăn: {dish_name}")
        print(f"✓ Số nguyên liệu: {len(ingredients)}")
        print()
        
        if ingredients:
            print("Top 10 nguyên liệu:")
            for i, ing in enumerate(ingredients[:10], 1):
                name = ing.get('vietnamese_name') or ing.get('name', '')
                unit = ing.get('unit', '')
                unit_str = f" ({unit})" if unit else ""
                print(f"  {i:2d}. {name}{unit_str}")
        else:
            print("⚠️  Không tìm thấy nguyên liệu")
        
        print()
        print("=" * 80)
        print("TEST COMPLETED")
        print("=" * 80)
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("ERROR")
        print("=" * 80)
        print(f"❌ Exception: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        import traceback
        print("\nTraceback:")
        traceback.print_exc()
        print()


if __name__ == "__main__":
    test_extract_dish_from_kb()
