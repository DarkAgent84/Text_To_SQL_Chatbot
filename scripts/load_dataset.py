"""
Loads the full 10-table dataset into app.db.
Can be executed from anywhere: python scripts/load_dataset.py
"""

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(PROJECT_ROOT, "app.db")
SCHEMA_FILE = os.path.join(DATA_DIR, "schema.sql")

# Order matters: parent tables before child tables, so foreign keys don't fail
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

def load_data():
    if not os.path.exists(DATA_DIR):
        print(f"Error: Data directory not found at {DATA_DIR}")
        return

    conn = sqlite3.connect(DB_PATH)

    # Step 1: build the schema (drops + recreates all 10 tables with real PK/FK constraints)
    with open(SCHEMA_FILE, "r") as f:
        conn.executescript(f.read())

    # Step 2: bulk load each CSV into its matching table
    for table in LOAD_ORDER:
        csv_path = os.path.join(DATA_DIR, f"{table}.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df.to_sql(table, conn, if_exists="append", index=False)
            print(f"Loaded {len(df)} rows into {table}")
        else:
            print(f"Warning: {csv_path} does not exist.")

    conn.commit()
    conn.close()
    print("Dataset successfully loaded into SQLite database.")

if __name__ == "__main__":
    load_data()
