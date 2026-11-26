from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.database import Base, engine
from app.core.auto_ingest import auto_ingest_if_needed
from app.api.endpoints import router as api_router

# Ensure DB tables are created
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically ingest dataset files into DB on server startup if needed
    try:
        auto_ingest_if_needed()
    except Exception as e:
        print(f"[Startup Warning] Auto-ingestion failed: {e}")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise-grade Text-to-SQL Chatbot powered by Google Gemini and FastAPI.",
    lifespan=lifespan
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Endpoints first
app.include_router(api_router)

# Mount Static Files (Web UI Dashboard) at Root /
app.mount("/", StaticFiles(directory="static", html=True), name="static")

