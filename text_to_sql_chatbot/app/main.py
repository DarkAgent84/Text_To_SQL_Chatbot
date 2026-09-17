"""
Enterprise FastAPI Main Application Entrypoint.
"""

import time
import uuid
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.core.database import Base, engine
from app.api.endpoints import router as api_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("text_to_sql_chatbot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan lifecycle: initializes database metadata tables and cleans up on shutdown."""
    logger.info(f"[{settings.PROJECT_NAME}] Starting enterprise server v{settings.VERSION} (env: {settings.ENVIRONMENT})...")
    Base.metadata.create_all(bind=engine)
    
    # Auto-migrate columns for existing SQLite database files
    try:
        with engine.connect() as conn:
            # Check chats columns
            chats_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(chats)")).fetchall()]
            if "title" not in chats_cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN title VARCHAR(255) DEFAULT 'New Conversation'"))
            if "updated_at" not in chats_cols:
                conn.execute(text("ALTER TABLE chats ADD COLUMN updated_at DATETIME"))
                
            # Check messages columns
            msg_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(messages)")).fetchall()]
            if "model_used" not in msg_cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN model_used VARCHAR(100)"))
            if "execution_time_ms" not in msg_cols:
                conn.execute(text("ALTER TABLE messages ADD COLUMN execution_time_ms INTEGER"))
            conn.commit()
    except Exception as e:
        logger.warning(f"Schema auto-migration check notice: {e}")

    yield
    logger.info(f"[{settings.PROJECT_NAME}] Server shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-Ready Text-to-SQL AI Chatbot with Dynamic Schema Reflection & Data Profiling.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


# ----------------------------------------------------------------------
# Middlewares
# ----------------------------------------------------------------------

# Request ID & Latency Tracking Middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.perf_counter()
    request.state.request_id = request_id

    response = await call_next(request)

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(latency_ms)

    if not request.url.path.startswith(("/static", "/favicon.ico")):
        logger.info(f"[{request_id}] {request.method} {request.url.path} -> status {response.status_code} ({latency_ms}ms)")

    return response


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# Global Exception Handlers
# ----------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "code": "VALIDATION_FAILED",
            "detail": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"[{req_id}] Unhandled Server Exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "code": "INTERNAL_SERVER_ERROR",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred. Please try again."
        }
    )


# ----------------------------------------------------------------------
# Routers & Static Mounts
# ----------------------------------------------------------------------

# Mount API Endpoints (both /api/v1 and root for backwards compatibility)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router)

# Mount Web Application Static Files
static_path = Path(__file__).resolve().parent.parent / "static"
if static_path.exists():
    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
