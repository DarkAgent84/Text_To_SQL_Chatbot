from fastapi import FastAPI
from app.database import Base, engine, SessionLocal, execute_query, get_chat_history
from app.models import Chat, Message
from app.llm import generate_sql, interpret_result
from app.sql_guard import is_safe_query
from app import models
from pydantic import BaseModel
from typing import Optional
from google.genai.errors import APIError

Base.metadata.create_all(bind=engine)

app = FastAPI()

class QuestionRequest(BaseModel):
    question: str
    chat_id: Optional[int] = None

@app.get("/")
def read_root():
    return {"message": "Text-To-SQL Chatbot backend is running."}

@app.get("/health")
def get_health():
    return {"status": "ok"}

@app.post("/ask")
def ask_question(request: QuestionRequest):
    db = SessionLocal()
    try:
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

        try:
            sql = generate_sql(request.question, history_text)
        except Exception as e:
            return {"error": "The AI service is temporarily unavailable, please try again in a moment."}

        if not is_safe_query(sql):
            return {
                "error": "This chatbot can only retrieve information, not modify or delete data. Please rephrase your question as a request to view or analyze data."
            }

        answer = execute_query(sql)
        try:
            interpreted_answer = interpret_result(request.question, answer)
        except Exception as e:
            return {"error": "The AI service is temporarily unavailable, please try again in a moment."}

        message = Message(
            chat_id=chat_id,
            question=request.question,
            sql_query=sql,
            sql_result=answer,
            answer=interpreted_answer
        )
        db.add(message)
        db.commit()

        return {
            "Chat Id": chat_id,
            "Question": request.question,
            "SQL Query": sql,
            "SQL Results": answer,
            "Answer": interpreted_answer,
        }
    finally:
        db.close()