"""
Automated Dataset Ingestion Core Module with Incremental SHA-256 Hash Caching

Scans a data directory for CSV and Excel (.xlsx/.xls) files, infers database table names
and column data types, and automatically ingests them into the connected database (SQLite or MySQL).
Uses SHA-256 file hashing to skip re-ingestion if dataset files are unchanged.
"""

import os
import sys
import re
import hashlib
import pandas as pd
from datetime import datetime
from sqlalchemy import text, inspect
from sqlalchemy.types import Date, DateTime

from app.config import settings
from app.core.database import engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
IGNORED_TABLES = {"chats", "messages", "_ingestion_metadata"}
IGNORED_FILES = {"text_to_sql_test_cases.csv", "schema.sql", "schema_mysql.sql"}


def compute_file_hash(file_path: str) -> str:
    """Computes SHA-256 hash of a file for incremental change detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


TABLE_NAME_OVERRIDES = {
    "dynamic_collection_done_mis_report_1": "collection_data_v2",
    "dynamic_collection_done_mis_report": "collection_data_v2",
    "soa_master_export_report_28_jul_2026_2": "soa_data_v2",
    "soa_master_export_report_28_jul_2026": "soa_data_v2",
}


def sanitize_identifier(name: str) -> str:
    """
    Sanitizes filenames or column names into clean SQL identifiers.
    Example: 'SOA Master Export Report-28-Jul-2026 (2)' -> 'soa_master_export_report_28_jul_2026_2'
    """
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', name.strip())
    clean = re.sub(r'_+', '_', clean).strip('_').lower()
    return clean if clean else "table_data"


def get_table_name_for_file(raw_file_name: str) -> str:
    clean = sanitize_identifier(raw_file_name)
    return TABLE_NAME_OVERRIDES.get(clean, clean)


def disable_foreign_keys(conn):
    dialect = engine.dialect.name
    if dialect == "sqlite":
        conn.execute(text("PRAGMA foreign_keys = OFF;"))
    elif dialect == "mysql":
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
    elif dialect == "postgresql":
        conn.execute(text("SET session_replication_role = 'replica';"))


def enable_foreign_keys(conn):
    dialect = engine.dialect.name
    if dialect == "sqlite":
        conn.execute(text("PRAGMA foreign_keys = ON;"))
    elif dialect == "mysql":
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
    elif dialect == "postgresql":
        conn.execute(text("SET session_replication_role = 'origin';"))


def init_metadata_table(conn):
    """Creates internal ingestion tracking table if it doesn't exist."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _ingestion_metadata (
                file_name VARCHAR(255) PRIMARY KEY,
                file_hash VARCHAR(64) NOT NULL,
                table_name VARCHAR(255) NOT NULL,
                row_count BIGINT NOT NULL,
                ingested_at VARCHAR(50) NOT NULL
            );
        """))
    else:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS `_ingestion_metadata` (
                file_name VARCHAR(255) PRIMARY KEY,
                file_hash VARCHAR(64) NOT NULL,
                table_name VARCHAR(255) NOT NULL,
                row_count BIGINT NOT NULL,
                ingested_at VARCHAR(50) NOT NULL
            );
        """))


def get_cached_metadata(conn) -> dict[str, str]:
    """Returns a dictionary mapping file_name -> file_hash from DB cache."""
    try:
        init_metadata_table(conn)
        res = conn.execute(text("SELECT file_name, file_hash FROM _ingestion_metadata;")).fetchall()
        return {r[0]: r[1] for r in res}
    except Exception:
        return {}


def update_cached_metadata(file_name: str, file_hash: str, table_name: str, row_count: int, conn):
    """Updates ingestion cache record for a file."""
    now_str = datetime.utcnow().isoformat()
    dialect = engine.dialect.name
    if dialect in ["sqlite", "postgresql"]:
        conn.execute(text("""
            INSERT INTO _ingestion_metadata (file_name, file_hash, table_name, row_count, ingested_at)
            VALUES (:file_name, :file_hash, :table_name, :row_count, :ingested_at)
            ON CONFLICT(file_name) DO UPDATE SET
                file_hash=EXCLUDED.file_hash,
                table_name=EXCLUDED.table_name,
                row_count=EXCLUDED.row_count,
                ingested_at=EXCLUDED.ingested_at;
        """), {"file_name": file_name, "file_hash": file_hash, "table_name": table_name, "row_count": row_count, "ingested_at": now_str})
    else:
        conn.execute(text("""
            INSERT INTO `_ingestion_metadata` (file_name, file_hash, table_name, row_count, ingested_at)
            VALUES (:file_name, :file_hash, :table_name, :row_count, :ingested_at)
            ON DUPLICATE KEY UPDATE
                file_hash=VALUES(file_hash),
                table_name=VALUES(table_name),
                row_count=VALUES(row_count),
                ingested_at=VALUES(ingested_at);
        """), {"file_name": file_name, "file_hash": file_hash, "table_name": table_name, "row_count": row_count, "ingested_at": now_str})



def drop_existing_tables(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    tables_to_drop = [t for t in tables if t.lower() not in IGNORED_TABLES]

    if not tables_to_drop:
        return

    dialect = engine.dialect.name
    for t in tables_to_drop:
        if dialect == "postgresql":
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}" CASCADE;'))
        elif dialect == "mysql":
            conn.execute(text(f"DROP TABLE IF EXISTS `{t}`;"))
        else:
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}";'))


def get_existing_user_tables() -> list[str]:
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return [t for t in tables if t.lower() not in IGNORED_TABLES]
    except Exception:
        return []


def infer_and_ingest_file(file_path: str, raw_table_name: str, conn=None) -> tuple[int, str]:
    """
    Reads a CSV or Excel file, infers data types, converts date columns to actual datetimes,
    and loads records into the database table with native SQL DATE types.
    """
    table_name = get_table_name_for_file(raw_table_name)
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(file_path, low_memory=False)
    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
    else:
        return 0, table_name

    # Sanitize column names for SQL safety
    df.columns = [sanitize_identifier(str(c)) for c in df.columns]

    dtype_map = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'date' in col_lower:
            try:
                df[col] = pd.to_datetime(df[col], format='mixed', errors='coerce')
                dtype_map[col] = Date()
            except Exception:
                pass
        elif 'time' in col_lower:
            try:
                df[col] = pd.to_datetime(df[col], format='mixed', errors='coerce')
                dtype_map[col] = DateTime()
            except Exception:
                pass

    # Load into SQL database table using active transaction connection
    db_conn = conn if conn is not None else engine
    df.to_sql(
        name=table_name,
        con=db_conn,
        if_exists="replace",
        index=False,
        chunksize=2000,
        dtype=dtype_map
    )
    return len(df), table_name



def run_auto_ingest(data_dir: str = None) -> list[str]:
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    abs_data_dir = os.path.abspath(data_dir)
    if not os.path.exists(abs_data_dir):
        print(f"Directory '{abs_data_dir}' does not exist.")
        return []

    all_files = os.listdir(abs_data_dir)
    dataset_files = [
        f for f in all_files
        if f.lower().endswith((".csv", ".xlsx", ".xls")) and f.lower() not in IGNORED_FILES
    ]

    if not dataset_files:
        print(f"No dataset CSV/Excel files found in '{abs_data_dir}'.")
        return []

    print(f"[AutoIngest] Ingesting {len(dataset_files)} dataset file(s) from '{abs_data_dir}'...")

    total_rows = 0
    tables_created = []

    with engine.begin() as conn:
        init_metadata_table(conn)
        disable_foreign_keys(conn)
        drop_existing_tables(conn)
        try:
            for file_name in sorted(dataset_files):
                file_path = os.path.join(abs_data_dir, file_name)
                file_hash = compute_file_hash(file_path)
                raw_table_name = os.path.splitext(file_name)[0]
                rows, clean_name = infer_and_ingest_file(file_path, raw_table_name, conn)
                update_cached_metadata(file_name, file_hash, clean_name, rows, conn)
                total_rows += rows
                tables_created.append(clean_name)
                print(f"  -> Ingested '{file_name}' into table '{clean_name}' ({rows} rows)")
        finally:
            enable_foreign_keys(conn)

    print(f"[AutoIngest] Successfully ingested {len(tables_created)} table(s) ({total_rows} total rows).")
    return tables_created


def auto_ingest_if_needed(data_dir: str = None) -> list[str]:
    """
    Checks if user data tables corresponding to dataset files exist and SHA-256 hashes match cache.
    If hashes match and dataset tables exist, skips re-ingestion for instant startup (<20ms).
    Otherwise triggers dataset ingestion.
    """
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    abs_data_dir = os.path.abspath(data_dir)
    if not os.path.exists(abs_data_dir):
        return get_existing_user_tables()

    all_files = os.listdir(abs_data_dir)
    dataset_files = [
        f for f in all_files
        if f.lower().endswith((".csv", ".xlsx", ".xls")) and f.lower() not in IGNORED_FILES
    ]

    expected_table_names = [get_table_name_for_file(os.path.splitext(f)[0]) for f in dataset_files]
    existing_tables = get_existing_user_tables()


    with engine.begin() as conn:
        init_metadata_table(conn)
        cached_hashes = get_cached_metadata(conn)

    tables_exist = all(t in existing_tables for t in expected_table_names) if expected_table_names else False

    if tables_exist:
        need_reingest = False
        with engine.begin() as conn:
            dialect = engine.dialect.name
            q = "`" if dialect == "mysql" else '"'
            for f in dataset_files:
                tbl = get_table_name_for_file(os.path.splitext(f)[0])
                try:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {q}{tbl}{q}")).scalar()
                except Exception:
                    count = 0

                if count == 0:
                    print(f"[AutoIngest] Table '{tbl}' is empty (0 rows). Triggering dataset ingestion...")
                    need_reingest = True
                    break

                file_path = os.path.join(abs_data_dir, f)
                current_hash = compute_file_hash(file_path)
                cached = cached_hashes.get(f)
                if cached is None:
                    update_cached_metadata(f, current_hash, tbl, count, conn)
                elif cached != current_hash:
                    need_reingest = True
                    break
        if not need_reingest:
            return existing_tables

    print("[AutoIngest] Missing dataset tables or file modification detected. Triggering ingestion...")
    return run_auto_ingest(data_dir)

