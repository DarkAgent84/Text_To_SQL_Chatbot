from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Union

from app.api.schemas import QuestionRequest, QuestionResponse, ErrorResponse, HealthResponse, SystemInfoResponse
from app.core.database import get_db, execute_query, get_chat_history
from app.core.models import Chat, Message
from app.core.sql_guard import is_safe_query
from app.services.llm_service import generate_sql, interpret_result, correct_sql_query, get_system_info

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health():
    return HealthResponse(status="ok")


@router.get("/system-info", response_model=SystemInfoResponse, tags=["Health"])
def system_info():
    return get_system_info()


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
