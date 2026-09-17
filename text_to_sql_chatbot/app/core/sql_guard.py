"""
Production SQL Security Guard and AST Safety Validator.
"""

import re
from typing import Tuple, Optional

# Disallowed modification statements and injection vectors
BLOCKED_KEYWORDS = [
    r"\b(insert\s+into)\b",
    r"\b(update\s+[\w`\"\[\]]+\s+set)\b",
    r"\b(delete\s+from)\b",
    r"\b(drop\s+(table|database|index|view|schema|trigger|procedure|function))\b",
    r"\b(alter\s+(table|database|schema|user|role))\b",
    r"\b(truncate\s+table?)\b",
    r"\b(create\s+(table|database|index|view|trigger|procedure|function|user|schema))\b",
    r"\b(grant|revoke)\b",
    r"\b(execute|exec|eval)\b",
    r"\b(call\s+\w+)\b",
    r"\b(copy\s+[\w`\"\[\]]+\s+(to|from))\b",
    r"\b(into\s+(outfile|dumpfile))\b",
    r"\b(load_file|pg_read_file|pg_write_file|xp_cmdshell)\b",
    r"\b(shutdown)\b",
]

# Chained statement detector
SEMICOLON_CHAIN_REGEX = re.compile(r";\s*[a-zA-Z0-9_]+")


def strip_sql_comments(sql: str) -> str:
    """Removes single-line (--) and multi-line (/* */) comments to prevent comment injection."""
    # Remove /* ... */ comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Remove -- comments
    sql = re.sub(r"--.*$", " ", sql, flags=re.MULTILINE)
    # Normalize multiple whitespaces
    sql = re.sub(r"\s+", " ", sql).strip()
    return sql


def validate_sql_safety(sql_query: str) -> Tuple[bool, Optional[str]]:
    """
    Strict validation ensuring the query is strictly read-only (SELECT / WITH ... SELECT).
    Returns (is_safe: bool, reason: Optional[str]).
    """
    if not sql_query or not isinstance(sql_query, str):
        return False, "SQL query is empty or invalid."

    clean_sql = strip_sql_comments(sql_query).strip()
    if not clean_sql:
        return False, "Query is empty after comment removal."

    # Prevent stacked queries (e.g. SELECT 1; DROP TABLE users;)
    # Remove trailing semicolon if present
    sql_without_trailing_semi = re.sub(r";\s*$", "", clean_sql)
    if SEMICOLON_CHAIN_REGEX.search(sql_without_trailing_semi):
        return False, "Multi-statement execution (chained queries with ';') is strictly disallowed."

    # Validate starting command (Must start with SELECT, WITH, or EXPLAIN)
    clean_lower = sql_without_trailing_semi.lower().strip()
    if not (clean_lower.startswith("select") or clean_lower.startswith("with") or clean_lower.startswith("explain")):
        return False, "Only read-only SELECT or WITH (CTE) queries are permitted."

    # Verify no blocked modification keywords exist anywhere in the query
    for pattern in BLOCKED_KEYWORDS:
        match = re.search(pattern, clean_lower, re.IGNORECASE)
        if match:
            blocked_term = match.group(0)
            return False, f"Potentially destructive SQL command detected: '{blocked_term}' is forbidden."

    return True, None


def is_safe_query(sql_query: str) -> bool:
    """Convenience boolean helper for legacy callers."""
    safe, _ = validate_sql_safety(sql_query)
    return safe
