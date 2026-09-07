"""
Loads the full 10-table dataset into app.db.
Can be executed from anywhere: python TextToSQL_Datasets/load_dataset.py
"""

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

DB_PATH = os.path.join(PROJECT_ROOT, "app.db")
SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")

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

conn = sqlite3.connect(DB_PATH)

# Step 1: build the schema (drops + recreates all 10 tables with real PK/FK constraints)
with open(SCHEMA_FILE, "r") as f:
    conn.executescript(f.read())

# Step 2: bulk load each CSV into its matching table
for table in LOAD_ORDER:
    csv_path = os.path.join(BASE_DIR, f"{table}.csv")
    df = pd.read_csv(csv_path)
    df.to_sql(table, conn, if_exists="append", index=False)
    print(f"Loaded {len(df)} rows into {table}")

conn.commit()
conn.close()
print("Done.")

