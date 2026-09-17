"""
REST API Endpoints for Chat, Database Connections, Dataset Ingestion, and Analytics.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, text

from app.config import settings
from app.core.database import (
    get_db,
    get_target_engine,
    get_active_connection_info,
    set_active_target_engine,
    reset_active_target_engine_to_default,
    test_db_connection_params,
    execute_query,
    get_chat_history
)
from app.core.models import Chat, Message, DatabaseConnection
from app.core.db_schema import get_db_schema, invalidate_schema_cache
from app.core.sql_guard import validate_sql_safety
from app.core.data_profiler import DatasetProfiler, clean_identifier
from app.services.llm_service import (
    generate_sql,
    correct_sql_query,
    interpret_result,
    suggest_chart_recommendation,
    get_system_info
)
from app.api.schemas import (
    ChatCreate,
    ChatResponse,
    AskQuestionRequest,
    AskQuestionResponse,
    MessageDetail,
    ConnectionTestRequest,
    ConnectionTestResponse,
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    DatasetProfileRequest,
    DatasetIngestRequest,
    DatasetIngestResponse,
    HealthResponse,
    ErrorResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ======================================================================
# System & Health Check Endpoints
# ======================================================================

@router.get("/health", response_model=HealthResponse, tags=["Health"])
@router.get("/health/live", tags=["Health"])
@router.get("/health/ready", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Production health check verifying database and LLM service readiness."""
    db_status = "healthy"
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "unhealthy"
        db_error = str(e)

    sys_info = get_system_info()

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": settings.VERSION,
        "database": {
            "status": db_status,
            "active_connection": sys_info.get("database"),
            "dialect": sys_info.get("dialect"),
            "error": db_error
        },
        "llm": {
            "status": "configured" if bool(settings.GEMINI_API_KEY) else "missing_api_key",
            "active_model": settings.GEMINI_MODEL,
            "fallbacks": settings.GEMINI_FALLBACK_MODELS
        }
    }


@router.get("/system/info", tags=["System"])
def system_information():
    """Returns active database connection information and model config."""
    return get_system_info()


# ======================================================================
# Chat & Message Endpoints
# ======================================================================

@router.post("/chats", response_model=ChatResponse, status_code=status.HTTP_201_CREATED, tags=["Chats"])
def create_chat_session(payload: Optional[ChatCreate] = None, db: Session = Depends(get_db)):
    """Creates a new conversation session."""
    title = payload.title.strip() if (payload and payload.title) else "New Conversation"
    chat = Chat(title=title)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat.to_dict()


@router.get("/chats", response_model=List[ChatResponse], tags=["Chats"])
def list_chats(limit: int = 50, db: Session = Depends(get_db)):
    """Lists recent conversation sessions."""
    chats = db.query(Chat).order_by(desc(Chat.updated_at)).limit(limit).all()
    return [c.to_dict() for c in chats]


@router.get("/chats/{chat_id}", response_model=ChatResponse, tags=["Chats"])
def get_chat_session(chat_id: int, db: Session = Depends(get_db)):
    """Gets details of a specific chat session."""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return chat.to_dict()


@router.put("/chats/{chat_id}", response_model=ChatResponse, tags=["Chats"])
def rename_chat_session(chat_id: int, payload: ChatCreate, db: Session = Depends(get_db)):
    """Renames an existing chat session."""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if payload.title:
        chat.title = payload.title.strip()
        db.commit()
        db.refresh(chat)
    return chat.to_dict()


@router.delete("/chats/{chat_id}", tags=["Chats"])
def delete_chat_session(chat_id: int, db: Session = Depends(get_db)):
    """Deletes a chat session and all associated messages."""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat session not found")
    db.delete(chat)
    db.commit()
    return {"status": "success", "message": f"Chat #{chat_id} deleted successfully"}


@router.get("/chats/{chat_id}/messages", response_model=List[MessageDetail], tags=["Messages"])
def get_chat_messages(chat_id: int, db: Session = Depends(get_db)):
    """Returns chronological message history for a chat session."""
    messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.timestamp.asc()).all()
    return [m.to_dict() for m in messages]


@router.post("/chats/{chat_id}/messages", response_model=AskQuestionResponse, tags=["Query Execution"])
@router.post("/ask", response_model=AskQuestionResponse, tags=["Query Execution"])
def ask_question(
    request: AskQuestionRequest,
    chat_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Core Text-to-SQL Execution Pipeline:
    1. Extracts schema context & conversation history.
    2. Generates dialect-aware SQL via Gemini.
    3. Validates query safety against SQL Guard.
    4. Executes query with automated Self-Correction loop on errors.
    5. Converts tabular results into a natural language executive summary.
    6. Recommends visual chart configuration.
    """
    # Create or retrieve chat session
    if chat_id is None:
        chat = Chat(title=request.question[:45] + "..." if len(request.question) > 45 else request.question)
        db.add(chat)
        db.commit()
        db.refresh(chat)
        chat_id = chat.id
    else:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            chat = Chat(id=chat_id, title=request.question[:45])
            db.add(chat)
            db.commit()

    # Build conversation context for multi-turn reasoning
    past_messages = get_chat_history(chat_id, db)
    history_lines = []
    for msg in past_messages[-5:]:
        history_lines.append(f"User: {msg.question}")
        history_lines.append(f"SQL: {msg.sql_query}")
        history_lines.append(f"Answer: {msg.answer}")
    history_text = "\n".join(history_lines)

    # 1. Generate SQL Query
    try:
        sql, used_model = generate_sql(request.question, history_text)
    except Exception as e:
        logger.error(f"SQL Generation Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI SQL generation service error: {str(e)}"
        )

    # 2. Validate SQL Safety
    is_safe, violation_reason = validate_sql_safety(sql)
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security Guardrail Triggered: {violation_reason}"
        )

    # 3. Execute Query with Self-Correction Loop (up to 2 retries)
    answer_rows = None
    exec_time_ms = 0
    last_exec_error = None
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            answer_rows, exec_time_ms = execute_query(sql)
            break
        except Exception as exec_err:
            last_exec_error = str(exec_err)
            logger.warning(f"[SelfCorrection] Execution attempt {attempt + 1} failed: {last_exec_error}")
            
            if attempt < max_retries:
                try:
                    sql, used_model = correct_sql_query(request.question, sql, last_exec_error, history_text)
                    is_safe, violation_reason = validate_sql_safety(sql)
                    if not is_safe:
                        break
                    logger.info(f"[SelfCorrection] Generated corrected SQL (Attempt {attempt + 2}): {sql}")
                except Exception as corr_err:
                    logger.error(f"[SelfCorrection] Correction call failed: {corr_err}")
                    break

    if answer_rows is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database execution failed: {last_exec_error}"
        )

    # 4. Generate Natural Language Interpretation
    try:
        interpreted_answer, used_model = interpret_result(request.question, answer_rows)
    except Exception as e:
        logger.warning(f"Result interpretation warning: {e}")
        interpreted_answer = f"Found {len(answer_rows)} records matching your query."

    # 5. Chart Recommendation
    chart_info = suggest_chart_recommendation(request.question, sql, answer_rows)

    # 6. Save Interaction to Database
    msg = Message(
        chat_id=chat_id,
        question=request.question,
        sql_query=sql,
        sql_result=answer_rows,
        answer=interpreted_answer,
        model_used=used_model,
        execution_time_ms=exec_time_ms
    )
    db.add(msg)
    
    # Auto-update chat title if default
    if chat.title in ("New Conversation", None):
        chat.title = request.question[:50]
        
    db.commit()

    sys_info = get_system_info()

    return {
        "chat_id": chat_id,
        "question": request.question,
        "sql_query": sql,
        "sql_results": answer_rows,
        "answer": interpreted_answer,
        "model_used": used_model,
        "database_used": sys_info.get("database", "Active Target DB"),
        "execution_time_ms": exec_time_ms,
        "row_count": len(answer_rows),
        "chart": chart_info
    }


# ======================================================================
# Database Connection Management Endpoints
# ======================================================================

@router.post("/connections/test", response_model=ConnectionTestResponse, tags=["Connections"])
def test_connection_endpoint(payload: ConnectionTestRequest):
    """Tests live database reachability and returns table counts and sample tables."""
    try:
        result = test_db_connection_params(
            db_type=payload.db_type,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            password=payload.password,
            extra_params=payload.extra_params
        )
        return ConnectionTestResponse(**result)
    except Exception as e:
        return ConnectionTestResponse(status="failed", error=str(e), table_count=0, tables=[])


@router.post("/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED, tags=["Connections"])
def create_connection(payload: ConnectionCreate, db: Session = Depends(get_db)):
    """Saves a new database connection profile and optionally activates it."""
    existing = db.query(DatabaseConnection).filter(
        DatabaseConnection.reference_name == payload.reference_name.strip()
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Connection name '{payload.reference_name}' is already in use."
        )

    # Test reachability
    try:
        test_db_connection_params(
            db_type=payload.db_type,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            password=payload.password,
            extra_params=payload.extra_params
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection verification failed: {str(e)}")

    new_conn = DatabaseConnection(
        reference_name=payload.reference_name.strip(),
        db_type=payload.db_type.strip().lower(),
        host=payload.host,
        port=payload.port,
        database_name=payload.database_name,
        username=payload.username,
        password=payload.password,
        extra_params=payload.extra_params,
        is_active=False
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)

    if payload.set_as_active:
        set_active_target_engine(new_conn, db)

    return new_conn.to_dict()


@router.get("/connections", response_model=List[ConnectionResponse], tags=["Connections"])
def list_connections(db: Session = Depends(get_db)):
    """Lists all saved database connections with masked credentials."""
    conns = db.query(DatabaseConnection).order_by(DatabaseConnection.created_at.desc()).all()
    return [c.to_dict(mask_password=True) for c in conns]


@router.post("/connections/{connection_id}/activate", tags=["Connections"])
def activate_connection(connection_id: int, db: Session = Depends(get_db)):
    """Switches active database target engine to the selected saved connection."""
    conn = db.query(DatabaseConnection).filter(DatabaseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    info = set_active_target_engine(conn, db)
    return {"status": "success", "active_connection": info}


@router.post("/connections/reset-default", tags=["Connections"])
def reset_to_default_database(db: Session = Depends(get_db)):
    """Resets the active target database engine to the default SQLite app.db."""
    info = reset_active_target_engine_to_default(db)
    return {"status": "success", "active_connection": info}


@router.delete("/connections/{connection_id}", tags=["Connections"])
def delete_connection(connection_id: int, db: Session = Depends(get_db)):
    """Deletes a saved database connection profile."""
    conn = db.query(DatabaseConnection).filter(DatabaseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if conn.is_active:
        reset_active_target_engine_to_default(db)

    db.delete(conn)
    db.commit()
    return {"status": "success", "message": "Connection deleted"}


# ======================================================================
# Dataset Upload & Profiling Endpoints
# ======================================================================

@router.post("/datasets/upload", tags=["Datasets"])
async def upload_dataset_file(file: UploadFile = File(...)):
    """Uploads a dataset file (Excel, CSV, TSV, JSON) to the upload repository."""
    allowed_extensions = {".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt", ".json", ".jsonl"}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_ext}'. Allowed types: {', '.join(sorted(allowed_extensions))}"
        )

    dest_path = Path(settings.UPLOAD_DIR) / file.filename
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "status": "success",
        "file_name": file.filename,
        "file_size_bytes": os.path.getsize(dest_path),
        "file_path": str(dest_path)
    }


@router.get("/datasets", tags=["Datasets"])
def list_available_datasets():
    """Lists all available files in upload and data directories."""
    files = []
    scan_dirs = [Path(settings.UPLOAD_DIR), Path("./data"), Path("./text_to_sql_chatbot/data")]
    seen_names = set()

    for d in scan_dirs:
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in (".xlsx", ".xls", ".csv", ".tsv", ".json") and f.name not in seen_names:
                    seen_names.add(f.name)
                    files.append({
                        "file_name": f.name,
                        "file_size_bytes": f.stat().st_size,
                        "file_path": str(f.resolve()),
                        "directory": str(d)
                    })

    return {"datasets": files}


@router.post("/datasets/profile", tags=["Datasets"])
def profile_dataset_endpoint(payload: DatasetProfileRequest):
    """Profiles a dataset and returns column semantic types, statistical metrics, and LLM schema markdown."""
    file_path = None
    for search_dir in [Path(settings.UPLOAD_DIR), Path("./data"), Path("./text_to_sql_chatbot/data"), Path(".")]:
        candidate = search_dir / payload.file_name
        if candidate.exists():
            file_path = str(candidate.resolve())
            break

    if not file_path:
        raise HTTPException(status_code=404, detail=f"File '{payload.file_name}' not found.")

    profiler = DatasetProfiler(sample_size=payload.sample_size)
    try:
        profiles = profiler.profile_file(file_path, sheet_name=payload.sheet_name)
        markdown_blocks = [profiler.to_llm_markdown(p) for p in profiles]
        ddl_blocks = [profiler.to_sql_ddl(p) for p in profiles]
        
        return {
            "status": "success",
            "file_name": payload.file_name,
            "table_count": len(profiles),
            "tables": [p.to_dict() for p in profiles],
            "llm_markdown": "\n\n---\n\n".join(markdown_blocks),
            "sql_ddl": "\n\n".join(ddl_blocks)
        }
    except Exception as e:
        logger.error(f"Dataset profiling error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Profiling failed: {str(e)}")


@router.post("/datasets/ingest", response_model=DatasetIngestResponse, tags=["Datasets"])
def ingest_dataset_endpoint(payload: DatasetIngestRequest):
    """Ingests a dataset file into the active database engine as a clean SQL table."""
    file_path = None
    for search_dir in [Path(settings.UPLOAD_DIR), Path("./data"), Path("./text_to_sql_chatbot/data"), Path(".")]:
        candidate = search_dir / payload.file_name
        if candidate.exists():
            file_path = str(candidate.resolve())
            break

    if not file_path:
        raise HTTPException(status_code=404, detail=f"File '{payload.file_name}' not found.")

    profiler = DatasetProfiler()
    target_engine = get_target_engine()

    try:
        import pandas as pd
        profiles = profiler.profile_file(file_path, sheet_name=payload.sheet_name)
        total_rows = 0
        final_table_name = ""

        for prof in profiles:
            tname = clean_identifier(payload.table_name) if payload.table_name else prof.clean_table_name
            final_table_name = tname

            if file_path.endswith((".xlsx", ".xls", ".xlsm")):
                df = pd.read_excel(file_path, sheet_name=prof.sheet_name)
            else:
                df = profiler._read_csv_robust(file_path)

            # Map column names to clean SQL identifiers
            col_map = {col.name: col.clean_name for col in prof.columns}
            df = df.rename(columns=col_map)

            # Ingest into active target database
            df.to_sql(tname, target_engine, if_exists="replace", index=False)
            total_rows += len(df)

        # Invalidate schema cache so the new table is immediately queryable
        invalidate_schema_cache()

        return DatasetIngestResponse(
            status="success",
            table_name=final_table_name,
            rows_ingested=total_rows,
            columns_count=len(df.columns),
            message=f"Successfully ingested {total_rows:,} rows into table '{final_table_name}'."
        )

    except Exception as e:
        logger.error(f"Dataset ingestion error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Ingestion failed: {str(e)}")


# ======================================================================
# Schema Inspection Endpoints
# ======================================================================

@router.get("/schema", tags=["Schema"])
def get_current_schema(refresh: bool = False):
    """Returns the reflected SQL schema of the active database engine."""
    schema_text = get_db_schema(force_refresh=refresh)
    sys_info = get_system_info()
    return {
        "database": sys_info.get("database"),
        "dialect": sys_info.get("dialect"),
        "schema": schema_text
    }


@router.post("/schema/refresh", tags=["Schema"])
def refresh_schema():
    """Forces an immediate cache invalidation and schema re-reflection."""
    invalidate_schema_cache()
    schema_text = get_db_schema(force_refresh=True)
    return {"status": "success", "schema": schema_text}
