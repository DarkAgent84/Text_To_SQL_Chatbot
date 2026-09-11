from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Union, List, Dict, Any

from app.api.schemas import (
    QuestionRequest, QuestionResponse, ErrorResponse, HealthResponse, SystemInfoResponse,
    ConnectionCreate, ConnectionUpdate, ConnectionResponse, ConnectionTestRequest, ConnectionTestResponse
)
from app.core.database import (
    get_db, execute_query, get_chat_history, test_db_connection_params,
    set_active_target_engine, get_active_connection_info, get_target_engine
)
from app.core.models import Chat, Message, DatabaseConnection
from app.core.sql_guard import is_safe_query
from app.services.llm_service import generate_sql, interpret_result, correct_sql_query, get_system_info

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health():
    return HealthResponse(status="ok")


@router.get("/system-info", response_model=SystemInfoResponse, tags=["Health"])
def system_info():
    return get_system_info()


# ==========================================
# Database Connection Management Endpoints
# ==========================================

def format_connection_response(conn: DatabaseConnection) -> Dict[str, Any]:
    return {
        "id": conn.id,
        "reference_name": conn.reference_name,
        "db_type": conn.db_type,
        "host": conn.host,
        "port": conn.port,
        "database_name": conn.database_name,
        "username": conn.username,
        "has_password": bool(conn.password),
        "extra_params": conn.extra_params,
        "is_active": bool(conn.is_active),
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }


@router.get("/connections", response_model=List[ConnectionResponse], tags=["Connections"])
def list_connections(db: Session = Depends(get_db)):
    """List all saved database connection profiles."""
    connections = db.query(DatabaseConnection).order_by(DatabaseConnection.created_at.desc()).all()
    return [format_connection_response(c) for c in connections]


@router.get("/connections/active", tags=["Connections"])
def get_active_connection(db: Session = Depends(get_db)):
    """Get currently active connection information and status."""
    active = db.query(DatabaseConnection).filter(DatabaseConnection.is_active == True).first()
    if active:
        return format_connection_response(active)
    return get_active_connection_info()


@router.post("/connections/test", response_model=ConnectionTestResponse, tags=["Connections"])
def test_connection_endpoint(payload: ConnectionTestRequest):
    """Test connection credentials and reachability without saving."""
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


@router.post("/connections", response_model=ConnectionResponse, tags=["Connections"])
def create_connection(payload: ConnectionCreate, db: Session = Depends(get_db)):
    """Create and save a new database connection profile."""
    # Check if reference name already exists
    existing = db.query(DatabaseConnection).filter(
        DatabaseConnection.reference_name == payload.reference_name.strip()
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A connection with Reference Name '{payload.reference_name}' already exists. Please choose a unique name."
        )

    # Optional test verification before saving
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database connection test failed: {str(e)}"
        )

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

    # If requested to set active immediately or if it's the first connection
    if payload.set_as_active:
        set_active_target_engine(new_conn, db)

    return format_connection_response(new_conn)


@router.put("/connections/{connection_id}", response_model=ConnectionResponse, tags=["Connections"])
def update_connection(connection_id: int, payload: ConnectionUpdate, db: Session = Depends(get_db)):
    """Update an existing database connection profile."""
    conn = db.query(DatabaseConnection).filter(DatabaseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if payload.reference_name:
        existing = db.query(DatabaseConnection).filter(
            DatabaseConnection.reference_name == payload.reference_name.strip(),
            DatabaseConnection.id != connection_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Reference name already exists.")
        conn.reference_name = payload.reference_name.strip()

    if payload.db_type:
        conn.db_type = payload.db_type.strip().lower()
    if payload.host is not None:
        conn.host = payload.host
    if payload.port is not None:
        conn.port = payload.port
    if payload.database_name is not None:
        conn.database_name = payload.database_name
    if payload.username is not None:
        conn.username = payload.username
    if payload.password is not None and payload.password != "":
        conn.password = payload.password
    if payload.extra_params is not None:
        conn.extra_params = payload.extra_params

    db.commit()
    db.refresh(conn)

    if conn.is_active:
        set_active_target_engine(conn, db)

    return format_connection_response(conn)


@router.delete("/connections/{connection_id}", tags=["Connections"])
def delete_connection(connection_id: int, db: Session = Depends(get_db)):
    """Delete a saved database connection profile."""
    conn = db.query(DatabaseConnection).filter(DatabaseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    was_active = conn.is_active
    db.delete(conn)
    db.commit()

    if was_active:
        # Fallback to another connection or default
        next_conn = db.query(DatabaseConnection).first()
        if next_conn:
            set_active_target_engine(next_conn, db)

    return {"status": "deleted", "id": connection_id}


@router.post("/connections/{connection_id}/activate", tags=["Connections"])
def activate_connection(connection_id: int, db: Session = Depends(get_db)):
    """Activate a database connection profile for the chatbot."""
    conn = db.query(DatabaseConnection).filter(DatabaseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    try:
        active_info = set_active_target_engine(conn, db)
        return {
            "status": "activated",
            "connection": format_connection_response(conn),
            "system_info": get_system_info()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to database: {str(e)}"
        )


# ==========================================
# Chatbot Question & Inference Endpoint
# ==========================================

@router.post(
    "/ask",
    response_model=Union[QuestionResponse, ErrorResponse],
    responses={
        200: {"model": QuestionResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    tags=["Chatbot"]
)
def ask_question(request: QuestionRequest, db: Session = Depends(get_db)):
    chat = None
    if request.chat_id is not None and request.chat_id > 0:
        chat = db.query(Chat).filter(Chat.id == request.chat_id).first()

    if chat is None:
        new_chat = Chat()
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        chat_id = new_chat.id
    else:
        chat_id = chat.id

    history = get_chat_history(chat_id, db)
    history_text = "\n".join(
        f"Q: {m.question}\nA: {m.answer}" for m in history
    )

    used_model = "Gemini AI"
    try:
        sql, sql_model = generate_sql(request.question, history_text)
        used_model = sql_model
    except Exception as e:
        print(f"[API Error] generate_sql failed: {e}")
        import traceback
        traceback.print_exc()
        return ErrorResponse(error=f"The AI service is temporarily unavailable: {str(e)}")

    if not is_safe_query(sql):
        return ErrorResponse(
            error="This chatbot can only retrieve information, not modify or delete data. Please rephrase your question as a request to view or analyze data."
        )

    # Attempt query execution with LLM Self-Correction Loop (up to 2 retries)
    answer = None
    last_error = None
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            answer = execute_query(sql)
            break
        except Exception as exec_err:
            last_error = str(exec_err)
            print(f"[SelfCorrection] Execution attempt {attempt + 1} failed: {last_error}")
            if attempt < max_retries:
                try:
                    sql, corr_model = correct_sql_query(request.question, sql, last_error, history_text)
                    used_model = corr_model
                    if not is_safe_query(sql):
                        break
                    print(f"[SelfCorrection] Generated corrected SQL (Attempt {attempt + 2}): {sql}")
                except Exception as corr_err:
                    print(f"[SelfCorrection] Correction failed: {corr_err}")
                    break

    if answer is None:
        return ErrorResponse(error=f"Error executing generated SQL query: {last_error}")

    try:
        interpreted_answer, interp_model = interpret_result(request.question, answer)
        used_model = interp_model
    except Exception as e:
        print(f"[API Error] interpret_result failed: {e}")
        import traceback
        traceback.print_exc()
        return ErrorResponse(error=f"The AI service is temporarily unavailable: {str(e)}")

    message = Message(
        chat_id=chat_id,
        question=request.question,
        sql_query=sql,
        sql_result=answer,
        answer=interpreted_answer
    )
    db.add(message)
    db.commit()

    sys_info = get_system_info()

    return {
        "Chat Id": chat_id,
        "Question": request.question,
        "SQL Query": sql,
        "SQL Results": answer,
        "Answer": interpreted_answer,
        "Model Used": used_model,
        "Database Used": sys_info.get("database", "Active Database")
    }
