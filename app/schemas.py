"""
Pydantic schemas for AI Service API
Defines request and response models for recipe analysis endpoints
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ConflictSource(BaseModel):
    """Source information for conflict data"""
    name: str = Field(..., description="Tên nguồn (VD: VnExpress)")
    url: str = Field(..., description="URL của nguồn")


class ConflictWarning(BaseModel):
    """
    Thông tin xung khắc giữa 2 nhóm nguyên liệu
    Theo yêu cầu: tách rõ conflicting_item_1 và conflicting_item_2, bỏ advice
    """
    conflicting_item_1: List[str] = Field(
        ..., 
        description="Nhóm nguyên liệu thứ nhất bị xung khắc (VD: ['Bò'])"
    )
    conflicting_item_2: List[str] = Field(
        ..., 
        description="Nhóm nguyên liệu thứ hai bị xung khắc (VD: ['Phô mai'])"
    )
    message: str = Field(..., description="Thông báo lý do xung khắc")
    sources: List[ConflictSource] = Field(
        default_factory=list, 
        description="Các nguồn tham khảo về xung khắc này"
    )
    severity: Optional[str] = Field(
        default="medium", 
        description="Mức độ nghiêm trọng: low, medium, high"
    )
    id: Optional[str] = Field(None, description="ID định danh xung khắc")


class IngredientItem(BaseModel):
    """Thông tin nguyên liệu trong giỏ hàng"""
    ingredient_id: str = Field(..., description="ID nguyên liệu")
    name_vi: str = Field(..., description="Tên tiếng Việt")
    quantity: str = Field(default="", description="Số lượng")
    unit: str = Field(default="", description="Đơn vị")
    category: Optional[str] = Field(None, description="Danh mục nguyên liệu")
    note: Optional[str] = Field(None, description="Ghi chú bổ sung")


class DishInfo(BaseModel):
    """Thông tin món ăn"""
    name: str = Field(..., description="Tên món ăn")
    prep_time: Optional[str] = Field(None, description="Thời gian chuẩn bị")
    servings: Optional[int] = Field(None, description="Số người ăn")


class CartInfo(BaseModel):
    """Thông tin giỏ hàng"""
    total_items: int = Field(..., description="Tổng số nguyên liệu")
    items: List[IngredientItem] = Field(..., description="Danh sách nguyên liệu")


class Warning(BaseModel):
    """Cảnh báo chung"""
    message: str = Field(..., description="Nội dung cảnh báo")
    severity: str = Field(default="warning", description="Mức độ: info, warning, error")
    source: str = Field(default="model", description="Nguồn cảnh báo")
    details: Optional[Dict[str, Any]] = Field(None, description="Chi tiết bổ sung")


class RecipeAnalysisRequest(BaseModel):
    """
    Request body cho endpoint phân tích công thức
    Main Service sẽ gửi yêu cầu phân tích món ăn
    """
    user_input: str = Field(
        ..., 
        description="Mô tả món ăn từ người dùng (text hoặc text từ speech-to-text)",
        examples=["Tôi muốn nấu phở bò và thêm trứng cút"]
    )
    image_base64: Optional[str] = Field(
        None, 
        description="Ảnh món ăn dạng base64 (nếu có)"
    )
    image_description: Optional[str] = Field(
        None, 
        description="Mô tả ảnh (nếu có)"
    )
    image_mime_type: Optional[str] = Field(
        default="image/png",
        description="MIME type của ảnh"
    )


class RecipeAnalysisResponse(BaseModel):
    """
    Response body cho endpoint phân tích công thức
    AI Service trả về kết quả phân tích đầy đủ
    """
    status: str = Field(
        ..., 
        description="Trạng thái: success, error, guardrail_blocked"
    )
    dish: Optional[DishInfo] = Field(None, description="Thông tin món ăn")
    cart: Optional[CartInfo] = Field(None, description="Giỏ hàng nguyên liệu")
    
    # Conflict warnings với format MỚI
    conflict_warnings: List[ConflictWarning] = Field(
        default_factory=list,
        description="Danh sách xung khắc giữa các nguyên liệu (format mới: conflicting_item_1 + conflicting_item_2)"
    )
    
    suggestions: List[IngredientItem] = Field(
        default_factory=list,
        description="Gợi ý nguyên liệu bổ sung"
    )
    similar_dishes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Món ăn tương tự"
    )
    warnings: List[Warning] = Field(
        default_factory=list,
        description="Các cảnh báo khác (guardrail, validation, etc.)"
    )
    insights: List[str] = Field(
        default_factory=list,
        description="Thông tin hữu ích về dinh dưỡng, xung khắc"
    )
    assistant_response: Optional[str] = Field(
        None,
        description="Phản hồi văn bản từ AI assistant"
    )
    error: Optional[str] = Field(None, description="Thông báo lỗi (nếu có)")
    guardrail: Optional[Dict[str, Any]] = Field(None, description="Thông tin guardrail")


class HealthCheckResponse(BaseModel):
    """Response cho health check endpoint"""
    status: str = Field(..., description="Trạng thái service")
    service: str = Field(..., description="Tên service")
    version: str = Field(..., description="Phiên bản")
