"""
Categorical Value Dictionary & Synonym Mapping Module

Prevents value mismatch hallucinations by:
1. Mapping common acronyms/abbreviations (LAP, HL, PL, etc.) to exact DB categorical string values.
2. Extracting distinct categorical values from connected database tables (soa_data_v2, collection_data_v2).
3. Formatting exact categorical value hints for Gemini LLM prompt context.
"""

from typing import Dict, List, Any
from sqlalchemy import text, inspect
from app.core.database import engine
from app.core.auto_ingest import IGNORED_TABLES

# Standard Domain Acronym & Synonym Mappings
SYNONYM_DICTIONARY: Dict[str, str] = {
    "lap": "Loan Against Property",
    "hl": "Home Loan",
    "pl": "Personal Loan",
    "bl": "Business Loan",
    "tw": "Two Wheeler",
    "al": "Auto Loan",
    "cl": "Commercial Loan",
    "mh": "MAHARASHTRA",
    "gj": "GUJARAT",
    "ka": "KARNATAKA",
    "dl": "DELHI",
    "tn": "TAMIL NADU",
    "up": "UTTAR PRADESH",
    "mp": "MADHYA PRADESH",
    "rj": "RAJASTHAN",
    "wb": "WEST BENGAL",
}

_VALUE_DICT_CACHE: Dict[str, str] = {}


def build_categorical_value_dictionary(force_refresh: bool = False) -> str:
    """
    Scans categorical columns across user database tables and builds a concise
    representation of exact column values and domain synonyms to prevent LLM value mismatch hallucinations.
    """
    global _VALUE_DICT_CACHE
    engine_key = str(engine.url)
    if not force_refresh and engine_key in _VALUE_DICT_CACHE:
        return _VALUE_DICT_CACHE[engine_key]

    try:
        inspector = inspect(engine)
        tables = [t for t in inspector.get_table_names() if t.lower() not in IGNORED_TABLES]
        if not tables:
            return ""

        dialect = engine.dialect.name
        q = "`" if dialect == "mysql" else '"'

        dict_lines = [
            "Categorical Value Reference & Business Acronym Dictionary:",
            "- Product Acronyms: LAP -> 'Loan Against Property', HL -> 'Home Loan', PL -> 'Personal Loan', BL -> 'Business Loan'",
            "- State Acronyms: MH -> 'MAHARASHTRA', GJ -> 'GUJARAT', KA -> 'KARNATAKA', DL -> 'DELHI', UP -> 'UTTAR PRADESH'"
        ]

        target_keywords = ["product", "bucket", "status", "mode", "legal", "business", "type", "risk", "state"]

        with engine.connect() as conn:
            for table in tables:
                columns = inspector.get_columns(table)
                table_val_hints = []
                for col in columns:
                    col_name = col["name"]
                    if any(kw in col_name.lower() for kw in target_keywords):
                        try:
                            sample_query = f"SELECT DISTINCT {q}{col_name}{q} FROM (SELECT {q}{col_name}{q} FROM {q}{table}{q} WHERE {q}{col_name}{q} IS NOT NULL LIMIT 100) sub LIMIT 5"
                            res = conn.execute(text(sample_query)).fetchall()
                            vals = [str(r[0]).strip() for r in res if r[0] is not None and str(r[0]).strip() != ""]
                            if vals:
                                table_val_hints.append(f"  * {col_name}: [{', '.join(vals[:5])}]")
                        except Exception:
                            pass

                if table_val_hints:
                    dict_lines.append(f"- Table `{table}` Exact Column Values:")
                    dict_lines.extend(table_val_hints)

        result_str = "\n".join(dict_lines)
        _VALUE_DICT_CACHE[engine_key] = result_str
        return result_str
    except Exception as e:
        print(f"[ValueDictionary] Warning: Value dictionary build failed ({e})")
        return ""
