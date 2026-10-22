"""
Pydantic Request and Response Schemas for the REST API.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# Chat & Message Schemas
# ----------------------------------------------------------------------

class ChatCreate(BaseModel):
    title: Optional[str] = Field(default=None, description="Optional title for the chat session")


class ChatResponse(BaseModel):
    id: int
    title: str
    created_at: Optional[str]
    updated_at: Optional[str]
    message_count: int = 0


class AskQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Natural language question to query against the active database")


class ChartSuggestion(BaseModel):
    suggested: bool = False
    chart_type: str = "none"
    x_axis_key: Optional[str] = None
    y_axis_key: Optional[str] = None
    label: Optional[str] = None


class AskQuestionResponse(BaseModel):
    chat_id: int
    question: str
    sql_query: str
    sql_results: List[Dict[str, Any]]
    answer: str
    model_used: Optional[str] = None
    database_used: Optional[str] = None
    execution_time_ms: Optional[int] = 0
    row_count: int = 0
    chart: Optional[ChartSuggestion] = None

    # Title-case aliases for frontend backwards compatibility
    Answer: Optional[str] = None
    SQL_Query: Optional[str] = Field(default=None, alias="SQL Query")
    SQL_Results: Optional[List[Dict[str, Any]]] = Field(default=None, alias="SQL Results")
    Model_Used: Optional[str] = Field(default=None, alias="Model Used")
    Database_Used: Optional[str] = Field(default=None, alias="Database Used")
    Chat_Id: Optional[int] = Field(default=None, alias="Chat Id")

    model_config = {"populate_by_name": True, "extra": "allow"}



class MessageDetail(BaseModel):
    id: int
    chat_id: int
    question: str
    sql_query: str
    sql_result: Optional[List[Dict[str, Any]]] = None
    answer: str
    model_used: Optional[str] = None
    execution_time_ms: Optional[int] = None
    timestamp: Optional[str] = None


# ----------------------------------------------------------------------
# Connection Management Schemas
# ----------------------------------------------------------------------

class ConnectionTestRequest(BaseModel):
    db_type: str = Field("postgresql", description="Database dialect: postgresql, mysql, or sqlite")
    host: Optional[str] = Field(default="localhost")
    port: Optional[int] = Field(default=None)
    database_name: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    extra_params: Optional[str] = Field(default=None)


class ConnectionTestResponse(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    dialect: Optional[str] = None
    table_count: int = 0
    tables: List[str] = []
    error: Optional[str] = None


class ConnectionCreate(BaseModel):
    reference_name: str = Field(..., min_length=1, max_length=100)
    db_type: str = Field("postgresql")
    host: Optional[str] = Field(default="localhost")
    port: Optional[int] = Field(default=None)
    database_name: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    extra_params: Optional[str] = Field(default=None)
    set_as_active: bool = Field(default=False)


class ConnectionUpdate(BaseModel):
    reference_name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    extra_params: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: int
    reference_name: str
    db_type: str
    host: Optional[str] = "localhost"
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    extra_params: Optional[str] = None
    is_active: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ----------------------------------------------------------------------
# Dataset Upload & Profiler Schemas
# ----------------------------------------------------------------------

class DatasetProfileRequest(BaseModel):
    file_name: str
    sheet_name: Optional[str] = None
    sample_size: Optional[int] = None


class DatasetIngestRequest(BaseModel):
    file_name: str
    table_name: Optional[str] = None
    sheet_name: Optional[str] = None
    connection_id: Optional[int] = None


class DatasetIngestResponse(BaseModel):
    status: str
    table_name: str
    rows_ingested: int
    columns_count: int
    message: str


# ----------------------------------------------------------------------
# System & Health Schemas
# ----------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str
    database: Dict[str, Any]
    llm: Dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    code: Optional[str] = "INTERNAL_ERROR"
    detail: Optional[Any] = None


# ----------------------------------------------------------------------
# Dashboard & Dynamic Metrics Schemas
# ----------------------------------------------------------------------

class MetricFilterSpec(BaseModel):
    column: str
    operator: str = "="
    value: Any


class MetricBuilderSpec(BaseModel):
    table: str
    column: Optional[str] = "*"
    aggregation: str = "COUNT"
    filters: Optional[List[MetricFilterSpec]] = []
    group_by: Optional[str] = None


class MetricEvaluationRequest(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = None
    title: Optional[str] = "Custom Metric"
    mode: str = "builder"  # builder, sql, manual, formula
    sql: Optional[str] = None
    builder: Optional[MetricBuilderSpec] = None
    manual_value: Optional[Any] = None
    format: Optional[str] = "number"
    unit: Optional[str] = ""
    trend: Optional[str] = None
    target: Optional[float] = None
    color: Optional[str] = "blue"
    icon: Optional[str] = "chart"
    global_filters: Optional[Dict[str, Any]] = None


class DashboardConfigSaveRequest(BaseModel):
    connection_id: Optional[int] = None
    name: Optional[str] = "default"
    config: Dict[str, Any]

