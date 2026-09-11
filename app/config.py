import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Text-to-SQL Chatbot"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"

    # Gemini LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Optional Default Database URL (fallback to local app.db)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db").strip()

    # Query Execution Guardrails
    MAX_ROWS_FOR_LLM: int = int(os.getenv("MAX_ROWS_FOR_LLM", "50"))
    MAX_EXECUTION_TIMEOUT_SEC: int = int(os.getenv("MAX_EXECUTION_TIMEOUT_SEC", "15"))


settings = Settings()
