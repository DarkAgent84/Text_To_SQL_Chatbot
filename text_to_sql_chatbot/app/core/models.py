from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, DateTime, Boolean
from app.core.database import Base


class Chat(Base):
    """Chat session model."""
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    """Individual question and answer interaction within a chat session."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    question = Column(Text, nullable=False)
    sql_query = Column(Text, nullable=False)
    sql_result = Column(JSON, nullable=True)
    answer = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class DatabaseConnection(Base):
    """Stored connection profiles for PostgreSQL, MySQL, and SQLite."""
    __tablename__ = "saved_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reference_name = Column(String(100), unique=True, nullable=False, index=True)
    db_type = Column(String(20), nullable=False, default="postgresql")
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    database_name = Column(String(100), nullable=True)
    username = Column(String(100), nullable=True)
    password = Column(String(255), nullable=True)
    extra_params = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
