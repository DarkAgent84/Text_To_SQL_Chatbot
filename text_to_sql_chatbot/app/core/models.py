"""
SQLAlchemy ORM Data Models for Application Metadata.
"""

from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, DateTime, Boolean, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


class Chat(Base):
    """Chat session model with cascading message cleanup."""
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=True, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.timestamp"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title or f"Chat #{self.id}",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": len(self.messages) if self.messages else 0
        }


class Message(Base):
    """Individual question, generated SQL, execution results, and AI answer."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    sql_query = Column(Text, nullable=False)
    sql_result = Column(JSON, nullable=True)
    answer = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    chat = relationship("Chat", back_populates="messages")

    __table_args__ = (
        Index("idx_messages_chat_timestamp", "chat_id", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "question": self.question,
            "sql_query": self.sql_query,
            "sql_result": self.sql_result,
            "answer": self.answer,
            "model_used": self.model_used,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class DatabaseConnection(Base):
    """Stored database connection profiles for PostgreSQL, MySQL, and SQLite."""
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
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self, mask_password: bool = True) -> Dict[str, Any]:
        return {
            "id": self.id,
            "reference_name": self.reference_name,
            "db_type": self.db_type,
            "host": self.host or "localhost",
            "port": self.port,
            "database_name": self.database_name,
            "username": self.username,
            "password": "••••••••" if (self.password and mask_password) else self.password,
            "extra_params": self.extra_params,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
