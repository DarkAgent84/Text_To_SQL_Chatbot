"""
Application Configuration and Environment Settings.
"""

import os
from pathlib import Path
from typing import List
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Production configuration settings with environment variable fallbacks."""
    PROJECT_NAME: str = "Text-to-SQL Chatbot"
    VERSION: str = "2.5.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # Gemini LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_FALLBACK_MODELS: List[str] = field(default_factory=lambda: [
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-flash-lite-latest"
    ])

    # Database Settings
    _BASE_DIR: str = str(Path(__file__).resolve().parent.parent).replace("\\", "/")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_BASE_DIR}/app.db").strip().replace("\\", "/")
    APP_METADATA_DB_URL: str = os.getenv("APP_METADATA_DB_URL", f"sqlite:///{_BASE_DIR}/app.db").strip().replace("\\", "/")
    
    # Connection Pool Settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_RECYCLE_SEC: int = int(os.getenv("DB_POOL_RECYCLE_SEC", "3600"))
    DB_POOL_TIMEOUT_SEC: int = int(os.getenv("DB_POOL_TIMEOUT_SEC", "30"))

    # Query Execution Guardrails
    MAX_ROWS_FOR_LLM: int = int(os.getenv("MAX_ROWS_FOR_LLM", "50"))
    MAX_RETURN_ROWS: int = int(os.getenv("MAX_RETURN_ROWS", "1000"))
    MAX_EXECUTION_TIMEOUT_SEC: int = int(os.getenv("MAX_EXECUTION_TIMEOUT_SEC", "15"))

    # Uploads & File Processing
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parent.parent / "data" / "uploads"))

    # CORS
    CORS_ORIGINS: List[str] = field(default_factory=lambda: ["*"])


settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
