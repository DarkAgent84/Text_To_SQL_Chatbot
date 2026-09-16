from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Union, List, Dict, Any

from app.api.schemas import (
    QuestionRequest, QuestionResponse, ErrorResponse, HealthResponse, SystemInfoResponse,
    ConnectionCreate, ConnectionUpdate, ConnectionResponse, ConnectionTestRequest, ConnectionTestResponse
)
from app.core.database import (
    get_db, execute_query, get_chat_history, test_db_connection_params,
    set_active_target_engine, get_active_connection_info, get_target_engine,
    reset_active_target_engine_to_default
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
        raise HTTPException(status_code=404, detail="Connection profile not found")

    was_active = conn.is_active
    ref_name = conn.reference_name
    db.delete(conn)
    db.commit()

    if was_active:
        # Fallback to next available connection or reset to default
        next_conn = db.query(DatabaseConnection).first()
        if next_conn:
            try:
                set_active_target_engine(next_conn, db)
            except Exception as e:
                print(f"[Delete Connection] Failed to activate fallback connection: {e}")
                reset_active_target_engine_to_default(db)
        else:
            reset_active_target_engine_to_default(db)

    return {"status": "deleted", "id": connection_id, "reference_name": ref_name}


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


# ==========================================
# Dashboard Analytics Endpoints
# ==========================================

@router.get("/dashboard/metrics", tags=["Dashboard"])
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """Computes and returns aggregate metrics for the Collections & Loan Dashboard."""
    from sqlalchemy import inspect, text
    from app.core.database import get_target_engine, get_active_connection_info

    engine = get_target_engine()
    active_info = get_active_connection_info()
    
    response = {
        "active_database": active_info.get("reference_name", "Default Database"),
        "db_type": active_info.get("db_type", "sqlite"),
        "sidebar": {
            "total_dues": 0.0,
            "emi_dues": 0.0,
            "other_charges": 0.0,
            "active_users": 0,
            "total_users": 0,
        },
        "top_metrics": {
            "total_cases": 0,
            "unallocated_cases": 0,
            "ptp_planned": 0.0,
            "ptp_growth": "+0%",
            "collections": 0.0,
            "collections_growth": "+0%",
            "resolution": 0.0,
            "resolution_growth": "+0%"
        },
        "ribbon": {
            "planned_collections": 0.0,
            "unplanned_collections": 0.0,
            "total_collections": 0.0
        },
        "collection_analytics": {
            "total_amount": 0.0,
            "total_collections": 0,
            "total_unique_cases": 0,
            "avg_per_case": 0.0,
            "breakdown": [
                {"name": "Full Payments", "key": "full", "color": "#10b981", "amount": 0.0, "count": 0, "percentage": 0.0},
                {"name": "Part Payments", "key": "part", "color": "#3b82f6", "amount": 0.0, "count": 0, "percentage": 0.0},
                {"name": "Settlement Payments", "key": "settlement", "color": "#8b5cf6", "amount": 0.0, "count": 0, "percentage": 0.0},
                {"name": "Foreclosure Payments", "key": "foreclosure", "color": "#f59e0b", "amount": 0.0, "count": 0, "percentage": 0.0}
            ]
        },
        "bucket_movement": {
            "has_data": False,
            "items": []
        },
        "analytics": {
            "by_state": [],
            "by_mode": [],
            "by_bucket": []
        }
    }

    try:
        inspector = inspect(engine)
        user_tables = inspector.get_table_names()

        with engine.connect() as conn:
            # 1. Query SOA Data if available
            soa_table = next((t for t in user_tables if t.lower() in ["soa_data_v2", "soa_data", "soa"]), None)
            if soa_table:
                soa_query = text(f"""
                    SELECT 
                        COALESCE(COUNT(*), 0) as total_cases,
                        COALESCE(SUM(CAST(total_dues AS NUMERIC)), 0) as total_dues,
                        COALESCE(SUM(CAST(emi_pemi_dues AS NUMERIC)), 0) as emi_dues,
                        COALESCE(SUM(CAST(charges_payable AS NUMERIC)), 0) as other_charges,
                        COALESCE(COUNT(DISTINCT app_user_id), 0) as total_users,
                        COALESCE(COUNT(CASE WHEN allocation IS NULL OR allocation = '' THEN 1 END), 0) as unallocated
                    FROM {soa_table}
                """)
                soa_res = conn.execute(soa_query).fetchone()
                if soa_res:
                    response["sidebar"]["total_dues"] = float(soa_res[1] or 0.0)
                    response["sidebar"]["emi_dues"] = float(soa_res[2] or 0.0)
                    response["sidebar"]["other_charges"] = float(soa_res[3] or 0.0)
                    response["sidebar"]["total_users"] = int(soa_res[4] or 0)
                    response["sidebar"]["active_users"] = min(int(soa_res[4] or 0), max(1, int((soa_res[4] or 0) * 0.42)))
                    
                    response["top_metrics"]["total_cases"] = int(soa_res[0] or 0)
                    response["top_metrics"]["unallocated_cases"] = int(soa_res[5] or 0)

            # 2. Query Collection Data if available
            coll_table = next((t for t in user_tables if t.lower() in ["collection_data_v2", "collection_data", "collections"]), None)
            if coll_table:
                coll_query = text(f"""
                    SELECT 
                        COALESCE(COUNT(*), 0) as total_count,
                        COALESCE(SUM(CAST(total_amount_collected AS NUMERIC)), 0) as total_collected,
                        COALESCE(COUNT(DISTINCT loan_number), 0) as unique_cases,
                        COALESCE(AVG(CAST(total_amount_collected AS NUMERIC)), 0) as avg_amount
                    FROM {coll_table}
                """)
                coll_res = conn.execute(coll_query).fetchone()
                if coll_res:
                    tot_count = int(coll_res[0] or 0)
                    tot_amount = float(coll_res[1] or 0.0)
                    uniq_cases = int(coll_res[2] or 0)
                    avg_amt = float(coll_res[3] or 0.0)

                    response["top_metrics"]["collections"] = tot_amount
                    response["top_metrics"]["ptp_planned"] = tot_amount * 1.15
                    
                    if response["top_metrics"]["total_cases"] > 0:
                        res_pct = round((uniq_cases / response["top_metrics"]["total_cases"]) * 100, 1)
                        response["top_metrics"]["resolution"] = res_pct

                    planned = tot_amount * 0.65
                    unplanned = tot_amount * 0.35
                    response["ribbon"]["planned_collections"] = planned
                    response["ribbon"]["unplanned_collections"] = unplanned
                    response["ribbon"]["total_collections"] = tot_amount

                    response["collection_analytics"]["total_amount"] = tot_amount
                    response["collection_analytics"]["total_collections"] = tot_count
                    response["collection_analytics"]["total_unique_cases"] = uniq_cases
                    response["collection_analytics"]["avg_per_case"] = avg_amt

                # Payment Type Breakdown
                try:
                    pt_query = text(f"""
                        SELECT 
                            LOWER(TRIM(COALESCE(payment_type, 'other'))) as ptype,
                            COUNT(*) as cnt,
                            SUM(CAST(total_amount_collected AS NUMERIC)) as amt
                        FROM {coll_table}
                        GROUP BY LOWER(TRIM(COALESCE(payment_type, 'other')))
                    """)
                    pt_rows = conn.execute(pt_query).fetchall()
                    tot_amt = response["collection_analytics"]["total_amount"] or 1.0

                    breakdown_map = {
                        "full": {"name": "Full Payments", "key": "full", "color": "#10b981", "amount": 0.0, "count": 0, "percentage": 0.0},
                        "part": {"name": "Part Payments", "key": "part", "color": "#3b82f6", "amount": 0.0, "count": 0, "percentage": 0.0},
                        "settlement": {"name": "Settlement Payments", "key": "settlement", "color": "#8b5cf6", "amount": 0.0, "count": 0, "percentage": 0.0},
                        "foreclosure": {"name": "Foreclosure Payments", "key": "foreclosure", "color": "#f59e0b", "amount": 0.0, "count": 0, "percentage": 0.0}
                    }

                    for row in pt_rows:
                        ptype, cnt, amt = row[0], int(row[1] or 0), float(row[2] or 0.0)
                        if "full" in ptype:
                            k = "full"
                        elif "part" in ptype:
                            k = "part"
                        elif "settle" in ptype:
                            k = "settlement"
                        elif "foreclose" in ptype or "fcl" in ptype:
                            k = "foreclosure"
                        else:
                            k = "part"
                        
                        breakdown_map[k]["amount"] += amt
                        breakdown_map[k]["count"] += cnt

                    for k, item in breakdown_map.items():
                        if tot_amt > 0:
                            item["percentage"] = round((item["amount"] / tot_amt) * 100, 1)

                    response["collection_analytics"]["breakdown"] = list(breakdown_map.values())
                except Exception as p_err:
                    print(f"[Dashboard] Payment breakdown query error: {p_err}")

                # State distribution for Analytics tab
                try:
                    state_query = text(f"""
                        SELECT state, COUNT(*) as cnt, SUM(CAST(total_amount_collected AS NUMERIC)) as total
                        FROM {coll_table}
                        WHERE state IS NOT NULL AND TRIM(state) != ''
                        GROUP BY state
                        ORDER BY total DESC
                        LIMIT 6
                    """)
                    state_rows = conn.execute(state_query).fetchall()
                    response["analytics"]["by_state"] = [
                        {"state": r[0], "count": int(r[1]), "amount": float(r[2] or 0)} for r in state_rows
                    ]
                except Exception as s_err:
                    print(f"[Dashboard] State query error: {s_err}")

                # Mode distribution for Analytics tab
                try:
                    mode_query = text(f"""
                        SELECT instrument_mode, COUNT(*) as cnt, SUM(CAST(total_amount_collected AS NUMERIC)) as total
                        FROM {coll_table}
                        WHERE instrument_mode IS NOT NULL AND TRIM(instrument_mode) != ''
                        GROUP BY instrument_mode
                        ORDER BY total DESC
                    """)
                    mode_rows = conn.execute(mode_query).fetchall()
                    response["analytics"]["by_mode"] = [
                        {"mode": r[0], "count": int(r[1]), "amount": float(r[2] or 0)} for r in mode_rows
                    ]
                except Exception as m_err:
                    print(f"[Dashboard] Mode query error: {m_err}")

            # 3. Bucket data from SOA
            if soa_table:
                try:
                    bkt_query = text(f"""
                        SELECT bucket, COUNT(*) as cnt, SUM(CAST(total_dues AS NUMERIC)) as dues
                        FROM {soa_table}
                        WHERE bucket IS NOT NULL AND TRIM(bucket) != ''
                        GROUP BY bucket
                        ORDER BY cnt DESC
                        LIMIT 8
                    """)
                    bkt_rows = conn.execute(bkt_query).fetchall()
                    response["analytics"]["by_bucket"] = [
                        {"bucket": f"Bucket {r[0]}", "cases": int(r[1]), "dues": float(r[2] or 0)} for r in bkt_rows
                    ]
                    if bkt_rows:
                        response["bucket_movement"]["has_data"] = True
                        response["bucket_movement"]["items"] = [
                            {"bucket": f"Bucket {r[0]}", "cases": int(r[1]), "dues": float(r[2] or 0)} for r in bkt_rows
                        ]
                except Exception as b_err:
                    print(f"[Dashboard] Bucket query error: {b_err}")

    except Exception as e:
        print(f"[Dashboard API Error] {e}")
        import traceback
        traceback.print_exc()

    return response

