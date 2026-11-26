"""
Automated CSV/Excel Dataset Ingestion Utility

Scans a directory of CSV and Excel files, infers database table names and column data types,
and automatically ingests them into the connected database (SQLite or MySQL).

Usage:
    python scripts/auto_ingest.py [--data-dir data]
"""

import sys
import os
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.auto_ingest import run_auto_ingest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Dataset Ingestion Utility for Text-to-SQL Chatbot.")
    parser.add_argument("--data-dir", type=str, default=os.path.join(PROJECT_ROOT, "data"), help="Path to directory containing CSV/Excel files (default: data/)")
    args = parser.parse_args()

    run_auto_ingest(args.data_dir)

