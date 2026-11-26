"""
Loads the full 10-table dataset into MySQL database.
Can be executed from anywhere: python scripts/load_dataset_mysql.py
"""

import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DB = os.getenv("MYSQL_DB", "text_to_sql_db")

def load_data_mysql():
    root_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}"
    try:
        temp_engine = create_engine(root_url)
        with temp_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB}"))
        print(f"Database '{MYSQL_DB}' checked/created successfully.")
    except Exception as e:
        print(f"Could not connect to MySQL server: {e}")
        print("Please verify your MySQL server is running and check your MYSQL_PASSWORD.")
        return

    DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    engine = create_engine(DATABASE_URL)

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
    SCHEMA_FILE = os.path.join(DATA_DIR, "schema_mysql.sql")

    LOAD_ORDER = [
        "customers",
        "suppliers",
        "categories",
        "employees",
        "products",
        "orders",
        "order_items",
        "payments",
        "shipments",
        "reviews",
    ]

    with open(SCHEMA_FILE, "r") as f:
        sql_statements = f.read().split(";")
        with engine.connect() as conn:
            for stmt in sql_statements:
                if stmt.strip():
                    conn.execute(text(stmt))

    print("MySQL tables created successfully.")

    for table in LOAD_ORDER:
        csv_path = os.path.join(DATA_DIR, f"{table}.csv")
        df = pd.read_csv(csv_path)
        df.to_sql(table, engine, if_exists="append", index=False)
        print(f"Loaded {len(df)} rows into {table}")

    print("All 10 tables loaded into MySQL successfully!")

if __name__ == "__main__":
    load_data_mysql()
