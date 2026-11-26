import re

DANGEROUS_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]


def is_safe_query(sql: str) -> bool:
    """
    Validates whether an SQL query is read-only (SELECT / WITH) and contains no data-modifying commands.
    """
    normalized = sql.strip().rstrip(";").strip().upper()

    # Reject multi-statement queries
    if ";" in normalized:
        return False

    # Must start with SELECT or WITH (CTEs)
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False

    # Reject dangerous keywords
    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            return False

    return True
