from datetime import datetime
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
    reference_name: Optional[str] = "Default Database"
    active_model: str
    fallback_models: List[str]


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str = "ok"


# Database Connection Schemas
class ConnectionCreate(BaseModel):
    reference_name: str = Field(..., description="Unique alias name for this database connection", example="Production Analytics DB")
    db_type: str = Field(..., description="Database dialect: postgresql, mysql, or sqlite", example="postgresql")
    host: Optional[str] = Field(None, example="localhost")
    port: Optional[int] = Field(None, example=5432)
    database_name: Optional[str] = Field(None, example="text_to_sql_db")
    username: Optional[str] = Field(None, example="postgres")
    password: Optional[str] = Field(None, example="secret123")
    extra_params: Optional[str] = Field(None, description="Custom SQLite filepath or connection options")
    set_as_active: Optional[bool] = Field(False, description="Immediately activate this connection after saving")


class ConnectionUpdate(BaseModel):
    reference_name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    extra_params: Optional[str] = None
    is_active: Optional[bool] = None


class ConnectionResponse(BaseModel):
    id: int
    reference_name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    has_password: bool = False
    extra_params: Optional[str] = None
    is_active: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConnectionTestRequest(BaseModel):
    db_type: str = Field(..., example="postgresql")
    host: Optional[str] = Field(None, example="localhost")
    port: Optional[int] = Field(None, example=5432)
    database_name: Optional[str] = Field(None, example="text_to_sql_db")
    username: Optional[str] = Field(None, example="postgres")
    password: Optional[str] = Field(None, example="secret123")
    extra_params: Optional[str] = None


class ConnectionTestResponse(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    dialect: Optional[str] = None
    table_count: Optional[int] = None
    tables: Optional[List[str]] = []
    error: Optional[str] = None
