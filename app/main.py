from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.database import Base, engine
from app.api.endpoints import router as api_router

# Ensure local metadata database tables (chats, messages, saved_connections) exist
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[{settings.PROJECT_NAME}] Starting server v{settings.VERSION}...")
    yield
    print(f"[{settings.PROJECT_NAME}] Server shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise Text-to-SQL AI Chatbot with dynamic database schema reflection.",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Endpoints (both /api/v1 and root for backwards compatibility)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router)

# Mount Static Web Application
app.mount("/", StaticFiles(directory="static", html=True), name="static")
