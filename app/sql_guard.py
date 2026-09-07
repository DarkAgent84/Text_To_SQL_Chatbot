import re

DANGEROUS_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "REPLACE"]

def is_safe_query(sql: str) -> bool:
    normalized = sql.strip().rstrip(";").strip().upper()

    if ";" in normalized:
        return False

    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False

    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            return False

    return True