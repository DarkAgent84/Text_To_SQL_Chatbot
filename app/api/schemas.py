from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str = Field(..., description="Natural language question to query database", example="How many active customers are in Pune?")
    chat_id: Optional[int] = Field(None, description="Optional conversation/chat ID for context history", example=1)


class QuestionResponse(BaseModel):
    chat_id: int = Field(..., alias="Chat Id")
    question: str = Field(..., alias="Question")
    sql_query: str = Field(..., alias="SQL Query")
    sql_results: List[Dict[str, Any]] = Field(..., alias="SQL Results")
    answer: str = Field(..., alias="Answer")
    model_used: Optional[str] = Field(None, alias="Model Used")
    database_used: Optional[str] = Field(None, alias="Database Used")

    class Config:
        populate_by_name = True


class SystemInfoResponse(BaseModel):
    database: str
    dialect: str
    active_model: str
    fallback_models: List[str]


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str = "ok"
