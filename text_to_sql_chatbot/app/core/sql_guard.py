import re

# Blocklist of disallowed SQL statements and modification keywords
BLOCKED_PATTERNS = [
    r"\b(insert\s+into)\b",
    r"\b(update\s+\w+\s+set)\b",
    r"\b(delete\s+from)\b",
    r"\b(drop\s+(table|database|index|view|schema))\b",
    r"\b(alter\s+(table|database|schema))\b",
    r"\b(truncate\s+table)\b",
    r"\b(create\s+(table|database|index|view))\b",
    r"\b(grant|revoke)\b",
    r"\b(execute|exec)\b",
    r";\s*\w+",  # Prevent chained multi-statement queries
]


def is_safe_query(sql_query: str) -> bool:
    """
    Validates whether an SQL query is strictly read-only.
    Permits SELECT and Common Table Expressions (WITH ... SELECT).
    """
    if not sql_query or not isinstance(sql_query, str):
        return False

    clean_sql = sql_query.strip().lower()

    # Must start with SELECT, WITH, or EXPLAIN
    if not (clean_sql.startswith("select") or clean_sql.startswith("with") or clean_sql.startswith("explain")):
        return False

    # Check against blocklist patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, clean_sql, re.IGNORECASE):
            return False

    return True
