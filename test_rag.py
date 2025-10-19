import os
from app.main import ShoppingCartPipeline
import json
from datetime import datetime

if __name__ == "__main__":
    pipeline = ShoppingCartPipeline()
    
    # Input
    user_input = "Tôi muốn nấu món thịt kho tàu"
    
    # Process
    text_result = pipeline.process(user_input)

    # # Image input (base64-encoded 1x1 transparent PNG as placeholder)
    # placeholder_image_b64 = (
    #     "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIW2P4"
    #     "//8/AwAI/AL+XhVVNwAAAABJRU5ErkJggg=="
    # )
    # image_description = "Ảnh minh họa món ăn"

    # if os.getenv("VISION_MODEL_ID"):
    #     try:
    #         image_result = pipeline.process_image(placeholder_image_b64, description=image_description)
    #     except Exception as exc:
    #         image_result = {"error": str(exc)}
    # else:
    #     image_result = {"error": "VISION_MODEL_ID environment variable is not set"}

    # Prepare output data
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "input": {
            "user_query": user_input,
            # "image_description": image_description
        },
        "output": {
            "text": text_result,
            # "image": image_result
        }
    }
    
    # Save to file
    output_file = "test_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Đã lưu kết quả vào file: {output_file}")