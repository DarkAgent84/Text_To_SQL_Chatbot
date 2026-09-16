import datetime
import time
from decimal import Decimal
from typing import Generator, List, Dict, Any, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.config import settings

# 1. App State Metadata Engine (persists chats, messages, and saved connections)
APP_METADATA_DB_URL = "sqlite:///./app.db"
engine = create_engine(APP_METADATA_DB_URL, pool_pre_ping=True, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    auth_part = f"{user_enc}:{pass_enc}@" if user_enc or pass_enc else ""

    if db_type_clean in ["postgres", "postgresql"]:
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
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}

    temp_engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    start_time = time.perf_counter()
    try:
        with temp_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        inspector = inspect(temp_engine)
        table_names = inspector.get_table_names()
        # Exclude internal metadata tables
        user_tables = [t for t in table_names if t.lower() not in ["chats", "messages", "saved_connections", "_ingestion_metadata", "sqlite_sequence"]]

        return {
            "status": "success",
            "latency_ms": latency_ms,
            "dialect": temp_engine.dialect.name,
            "table_count": len(user_tables),
            "tables": user_tables[:12]
        }
    finally:
        temp_engine.dispose()


def get_target_engine() -> Engine:
    """Returns the currently active target database engine."""
    global _active_target_engine
    if _active_target_engine is None:
        url = settings.DATABASE_URL
        connect_args = {"check_same_thread": False} if "sqlite" in url else {}
        _active_target_engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    return _active_target_engine


def set_active_target_engine(connection_obj, db: Session) -> Dict[str, Any]:
    """Switches the active target engine and invalidates the schema cache."""
    global _active_target_engine, _active_connection_info
    from app.core.models import DatabaseConnection

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
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}

    if _active_target_engine is not None and _active_target_engine != engine:
        try:
            _active_target_engine.dispose()
        except Exception:
            pass

    _active_target_engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
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

    return _active_connection_info


def reset_active_target_engine_to_default(db: Optional[Session] = None) -> Dict[str, Any]:
    """Resets the active target engine to default SQLite database."""
    global _active_target_engine, _active_connection_info
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
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    _active_target_engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
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
    return _active_connection_info


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for app metadata database session lifecycle."""
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
    """Executes SQL against the currently active target database engine."""
    target = get_target_engine()
    with target.connect() as connection:
        result = connection.execute(text(sql))
        if result.returns_rows:
            rows = result.fetchall()
            columns = result.keys()
            return [
                {k: serialize_value(v) for k, v in dict(zip(columns, row)).items()}
                for row in rows
            ]
        return [{"affected_rows": result.rowcount}]


def get_chat_history(chat_id: int, db: Session):
    from app.core.models import Message
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.timestamp)
        .all()
    )
