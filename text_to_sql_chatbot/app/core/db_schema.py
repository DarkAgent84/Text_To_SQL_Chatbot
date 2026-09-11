from typing import Dict, List, Optional
from sqlalchemy import inspect, text
from app.core.database import get_target_engine

# Schema Cache indexed by engine connection URL
_SCHEMA_CACHE: Dict[str, str] = {}
_IGNORED_TABLES = {"chats", "messages", "saved_connections", "sqlite_sequence", "_ingestion_metadata"}


def invalidate_schema_cache():
    """Clears the schema cache when the database connection changes."""
    global _SCHEMA_CACHE
    _SCHEMA_CACHE.clear()


def get_db_schema(force_refresh: bool = False) -> str:
    """
    Dynamically extracts the exact schema from the active target database engine.
    Reflects:
      - All user tables
      - Exact column names & SQL data types (e.g., VARCHAR(100), DECIMAL(10,2), INTEGER, TIMESTAMP)
      - Primary Key constraints (PK)
      - Foreign Key constraints (FK)
      - Sample categorical distinct values for string/enum columns
    """
    global _SCHEMA_CACHE
    current_engine = get_target_engine()
    engine_key = str(current_engine.url)

    if not force_refresh and engine_key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[engine_key]

    try:
        inspector = inspect(current_engine)
        table_names = inspector.get_table_names()
        user_tables = [t for t in table_names if t.lower() not in _IGNORED_TABLES]

        if not user_tables:
            return "-- No user tables found in the connected database."

        table_schemas = []
        dialect = current_engine.dialect.name.lower()
        quote_char = "`" if dialect == "mysql" else '"'

        with current_engine.connect() as conn:
            for table in user_tables:
                columns = inspector.get_columns(table)
                pk_constraint = inspector.get_pk_constraint(table)
                pk_cols = set(pk_constraint.get("constrained_columns", []))
                fk_constraints = inspector.get_foreign_keys(table)

                col_defs = []
                for col in columns:
                    col_name = col["name"]
                    # Exact SQL DataType assigned to the column
                    col_type = str(col["type"]).upper()
                    
                    parts = [f"{col_name} {col_type}"]
                    if col_name in pk_cols:
                        parts.append("PRIMARY KEY")
                    elif not col.get("nullable", True):
                        parts.append("NOT NULL")

                    # Extract sample values for categorical / string columns to assist LLM with accurate literal filtering
                    if any(c in col_type for c in ["CHAR", "TEXT", "ENUM", "STRING"]) or any(
                        k in col_name.lower() for k in ["status", "type", "category", "city", "state", "segment", "mode", "role", "bucket"]
                    ):
                        try:
                            sample_sql = f"SELECT DISTINCT {quote_char}{col_name}{quote_char} FROM (SELECT {quote_char}{col_name}{quote_char} FROM {quote_char}{table}{quote_char} WHERE {quote_char}{col_name}{quote_char} IS NOT NULL LIMIT 100) sub LIMIT 3"
                            rows = conn.execute(text(sample_sql)).fetchall()
                            samples = [str(r[0]) for r in rows if r[0] is not None and str(r[0]).strip()]
                            if samples:
                                parts.append(f"[samples: {', '.join(samples[:3])}]")
                        except Exception:
                            pass

                    col_defs.append("  " + " ".join(parts))

                # Append Foreign Key constraints
                for fk in fk_constraints:
                    referred_table = fk.get("referred_table")
                    constrained_cols = fk.get("constrained_columns", [])
                    referred_cols = fk.get("referred_columns", [])
                    if constrained_cols and referred_cols and referred_table:
                        c_col = ", ".join(constrained_cols)
                        r_col = ", ".join(referred_cols)
                        col_defs.append(f"  FOREIGN KEY ({c_col}) REFERENCES {referred_table}({r_col})")

                table_str = f"CREATE TABLE {table} (\n" + ",\n".join(col_defs) + "\n);"
                table_schemas.append(table_str)

        full_schema_text = "\n\n".join(table_schemas)
        _SCHEMA_CACHE[engine_key] = full_schema_text
        return full_schema_text

    except Exception as e:
        err_msg = f"-- Dynamic schema extraction warning: {str(e)}"
        print(err_msg)
        return err_msg
