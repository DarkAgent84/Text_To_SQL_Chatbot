"""
Production Database Engine Manager & Dynamic Connection Switcher.
"""

import time
import logging
import datetime
import threading
from decimal import Decimal
from typing import Generator, List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus
import uuid

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import QueuePool, NullPool

from app.config import settings

logger = logging.getLogger(__name__)

# Mutex lock for thread-safe dynamic target engine switching
_ENGINE_LOCK = threading.Lock()

# 1. App State Metadata Engine (persists chats, messages, and saved connections)
APP_METADATA_DB_URL = settings.APP_METADATA_DB_URL
engine = create_engine(
    APP_METADATA_DB_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in APP_METADATA_DB_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_metadata_db():
    """Initializes metadata tables and ensures required schema columns exist."""
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            # Auto-migrate chats columns if needed
            chats_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(chats)")).fetchall()]
            if chats_cols and "title" not in chats_cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN title VARCHAR(255) DEFAULT 'New Conversation'"))
            if chats_cols and "updated_at" not in chats_cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN updated_at DATETIME"))

            # Auto-migrate messages columns if needed
            msg_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()]
            if msg_cols and "model_used" not in msg_cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN model_used VARCHAR(100)"))
            if msg_cols and "execution_time_ms" not in msg_cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN execution_time_ms INTEGER"))
            conn.commit()
    except Exception as e:
        logger.debug(f"Metadata DB check notice: {e}")


# Initialize metadata schema immediately
init_metadata_db()

# 2. Dynamic Target Engine State (for executing queries against user databases)
_active_target_engine: Optional[Engine] = None
_active_connection_info: Dict[str, Any] = {
    "id": None,
    "reference_name": "Default Database",
    "db_type": "sqlite",
    "database_name": "app.db",
    "host": "localhost",
    "port": None,
    "is_active": True
}


def build_db_url(
    db_type: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    database_name: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    extra_params: Optional[str] = None
) -> str:
    """Builds a standard SQLAlchemy connection string from parameters."""
    db_type_clean = (db_type or "sqlite").strip().lower()

    if extra_params and extra_params.strip().startswith(("postgresql://", "postgresql+psycopg2://", "mysql://", "mysql+pymysql://", "sqlite://")):
        return extra_params.strip()

    if db_type_clean == "sqlite":
        path = extra_params or database_name or "./app.db"
        if not path.startswith("sqlite:///"):
            path = f"sqlite:///{path}"
        return path

    user_enc = quote_plus(username) if username else ""
    pass_enc = quote_plus(password) if password else ""
    auth_part = f"{user_enc}:{pass_enc}@" if (user_enc or pass_enc) else ""

    if db_type_clean in ("postgres", "postgresql"):
        p = port or 5432
        h = host or "localhost"
        db = database_name or "postgres"
        return f"postgresql+psycopg2://{auth_part}{h}:{p}/{db}"

    elif db_type_clean == "mysql":
        p = port or 3306
        h = host or "localhost"
        db = database_name or "mysql"
        return f"mysql+pymysql://{auth_part}{h}:{p}/{db}"

    return settings.DATABASE_URL


def create_managed_engine(url: str) -> Engine:
    """Factory creating robust, pooled SQLAlchemy engines."""
    if "sqlite" in url:
        return create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": settings.MAX_EXECUTION_TIMEOUT_SEC}
        )
    else:
        return create_engine(
            url,
            poolclass=QueuePool,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_recycle=settings.DB_POOL_RECYCLE_SEC,
            pool_pre_ping=True,
            connect_args={"connect_timeout": settings.MAX_EXECUTION_TIMEOUT_SEC}
        )


def test_db_connection_params(
    db_type: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    database_name: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    extra_params: Optional[str] = None
) -> Dict[str, Any]:
    """Tests live connection reachability, latency, and extracts sample table names."""
    url = build_db_url(db_type, host, port, database_name, username, password, extra_params)
    temp_engine = create_managed_engine(url)
    start_time = time.perf_counter()
    try:
        with temp_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        inspector = inspect(temp_engine)
        table_names = inspector.get_table_names()
        # Exclude internal metadata tables
        user_tables = [
            t for t in table_names
            if t.lower() not in ["chats", "messages", "saved_connections", "_ingestion_metadata", "sqlite_sequence"]
        ]

        return {
            "status": "success",
            "latency_ms": latency_ms,
            "dialect": temp_engine.dialect.name,
            "table_count": len(user_tables),
            "tables": user_tables[:15]
        }
    finally:
        temp_engine.dispose()


def get_target_engine() -> Engine:
    """Returns the currently active target database engine with thread safety."""
    global _active_target_engine
    with _ENGINE_LOCK:
        if _active_target_engine is None:
            url = settings.DATABASE_URL
            _active_target_engine = create_managed_engine(url)
        return _active_target_engine


def set_active_target_engine(connection_obj, db: Session) -> Dict[str, Any]:
    """Thread-safely switches the active target engine and invalidates the schema cache."""
    global _active_target_engine, _active_connection_info
    from app.core.models import DatabaseConnection

    with _ENGINE_LOCK:
        db.query(DatabaseConnection).update({DatabaseConnection.is_active: False})
        connection_obj.is_active = True
        db.commit()
        db.refresh(connection_obj)

        url = build_db_url(
            db_type=connection_obj.db_type,
            host=connection_obj.host,
            port=connection_obj.port,
            database_name=connection_obj.database_name,
            username=connection_obj.username,
            password=connection_obj.password,
            extra_params=connection_obj.extra_params
        )

        if _active_target_engine is not None and _active_target_engine != engine:
            try:
                _active_target_engine.dispose()
            except Exception as e:
                logger.warning(f"Error disposing previous engine: {e}")

        _active_target_engine = create_managed_engine(url)
        _active_connection_info = {
            "id": connection_obj.id,
            "reference_name": connection_obj.reference_name,
            "db_type": connection_obj.db_type,
            "database_name": connection_obj.database_name or "app.db",
            "host": connection_obj.host or "localhost",
            "port": connection_obj.port,
            "is_active": True
        }

    # Invalidate cached schema so new database schema is extracted immediately
    from app.core.db_schema import invalidate_schema_cache
    invalidate_schema_cache()

    logger.info(f"Switched active database engine to: {_active_connection_info['reference_name']} ({_active_connection_info['db_type']})")
    return _active_connection_info


def reset_active_target_engine_to_default(db: Optional[Session] = None) -> Dict[str, Any]:
    """Resets the active target engine to default SQLite database."""
    global _active_target_engine, _active_connection_info
    with _ENGINE_LOCK:
        if db is not None:
            from app.core.models import DatabaseConnection
            try:
                db.query(DatabaseConnection).update({DatabaseConnection.is_active: False})
                db.commit()
            except Exception:
                pass

        if _active_target_engine is not None and _active_target_engine != engine:
            try:
                _active_target_engine.dispose()
            except Exception:
                pass

        url = settings.DATABASE_URL
        _active_target_engine = create_managed_engine(url)
        _active_connection_info = {
            "id": None,
            "reference_name": "Default Database",
            "db_type": "sqlite",
            "database_name": "app.db",
            "host": "localhost",
            "port": None,
            "is_active": True
        }

    from app.core.db_schema import invalidate_schema_cache
    invalidate_schema_cache()

    return _active_connection_info


def get_active_connection_info() -> Dict[str, Any]:
    global _active_connection_info
    with _ENGINE_LOCK:
        return dict(_active_connection_info)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for app metadata database session lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_value(val: Any) -> Any:
    """Safe serialization of SQL cell values to JSON-serializable Python types."""
    if val is None:
        return None
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return f"<blob: {len(val)} bytes>"
    if isinstance(val, uuid.UUID):
        return str(val)
    return val


def execute_query(sql: str) -> Tuple[List[Dict[str, Any]], int]:
    """
    Executes SQL against the currently active target database engine with
    row limit clamping and execution latency tracking.
    Returns (results, execution_time_ms).
    """
    target = get_target_engine()
    start_time = time.perf_counter()
    
    with target.connect() as connection:
        result = connection.execute(text(sql))
        exec_ms = int(round((time.perf_counter() - start_time) * 1000))
        
        if result.returns_rows:
            columns = list(result.keys())
            rows = result.fetchmany(settings.MAX_RETURN_ROWS)
            serialized_rows = [
                {k: serialize_value(v) for k, v in dict(zip(columns, row)).items()}
                for row in rows
            ]
            return serialized_rows, exec_ms
        else:
            return [{"affected_rows": result.rowcount}], exec_ms


def get_chat_history(chat_id: int, db: Session) -> List[Any]:
    from app.core.models import Message
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.timestamp.asc())
        .all()
    )
