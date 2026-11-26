from datetime import datetime
from sqlalchemy import Column, Integer, Text, ForeignKey, JSON, DateTime
from app.core.database import Base


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, autoincrement=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    question = Column(Text)
    sql_query = Column(Text)
    sql_result = Column(JSON)
    answer = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

