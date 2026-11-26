import datetime
from decimal import Decimal
from typing import Generator, List, Dict, Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for managing database session lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_value(val: Any) -> Any:
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return val


def execute_query(sql: str) -> List[Dict[str, Any]]:
    with engine.connect() as connection:
        result = connection.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()
        return [
            {k: serialize_value(v) for k, v in dict(zip(columns, row)).items()}
            for row in rows
        ]


def get_chat_history(chat_id: int, db: Session):
    from app.core.models import Message
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.timestamp)
        .all()
    )
    return messages
