from app.main import ShoppingCartPipeline
import json
from datetime import datetime

if __name__ == "__main__":
    pipeline = ShoppingCartPipeline()
    
    # Input
    user_input = "Tôi muốn nấu món thịt kho tàu"
    
    # Process
    result = pipeline.process(user_input)

    # Prepare output data
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "input": {
            "user_query": user_input
        },
        "output": result
    }
    
    # Save to file
    output_file = "test_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Đã lưu kết quả vào file: {output_file}")