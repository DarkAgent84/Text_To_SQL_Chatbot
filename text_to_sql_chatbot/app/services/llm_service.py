"""
AI / LLM Service: Text-to-SQL Generation, Self-Correction, and Data Interpretation.
"""

import json
import time
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from google import genai

from app.config import settings
from app.core.database import get_target_engine, get_active_connection_info
from app.core.db_schema import get_db_schema

logger = logging.getLogger(__name__)


def get_client() -> genai.Client:
    """Initializes and returns a Google GenAI Client with API key validation."""
    key = settings.GEMINI_API_KEY
    if not key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is missing or empty. "
            "Please add GEMINI_API_KEY=your_key_here to your .env file."
        )
    return genai.Client(api_key=key)


def generate_content_with_fallback(contents: str) -> Tuple[Any, str]:
    """
    Attempts to generate content using the configured GEMINI_MODEL.
    If transient network errors, rate limits (429), or model unavailabilities occur,
    it automatically retries with backoff and cascades through fallback models.
    """
    models_to_try = [settings.GEMINI_MODEL]
    for candidate in settings.GEMINI_FALLBACK_MODELS:
        if candidate.lower() not in [m.lower() for m in models_to_try]:
            models_to_try.append(candidate)

    last_exception = None
    fatal_auth_keywords = ["api_key_invalid", "permission_denied", "unauthenticated", "invalid_api_key"]

    for idx, model_name in enumerate(models_to_try):
        max_attempts_per_model = 2
        for attempt in range(max_attempts_per_model):
            try:
                client = get_client()
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                )
                return response, model_name
            except Exception as e:
                last_exception = e
                err_str = str(e).lower()

                # If API key itself is completely invalid, fail fast
                if any(k in err_str for k in fatal_auth_keywords):
                    raise e

                # Retryable network/service errors
                if attempt < max_attempts_per_model - 1:
                    wait_sec = (attempt + 1) * 1.5
                    logger.warning(f"[Model Retry] '{model_name}' attempt {attempt + 1} failed: {e}. Retrying in {wait_sec}s...")
                    time.sleep(wait_sec)
                    continue
                else:
                    next_model = models_to_try[idx + 1] if idx + 1 < len(models_to_try) else "none"
                    logger.warning(f"[Model Fallback] '{model_name}' failed after {max_attempts_per_model} attempts ({e}). Falling back to '{next_model}'...")
                    break

    raise last_exception or RuntimeError("Failed to generate content from Gemini AI.")


def get_dialect_rules() -> Tuple[str, str]:
    """Returns the SQL dialect name and syntax guidelines for the active database engine."""
    target = get_target_engine()
    dialect_name = target.dialect.name.upper()

    if dialect_name in ("POSTGRESQL", "POSTGRES"):
        rules = (
            "- Use standard PostgreSQL functions (e.g. EXTRACT(YEAR FROM date_col), TO_CHAR(), NOW(), ILIKE for case-insensitive search).\n"
            "- Double-quote table and column names if they contain uppercase letters or spaces (e.g. \"Total Amount\")."
        )
    elif dialect_name == "MYSQL":
        rules = (
            "- Use standard MySQL functions (e.g. YEAR(date_col), DATE_FORMAT(), NOW(), IFNULL()).\n"
            "- Use backticks for reserved table/column names if needed (e.g. `order`, `group`)."
        )
    else:
        rules = (
            "- Use standard SQLite functions (e.g. strftime('%Y', date_col), DATE('now'), IFNULL(), COALESCE()).\n"
            "- Double-quote or backtick column names containing special characters or spaces."
        )

    return dialect_name, rules


def get_system_info() -> Dict[str, Any]:
    """Returns metadata about the active database engine and LLM configuration."""
    target = get_target_engine()
    dialect_name = target.dialect.name.upper()
    active_info = get_active_connection_info()

    ref_name = active_info.get("reference_name", "Default Database")
    db_name_str = active_info.get("database_name", "app.db")
    db_display = f"{ref_name} ({dialect_name} - {db_name_str})"

    return {
        "database": db_display,
        "dialect": dialect_name,
        "reference_name": ref_name,
        "active_model": settings.GEMINI_MODEL,
        "fallback_models": settings.GEMINI_FALLBACK_MODELS
    }


def generate_sql(question: str, history: str = "") -> Tuple[str, str]:
    """Generates an executable read-only SQL query from natural language using the exact extracted schema."""
    schema_text = get_db_schema()
    dialect_name, dialect_rules = get_dialect_rules()

    prompt = f"""You are an expert Text-to-SQL database engineer specializing in {dialect_name}.
Generate a single, precise, executable {dialect_name} read-only SQL query to answer the user's question.

Guidelines:
1. Output ONLY the raw executable SQL query. Do not wrap in markdown quotes (```sql), do not include comments or explanations.
2. Carefully inspect the exact Column Data Types and Table Schemas provided below.
3. {dialect_rules}
4. Use ONLY columns and tables that exist in the Schema.
5. If column sample values are provided in brackets (e.g. [samples: ...]), use exact matching strings.
6. The query MUST strictly be a read-only SELECT or WITH ... SELECT statement.
7. Always use meaningful column aliases when aggregating (e.g. SELECT SUM(amount) AS total_amount).

Database Schema with Exact Data Types:
{schema_text}

Conversation Context:
{history if history else "No previous conversation."}

User Question: {question}

Raw Executable SQL Query:"""

    response, used_model = generate_content_with_fallback(prompt)
    sql = clean_sql_output(response.text)
    return sql, used_model


def correct_sql_query(question: str, broken_sql: str, error_message: str, history: str = "") -> Tuple[str, str]:
    """Self-correction loop: generates a corrected SQL query given the database error message."""
    schema_text = get_db_schema()
    dialect_name, dialect_rules = get_dialect_rules()

    prompt = f"""You are an expert SQL query debugger for {dialect_name}.
The previously generated SQL query encountered a database execution error.
Analyze the error traceback and exact schema, then output ONLY a corrected, executable SQL query.

Rules:
- Output ONLY the raw executable SQL query without markdown code blocks or explanations.
- {dialect_rules}
- Adhere strictly to the column data types and relationships in the schema below.

Database Schema:
{schema_text}

Question: {question}

Broken SQL:
{broken_sql}

Database Execution Error:
{error_message}

Corrected Executable SQL Query:"""

    response, used_model = generate_content_with_fallback(prompt)
    sql = clean_sql_output(response.text)
    return sql, used_model


def interpret_result(question: str, sql_result: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Converts tabular SQL query results into a concise, plain-English executive summary."""
    preview_data = sql_result[:settings.MAX_ROWS_FOR_LLM]
    result_json = json.dumps(preview_data, default=str)

    prompt = f"""You are a professional business intelligence data analyst.
Explain the following SQL query results in response to the user's question.

Question: {question}
Query Results ({len(sql_result)} rows total):
{result_json}

Guidelines:
- Provide a clear, natural, and concise answer directly addressing the question.
- Highlight key totals, trends, or notable statistics if present.
- Format numerical amounts and counts nicely for readability (e.g. $1.2M, 4,500, etc.)."""

    response, used_model = generate_content_with_fallback(prompt)
    return response.text.strip(), used_model


def suggest_chart_recommendation(question: str, sql_query: str, sql_result: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes query result structure and suggests the best visual chart type (bar, line, pie, doughnut, or none).
    """
    if not sql_result or len(sql_result) <= 1:
        return {"suggested": False, "chart_type": "none"}

    first_row = sql_result[0]
    keys = list(first_row.keys())
    if len(keys) < 2:
        return {"suggested": False, "chart_type": "none"}

    # Find string/categorical dimension column (x-axis) and numeric measure column (y-axis)
    str_cols = []
    num_cols = []

    for k, v in first_row.items():
        if isinstance(v, (int, float)) and not any(id_k in k.lower() for id_k in ["id", "code", "year"]):
            num_cols.append(k)
        elif isinstance(v, str) or any(id_k in k.lower() for id_k in ["year", "month", "date", "status", "type", "category", "zone", "state", "branch", "name"]):
            str_cols.append(k)

    if str_cols and num_cols:
        x_key = str_cols[0]
        y_key = num_cols[0]

        # Determine best chart type
        q_lower = question.lower()
        if any(w in q_lower for w in ["trend", "over time", "monthly", "daily", "timeline", "yearly"]) or "date" in x_key.lower() or "year" in x_key.lower() or "month" in x_key.lower():
            chart_type = "line"
        elif any(w in q_lower for w in ["share", "proportion", "breakdown", "percentage", "distribution", "ratio"]) and len(sql_result) <= 8:
            chart_type = "doughnut" if "doughnut" in q_lower else "pie"
        else:
            chart_type = "bar"

        return {
            "suggested": True,
            "chart_type": chart_type,
            "x_axis_key": x_key,
            "y_axis_key": y_key,
            "label": y_key.replace("_", " ").title()
        }

    return {"suggested": False, "chart_type": "none"}


def clean_sql_output(raw_sql: str) -> str:
    """Strips markdown code blocks, backticks, and trailing semicolons from LLM SQL output."""
    sql = raw_sql.strip()
    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql
