import json
from typing import List, Dict, Any, Tuple
from google import genai

from app.config import settings
from app.core.database import get_target_engine, get_active_connection_info
from app.core.db_schema import get_db_schema


def get_client() -> genai.Client:
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
    If a rate limit (429), quota limit, or transient 503 occurs,
    automatically switches to candidate fallback models.
    """
    client = get_client()
    models_to_try = [settings.GEMINI_MODEL]
    fallback_candidates = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest"
    ]
    for candidate in fallback_candidates:
        if candidate.lower() not in [m.lower() for m in models_to_try]:
            models_to_try.append(candidate)

    last_exception = None
    for idx, model_name in enumerate(models_to_try):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
            )
            return response, model_name
        except Exception as e:
            last_exception = e
            err_str = str(e).lower()
            if any(k in err_str for k in ["429", "resource_exhausted", "quota", "503", "unavailable", "404", "not_found"]):
                next_model = models_to_try[idx + 1] if idx + 1 < len(models_to_try) else "none"
                print(f"[Model Fallback] '{model_name}' unavailable ({e}). Retrying with '{next_model}'...")
                continue
            raise e

    raise last_exception or RuntimeError("Failed to generate content from Gemini.")


def get_dialect_rules() -> Tuple[str, str]:
    target = get_target_engine()
    dialect_name = target.dialect.name.upper()

    if dialect_name == "POSTGRESQL":
        rules = "Use standard PostgreSQL functions (e.g., EXTRACT(YEAR FROM date_col), TO_CHAR(), NOW(), ILIKE for case-insensitive search)."
    elif dialect_name == "MYSQL":
        rules = "Use standard MySQL functions (e.g., YEAR(date_col), DATE_FORMAT(), NOW(), IFNULL()). Use backticks for reserved table/column names if needed."
    else:
        rules = "Use standard SQLite functions (e.g., strftime('%Y', date_col), DATE('now'), IFNULL())."

    return dialect_name, rules


def get_system_info() -> Dict[str, Any]:
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
        "fallback_models": [
            "gemini-2.5-flash",
            "gemini-1.5-flash",
            "gemini-3.5-flash",
            "gemini-3.7-flash",
            "gemini-flash-latest"
        ]
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
- Format numerical amounts and counts nicely for readability."""

    response, used_model = generate_content_with_fallback(prompt)
    return response.text.strip(), used_model


def clean_sql_output(raw_sql: str) -> str:
    """Strips markdown code blocks, backticks, and extra whitespace from LLM SQL output."""
    sql = raw_sql.strip()
    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql
