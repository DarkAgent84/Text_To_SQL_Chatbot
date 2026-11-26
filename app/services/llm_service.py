from typing import List, Dict, Any
from google import genai

from app.config import settings
from app.core.database import engine
from app.core.db_schema import get_db_schema


def get_client() -> genai.Client:
    key = settings.GEMINI_API_KEY
    if not key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is missing or empty. "
            "Please add GEMINI_API_KEY=your_key_here to your .env file."
        )
    return genai.Client(api_key=key)


def generate_content_with_fallback(contents: str) -> tuple[Any, str]:
    """
    Attempts to generate content using the configured GEMINI_MODEL.
    If a rate limit (429), quota limit (RESOURCE_EXHAUSTED), or 503 capacity limit occurs,
    automatically switches to secondary candidate models (gemini-3.5-flash, gemini-3.6-flash, gemini-3.7-flash, gemini-flash-latest, etc.).
    Returns tuple of (response_object, model_name_used).
    """
    client = get_client()
    
    models_to_try = [settings.GEMINI_MODEL]
    fallback_candidates = [
        "gemini-flash-latest",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
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
            if any(k in err_str for k in ["getaddrinfo", "namerelocation", "dns", "connection error", "connecterror", "connection refused", "timeout"]):
                next_model = models_to_try[idx + 1] if idx + 1 < len(models_to_try) else "none"
                print(f"[Network Alert] Connection to Gemini API failed ({e}). Retrying with candidate model '{next_model}'...")
                continue
            if any(k in err_str for k in ["503", "capacity", "unavailable", "429", "resource_exhausted", "quota"]):
                next_model = models_to_try[idx + 1] if idx + 1 < len(models_to_try) else "none"
                print(f"[Model Fallback Alert] Rate limit or quota reached on '{model_name}'. Automatically switching to next candidate model '{next_model}'...")
                continue
            if "404" in err_str or "not_found" in err_str:
                next_model = models_to_try[idx + 1] if idx + 1 < len(models_to_try) else "none"
                print(f"[Model Fallback Alert] Model '{model_name}' non-existent/404. Switching to '{next_model}'...")
                continue
            raise e
            
    err_msg = str(last_exception)
    if any(k in err_msg.lower() for k in ["getaddrinfo", "dns", "connecterror", "connection"]):
        raise RuntimeError("Internet connection or DNS resolution to Google Gemini API failed (getaddrinfo). Please check your network connection and try again.")
    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
        raise RuntimeError("Gemini API rate limit or daily quota reached across available models. Please wait a moment or update your GEMINI_API_KEY in .env.")
    raise last_exception


def get_dialect_rules() -> tuple[str, str]:
    dialect_name = engine.dialect.name.upper()
    if dialect_name == "POSTGRESQL":
        rules = "Use standard PostgreSQL functions (e.g. EXTRACT(YEAR FROM payment_date), TO_CHAR(), NOW())."
    elif dialect_name == "MYSQL":
        rules = "Use standard MySQL functions (e.g. YEAR(), DATE_FORMAT(), NOW()). Use backticks for table and column names if needed."
    else:
        rules = "Use standard SQLite functions (e.g. strftime(), DATE())."
    return dialect_name, rules


def get_system_info() -> Dict[str, Any]:
    dialect_name = engine.dialect.name.upper()
    if dialect_name == "POSTGRESQL":
        db_name = f"PostgreSQL ({settings.POSTGRES_DB})"
    elif dialect_name == "MYSQL":
        db_name = f"MySQL ({settings.MYSQL_DB})"
    else:
        db_name = f"SQLite ({settings.DATABASE_URL.split('/')[-1]})"

    return {
        "database": db_name,
        "dialect": dialect_name,
        "active_model": settings.GEMINI_MODEL,
        "fallback_models": [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.7-flash",
            "gemini-flash-latest"
        ]
    }


from app.core.value_dictionary import build_categorical_value_dictionary


def test_connection() -> str:
    response, used_model = generate_content_with_fallback("Say hello in one short sentence.")
    return response.text


def generate_sql(question: str, history: str = "") -> tuple[str, str]:
    schema_text = get_db_schema()
    val_dict_text = build_categorical_value_dictionary()
    dialect_name, dialect_rules = get_dialect_rules()

    prompt = f"""You are an expert SQL query generator for {dialect_name} databases.
Given a database schema and a natural language question, generate ONLY the executable SQL query needed to answer it.
Do not include markdown code block formatting (e.g. ```sql), explanations, or anything other than the raw executable SQL query.

Rules:
- {dialect_rules}
- When joining tables, use explicit JOIN syntax with clear aliases.
- Use column names strictly as defined in the Schema below.
- Check the Categorical Value Reference below to map acronyms (e.g. LAP -> 'Loan Against Property', HL -> 'Home Loan', MH -> 'MAHARASHTRA') to exact database string values.

Schema:
{schema_text}

{val_dict_text}

Previous conversation:
{history}

Question: {question}

SQL Query:"""

    response, used_model = generate_content_with_fallback(prompt)
    sql = response.text.strip()

    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()

    return sql, used_model


def format_result_compact(result: List[Dict[str, Any]]) -> str:
    if not result:
        return "[]"
    headers = list(result[0].keys())
    lines = [" | ".join(headers)]
    for row in result:
        vals = [str(row.get(h, "")) for h in headers]
        lines.append(" | ".join(vals))
    return "\n".join(lines)


def interpret_result(question: str, result: List[Dict[str, Any]]) -> tuple[str, str]:
    total_rows = len(result)
    max_rows = settings.MAX_ROWS_FOR_LLM
    
    rows_to_format = result[:max_rows] if total_rows > max_rows else result
    result_str = format_result_compact(rows_to_format)
    
    if total_rows > max_rows:
        result_str += f"\n... [Showing first {max_rows} of {total_rows} total rows]"

    prompt = f"""You are a helpful business intelligence assistant. A user asked a question, and a database query was run to answer it. Given the user's original question and the raw query results (Total records returned: {total_rows}), write a clear, natural-language answer.

Do not mention raw SQL, database internal schemas, or technical jargon. Provide a concise, plain English answer as if you were a helpful data analyst.

Question: {question}
Raw results:
{result_str}

Answer:"""

    response, used_model = generate_content_with_fallback(prompt)
    return response.text.strip(), used_model


def correct_sql_query(question: str, broken_sql: str, error_message: str, history: str = "") -> tuple[str, str]:
    schema_text = get_db_schema()
    val_dict_text = build_categorical_value_dictionary()
    dialect_name, dialect_rules = get_dialect_rules()

    prompt = f"""You are an expert SQL query debugger for {dialect_name} databases.
The previous SQL query generated to answer a user question resulted in a database execution error.
Analyze the database error message and the schema, and output ONLY a corrected, executable SQL query.
Do not include markdown code block formatting (e.g. ```sql), explanations, or anything other than the raw executable SQL query.

Rules:
- {dialect_rules}
- Use column names strictly as defined in the Schema below.
- Check the Categorical Value Reference to map acronyms (e.g. LAP -> 'Loan Against Property', HL -> 'Home Loan', MH -> 'MAHARASHTRA') to exact database string values.
- Correct the syntax or schema reference error identified in the Error Traceback.

Schema:
{schema_text}

{val_dict_text}

Question: {question}

Broken SQL Query:
{broken_sql}

Database Error Traceback:
{error_message}

Corrected Executable SQL Query:"""

    response, used_model = generate_content_with_fallback(prompt)
    sql = response.text.strip()

    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()

    return sql, used_model



