#!/usr/bin/env python3
"""
Standalone Column Data Profiler & Semantic Type Inference CLI Tool.

Reads Excel (.xlsx, .xls), CSV (.csv), TSV (.tsv), and JSON files,
infers accurate column data types (dates, currencies, IDs, enums, numbers, flags),
profiles statistics, and exports LLM-ready schema dictionaries, Markdown prompts,
SQL DDL, or SQLite tables.

Usage Examples:
    # 1. Print summary table in terminal
    python data_profiler.py --file text_to_sql_chatbot/data/sample.csv

    # 2. Generate LLM Prompt Markdown schema
    python data_profiler.py --file text_to_sql_chatbot/data/sample.xlsx --format markdown

    # 3. Export JSON schema dictionary to file
    python data_profiler.py --file text_to_sql_chatbot/data/sample.csv --to-json schema_dict.json

    # 4. Generate clean SQL CREATE TABLE DDL
    python data_profiler.py --file text_to_sql_chatbot/data/sample.csv --format ddl

    # 5. Ingest file into SQLite database with properly typed columns
    python data_profiler.py --file text_to_sql_chatbot/data/sample.csv --to-sqlite app.db --table-name loans
"""

import os
import sys
import argparse
import json
import sqlite3
from typing import Optional, List, Dict, Any
from pathlib import Path

# Ensure UTF-8 output stream on Windows consoles
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add directories to sys.path
current_dir = Path(__file__).resolve().parent
sub_dir = current_dir / "text_to_sql_chatbot"
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))
if str(sub_dir) not in sys.path:
    sys.path.insert(0, str(sub_dir))

try:
    from app.core.data_profiler import DatasetProfiler, TableProfile, clean_identifier
except ImportError:
    from text_to_sql_chatbot.app.core.data_profiler import DatasetProfiler, TableProfile, clean_identifier

import pandas as pd


def export_to_sqlite(file_path: str, db_path: str, table_name: Optional[str] = None, sheet_name: Optional[str] = None):
    """
    Ingests the file data into a SQLite database with cleaned column names
    and inferred SQL schemas.
    """
    profiler = DatasetProfiler()
    profiles = profiler.profile_file(file_path, sheet_name=sheet_name)
    
    conn = sqlite3.connect(db_path)
    
    for prof in profiles:
        target_tname = table_name or prof.clean_table_name
        print(f"📦 Ingesting table '{target_tname}' into SQLite database '{db_path}'...")
        
        # Read the full dataset
        if file_path.endswith((".xlsx", ".xls", ".xlsm")):
            df = pd.read_excel(file_path, sheet_name=prof.sheet_name)
        else:
            df = profiler._read_csv_robust(file_path)
            
        # Rename columns to clean SQL names
        clean_col_map = {col.name: col.clean_name for col in prof.columns}
        df = df.rename(columns=clean_col_map)
        
        # Write to SQLite
        df.to_sql(target_tname, conn, if_exists="replace", index=False)
        print(f"✅ Successfully written {len(df):,} rows into '{target_tname}' in {db_path}!")
        
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Tabular Dataset Profiler & Semantic Column Type Inference Tool for LLM Text-to-SQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python data_profiler.py --file data/report.xlsx
  python data_profiler.py --file data/report.csv --format markdown
  python data_profiler.py --file data/report.csv --to-json schema.json
  python data_profiler.py --file data/report.xlsx --to-sqlite app.db
        """
    )
    parser.add_argument("--file", "-f", required=True, help="Path to CSV, Excel (.xlsx/.xls), TSV, or JSON file")
    parser.add_argument("--sheet", "-s", default=None, help="Specific sheet name to profile (for Excel files)")
    parser.add_argument("--format", choices=["table", "markdown", "json", "ddl"], default="table",
                        help="Output format to display (default: table)")
    parser.add_argument("--sample-size", "-n", type=int, default=None,
                        help="Number of rows to sample for profiling (default: analyze all rows)")
    parser.add_argument("--to-json", type=str, default=None, help="Save schema data dictionary to a JSON file")
    parser.add_argument("--to-markdown", type=str, default=None, help="Save LLM Markdown schema context to a file")
    parser.add_argument("--to-ddl", type=str, default=None, help="Save SQL CREATE TABLE DDL statements to a file")
    parser.add_argument("--to-sqlite", type=str, default=None, help="Ingest dataset into specified SQLite database file")
    parser.add_argument("--table-name", type=str, default=None, help="Target table name when exporting to SQLite")

    args = parser.parse_args()

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ Error: File not found at '{file_path}'", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Profiling dataset: {file_path}")
    profiler = DatasetProfiler(sample_size=args.sample_size)
    try:
        profiles = profiler.profile_file(file_path, sheet_name=args.sheet)
    except Exception as e:
        print(f"❌ Error during profiling: {e}", file=sys.stderr)
        sys.exit(1)

    # Ingest to SQLite if requested
    if args.to_sqlite:
        export_to_sqlite(file_path, args.to_sqlite, table_name=args.table_name, sheet_name=args.sheet)

    # Save to JSON file if requested
    if args.to_json:
        out_data = [p.to_dict() for p in profiles]
        with open(args.to_json, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)
        print(f"💾 JSON Schema Dictionary saved to: {args.to_json}")

    # Save to Markdown file if requested
    if args.to_markdown:
        md_text = "\n\n---\n\n".join([profiler.to_llm_markdown(p) for p in profiles])
        with open(args.to_markdown, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"💾 LLM Markdown Schema saved to: {args.to_markdown}")

    # Save to DDL file if requested
    if args.to_ddl:
        ddl_text = "\n\n".join([profiler.to_sql_ddl(p) for p in profiles])
        with open(args.to_ddl, "w", encoding="utf-8") as f:
            f.write(ddl_text)
        print(f"💾 SQL DDL Statements saved to: {args.to_ddl}")

    # Display requested format to stdout
    print()
    for p in profiles:
        if args.format == "table":
            print(profiler.to_summary_table(p))
            print()
        elif args.format == "markdown":
            print(profiler.to_llm_markdown(p))
            print("\n" + "=" * 80 + "\n")
        elif args.format == "json":
            print(json.dumps(p.to_dict(), indent=2))
        elif args.format == "ddl":
            print(profiler.to_sql_ddl(p))
            print("\n")


if __name__ == "__main__":
    main()
