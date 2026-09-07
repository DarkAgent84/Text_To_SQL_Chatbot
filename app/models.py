from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey, Numeric, DateTime, JSON
from datetime import datetime
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True)
    customer_name = Column(String(100))
    email = Column(String(100))
    phone = Column(String(20))
    city = Column(String(50))
    state = Column(String(50))
    signup_date = Column(Date)
    customer_segment = Column(String(20))
    is_active = Column(Integer)

class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"))
    employee_id = Column(Integer, ForeignKey("employees.employee_id"))
    order_date = Column(Date)
    order_status = Column(String(20))
    shipping_city = Column(String(50)) 

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