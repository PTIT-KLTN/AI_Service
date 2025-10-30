# Pydantic schemas for AI Service
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ConflictSource(BaseModel):
    name: str
    url: str


class ConflictWarning(BaseModel):
    conflicting_item_1: List[str]
    conflicting_item_2: List[str]
    message: str
    sources: List[ConflictSource] = Field(default_factory=list)
    severity: Optional[str] = "medium"
    id: Optional[str] = None


class IngredientItem(BaseModel):
    ingredient_id: str
    name_vi: str
    quantity: str = ""
    unit: str = ""
    category: Optional[str] = None
    note: Optional[str] = None


class DishInfo(BaseModel):
    name: str
    prep_time: Optional[str] = None
    servings: Optional[int] = None


class CartInfo(BaseModel):
    total_items: int
    items: List[IngredientItem]


class Warning(BaseModel):
    message: str
    severity: str = "warning"
    source: str = "model"
    details: Optional[Dict[str, Any]] = None


class RecipeAnalysisRequest(BaseModel):
    user_input: Optional[str] = None
    s3_url: Optional[str] = None
    image_s3_url: Optional[str] = None
    description: Optional[str] = None
    image_description: Optional[str] = None


class RecipeAnalysisResponse(BaseModel):
    status: str
    dish: Optional[DishInfo] = None
    cart: Optional[CartInfo] = None
    conflict_warnings: List[ConflictWarning] = Field(default_factory=list)
    suggestions: List[IngredientItem] = Field(default_factory=list)
    similar_dishes: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Warning] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    assistant_response: Optional[str] = None
    error: Optional[str] = None
    guardrail: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str
