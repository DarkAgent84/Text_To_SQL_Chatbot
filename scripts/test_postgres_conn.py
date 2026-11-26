"""
PostgreSQL Connection & Schema Setup Utility

Verifies connection to PostgreSQL, creates target database if missing,
and applies the PostgreSQL schema from data/schema_postgres.sql.
"""

import sys
import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.config import settings

def test_and_setup_postgres():
    user = settings.POSTGRES_USER or "postgres"
    password = settings.POSTGRES_PASSWORD or ""
    host = settings.POSTGRES_HOST or "localhost"
    port = settings.POSTGRES_PORT or "5432"
    target_db = settings.POSTGRES_DB or "text_to_sql_db"

    print(f"Connecting to PostgreSQL server at {host}:{port} as user '{user}'...")

    try:
        # Step 1: Connect to default 'postgres' database
        conn = psycopg2.connect(
            dbname="postgres",
            user=user,
            password=password,
            host=host,
            port=port,
            connect_timeout=5
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        print("  ✓ Connected successfully to PostgreSQL server!")

        # Step 2: Check if target database exists, create if missing
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db,))
        exists = cursor.fetchone()
        if not exists:
            print(f"  -> Database '{target_db}' does not exist. Creating...")
            cursor.execute(f'CREATE DATABASE "{target_db}";')
            print(f"  ✓ Database '{target_db}' created successfully.")
        else:
            print(f"  ✓ Target database '{target_db}' already exists.")

        cursor.close()
        conn.close()

        # Step 3: Connect to target database
        conn = psycopg2.connect(
            dbname=target_db,
            user=user,
            password=password,
            host=host,
            port=port
        )
        cursor = conn.cursor()

        # Step 4: Apply schema_postgres.sql if available
        schema_file = os.path.join(PROJECT_ROOT, "data", "schema_postgres.sql")
        if os.path.exists(schema_file):
            print(f"  -> Applying PostgreSQL schema from '{schema_file}'...")
            with open(schema_file, "r", encoding="utf-8") as f:
                sql_script = f.read()
            cursor.execute(sql_script)
            conn.commit()
            print("  ✓ PostgreSQL tables (collection_data_v2, soa_data_v2) and indexes applied successfully.")

        cursor.close()
        conn.close()
        print(f"\n[PostgreSQL Setup Complete] Database '{target_db}' is ready for the Text-to-SQL Chatbot!")
        return True

    except psycopg2.OperationalError as e:
        err_msg = str(e).strip()
        print(f"\n[PostgreSQL Connection Error] {err_msg}")
        if "password authentication failed" in err_msg:
            print("\n  -> FIX: Update POSTGRES_PASSWORD in your .env file with your pgAdmin/PostgreSQL password.")
        elif "could not connect to server" in err_msg:
            print("\n  -> FIX: Ensure PostgreSQL service is running on your system.")
        return False
    except Exception as e:
        print(f"\n[Error] {e}")
        return False

if __name__ == "__main__":
    test_and_setup_postgres()
