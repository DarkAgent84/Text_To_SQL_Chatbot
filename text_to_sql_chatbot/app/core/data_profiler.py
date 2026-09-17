"""
Dataset Profiler & Semantic Column Type Inference Engine.

Analyzes tabular data files (Excel, CSV, TSV, JSON) to understand column contents,
infer accurate data types, compute statistical profiles, and generate LLM-ready
data dictionaries and SQL DDL for precise Text-to-SQL generation.
"""

import os
import re
import math
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Data Classes
# ----------------------------------------------------------------------

@dataclass
class ColumnProfile:
    name: str
    clean_name: str
    inferred_type: str
    sql_type: str
    semantic_role: str
    total_rows: int
    non_null_count: int
    null_count: int
    null_percentage: float
    unique_count: int
    is_unique: bool
    sample_values: List[Any] = field(default_factory=list)
    distinct_values: Optional[List[str]] = None
    value_frequencies: Optional[Dict[str, int]] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    mean_value: Optional[float] = None
    median_value: Optional[float] = None
    date_format: Optional[str] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    llm_guidance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableProfile:
    table_name: str
    clean_table_name: str
    source_file: str
    sheet_name: Optional[str]
    total_rows: int
    total_columns: int
    columns: List[ColumnProfile] = field(default_factory=list)
    primary_key_candidates: List[str] = field(default_factory=list)
    date_columns: List[str] = field(default_factory=list)
    metric_columns: List[str] = field(default_factory=list)
    categorical_columns: List[str] = field(default_factory=list)
    identifier_columns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "clean_table_name": self.clean_table_name,
            "source_file": self.source_file,
            "sheet_name": self.sheet_name,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "primary_key_candidates": self.primary_key_candidates,
            "date_columns": self.date_columns,
            "metric_columns": self.metric_columns,
            "categorical_columns": self.categorical_columns,
            "identifier_columns": self.identifier_columns,
            "columns": [col.to_dict() for col in self.columns]
        }


# ----------------------------------------------------------------------
# Regex & Pattern Matchers
# ----------------------------------------------------------------------

# Common date patterns with format strings
DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY/MM/DD
    (re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"), "%Y-%m-%d"),
    # DD-MM-YYYY or DD/MM/YYYY
    (re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$"), "%d-%m-%Y"),
    # DD-Mon-YYYY (e.g. 28-Jul-2026)
    (re.compile(r"^\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}$"), "%d-%b-%Y"),
    # YYYY-MM-DD HH:MM:SS or DD-MM-YYYY HH:MM:SS
    (re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?$"), "%Y-%m-%d %H:%M:%S"),
    (re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}\s+\d{1,2}:\d{2}(:\d{2})?$"), "%d-%m-%Y %H:%M:%S"),
    # ISO 8601 with T
    (re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"), "ISO8601"),
]

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,5}[-.\s]?\d{4,5}$")
URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
PINCODE_REGEX = re.compile(r"^\d{5,6}$")
CURRENCY_PREFIX_REGEX = re.compile(r"^[\$€£₹]|(?:USD|INR|EUR|GBP|Rs\.?)\s*", re.IGNORECASE)
PERCENTAGE_REGEX = re.compile(r"^-?\d+(?:\.\d+)?%$")
TIME_REGEX = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?(\s*(?:AM|PM|am|pm))?$")

BOOLEAN_TRUE_VALUES = {"true", "1", "yes", "y", "t", "active", "enabled", "success"}
BOOLEAN_FALSE_VALUES = {"false", "0", "no", "n", "f", "inactive", "disabled", "failed"}
BOOLEAN_SET = BOOLEAN_TRUE_VALUES | BOOLEAN_FALSE_VALUES

IDENTIFIER_KEYWORDS = {
    "id", "no", "number", "num", "code", "key", "account", "acc", "ref", "reference",
    "uuid", "guid", "pin", "pincode", "pan", "aadhar", "ssn", "sr_no", "srno", "serial",
    "receipt", "txn", "transaction", "ifsc"
}

FINANCIAL_KEYWORDS = {
    "amount", "amt", "balance", "bal", "dues", "due", "charges", "charge", "fee", "penalty",
    "interest", "waiver", "incentive", "collected", "outstanding", "emi", "pemi", "salary",
    "price", "cost", "revenue", "profit", "loss", "fcl_amount"
}

METRIC_KEYWORDS = FINANCIAL_KEYWORDS | {
    "count", "cnt", "quantity", "qty", "total", "sum", "rate", "percent", "percentage",
    "pct", "score", "weight", "height", "tenure", "dpd", "rejection_count", "rejection count"
}

COORDINATE_KEYWORDS = {"latitude", "longitude", "lat", "lon", "lng"}

STATUS_KEYWORDS = {
    "status", "type", "category", "cat", "state", "zone", "region", "branch", "mode",
    "bucket", "group", "sub_group", "role", "language", "gender", "flag", "stage",
    "priority", "action", "tag", "npa"
}


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------

def clean_identifier(name: str) -> str:
    """Normalizes a column or table name to a clean, valid SQL identifier."""
    if not name or not str(name).strip():
        return "unnamed_column"
    
    clean = str(name).strip()
    # Replace slashes, dashes, dots, spaces with underscores
    clean = re.sub(r"[\s\-\./\(\)\[\]\{\}\\:\?\,\'\"\*\%\$\#\@\!]+", "_", clean)
    clean = re.sub(r"_+", "_", clean).strip("_").lower()
    
    # Prepend 'col_' if starts with a digit
    if clean and clean[0].isdigit():
        clean = f"col_{clean}"
    
    return clean or "unnamed_column"


def try_parse_numeric_string(val: str) -> Optional[Union[int, float]]:
    """Attempts to clean and parse a string into int or float (stripping commas, currency symbols, percentages)."""
    if not isinstance(val, str):
        return None
    
    v = val.strip()
    if not v or v.lower() in ("nan", "none", "null", "n/a", "-", "--", "nil", ""):
        return None
    
    # Strip currency symbols
    v = CURRENCY_PREFIX_REGEX.sub("", v).strip()
    
    # Check percentage
    is_pct = False
    if v.endswith("%"):
        is_pct = True
        v = v[:-1].strip()
    
    # Remove thousand commas
    v_clean = v.replace(",", "").replace(" ", "")
    
    # Handle parenthesized negative numbers e.g. (100.50)
    if v_clean.startswith("(") and v_clean.endswith(")"):
        v_clean = "-" + v_clean[1:-1]
        
    try:
        if "." in v_clean:
            num = float(v_clean)
            return (num / 100.0) if is_pct else num
        else:
            num = int(v_clean)
            return (num / 100.0) if is_pct else num
    except ValueError:
        return None


def detect_date_string(val: str) -> Optional[Tuple[str, str]]:
    """
    Checks if a string is a date or datetime.
    Returns (detected_format, parsed_iso_string) if valid, else None.
    """
    if not isinstance(val, str):
        return None
    
    v = val.strip()
    if not v or len(v) < 6 or len(v) > 35:
        return None
    
    for pattern, fmt_name in DATE_PATTERNS:
        if pattern.match(v):
            if fmt_name == "%d-%b-%Y":
                try:
                    dt = datetime.strptime(v, "%d-%b-%Y")
                    return ("DD-Mon-YYYY", dt.strftime("%Y-%m-%d"))
                except ValueError:
                    pass
            elif fmt_name == "%d-%m-%Y":
                # Disambiguate DD-MM-YYYY vs MM-DD-YYYY if needed
                parts = re.split(r"[-/]", v)
                if len(parts) >= 3:
                    try:
                        p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
                        dt = datetime(p3, p2, p1)
                        return ("DD-MM-YYYY", dt.strftime("%Y-%m-%d"))
                    except Exception:
                        pass
            elif fmt_name == "%Y-%m-%d":
                try:
                    parts = re.split(r"[-/]", v)
                    dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                    return ("YYYY-MM-DD", dt.strftime("%Y-%m-%d"))
                except Exception:
                    pass
            elif fmt_name in ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "ISO8601"):
                return ("DATETIME", v)
    
    return None


# ----------------------------------------------------------------------
# Core Profiler Class
# ----------------------------------------------------------------------

class DatasetProfiler:
    """
    Advanced tabular data profiler that reads Excel, CSV, TSV, JSON datasets,
    infers precise semantic column types, detects patterns, calculates statistical
    metrics, and produces LLM prompt context & SQL DDL.
    """

    def __init__(self, sample_size: Optional[int] = None, max_categories: int = 25):
        """
        Args:
            sample_size: Maximum rows to sample for deep profiling (None = analyze all rows).
            max_categories: Maximum discrete values to list for categorical columns.
        """
        self.sample_size = sample_size
        self.max_categories = max_categories

    def profile_file(self, file_path: str, sheet_name: Optional[Union[str, int]] = None) -> List[TableProfile]:
        """
        Profiles a data file. If Excel has multiple sheets and sheet_name is None,
        profiles all sheets in the workbook.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        profiles = []

        if ext in (".xlsx", ".xls", ".xlsm"):
            excel_file = pd.ExcelFile(file_path)
            sheets_to_process = [sheet_name] if sheet_name is not None else excel_file.sheet_names

            for sheet in sheets_to_process:
                logger.info(f"Loading sheet '{sheet}' from {path.name}...")
                df = pd.read_excel(excel_file, sheet_name=sheet, nrows=self.sample_size)
                clean_tname = clean_identifier(f"{path.stem}_{sheet}") if len(sheets_to_process) > 1 else clean_identifier(path.stem)
                profile = self.profile_dataframe(
                    df=df,
                    table_name=str(sheet),
                    clean_table_name=clean_tname,
                    source_file=str(path.resolve()),
                    sheet_name=str(sheet)
                )
                profiles.append(profile)

        elif ext in (".csv", ".tsv", ".txt"):
            delimiter = "\t" if ext == ".tsv" else None
            df = self._read_csv_robust(file_path, delimiter=delimiter, nrows=self.sample_size)
            clean_tname = clean_identifier(path.stem)
            profile = self.profile_dataframe(
                df=df,
                table_name=path.stem,
                clean_table_name=clean_tname,
                source_file=str(path.resolve()),
                sheet_name=None
            )
            profiles.append(profile)

        elif ext in (".json", ".jsonl"):
            lines = ext == ".jsonl"
            df = pd.read_json(file_path, lines=lines, nrows=self.sample_size)
            clean_tname = clean_identifier(path.stem)
            profile = self.profile_dataframe(
                df=df,
                table_name=path.stem,
                clean_table_name=clean_tname,
                source_file=str(path.resolve()),
                sheet_name=None
            )
            profiles.append(profile)

        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported formats: .xlsx, .xls, .csv, .tsv, .txt, .json, .jsonl")

        return profiles

    def _read_csv_robust(self, file_path: str, delimiter: Optional[str] = None, nrows: Optional[int] = None) -> pd.DataFrame:
        """Reads CSV with automatic encoding & delimiter detection."""
        encodings = ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1"]
        
        for enc in encodings:
            try:
                if delimiter:
                    return pd.read_csv(file_path, delimiter=delimiter, encoding=enc, nrows=nrows, low_memory=False)
                # Let pandas auto-detect engine='python' separator if needed
                try:
                    return pd.read_csv(file_path, encoding=enc, nrows=nrows, low_memory=False)
                except Exception:
                    return pd.read_csv(file_path, sep=None, engine="python", encoding=enc, nrows=nrows)
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                logger.warning(f"Failed reading with {enc}: {e}")
                continue

        # Last resort fallback
        return pd.read_csv(file_path, encoding="latin1", errors="replace", nrows=nrows, low_memory=False)

    def profile_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        clean_table_name: Optional[str] = None,
        source_file: str = "",
        sheet_name: Optional[str] = None
    ) -> TableProfile:
        """Profiles an in-memory pandas DataFrame and generates comprehensive column understanding."""
        total_rows = len(df)
        total_columns = len(df.columns)
        clean_tname = clean_table_name or clean_identifier(table_name)

        col_profiles: List[ColumnProfile] = []
        pk_candidates: List[str] = []
        date_cols: List[str] = []
        metric_cols: List[str] = []
        cat_cols: List[str] = []
        id_cols: List[str] = []

        # Deduplicate column names if duplicates exist
        seen_col_names = {}
        unique_columns = []
        for c in df.columns:
            c_str = str(c)
            if c_str in seen_col_names:
                seen_col_names[c_str] += 1
                unique_columns.append(f"{c_str}_{seen_col_names[c_str]}")
            else:
                seen_col_names[c_str] = 0
                unique_columns.append(c_str)
        df.columns = unique_columns

        for col_name in df.columns:
            series = df[col_name]
            col_prof = self._profile_column(series, col_name, total_rows)
            col_profiles.append(col_prof)

            # Categorize column into table-level groups
            if col_prof.semantic_role == "Primary Key / Identifier" or col_prof.is_unique:
                if col_prof.null_count == 0 and col_prof.is_unique:
                    pk_candidates.append(col_prof.name)
                id_cols.append(col_prof.name)
            elif col_prof.semantic_role == "Date / Time Dimension":
                date_cols.append(col_prof.name)
            elif col_prof.semantic_role == "Metric / Measure":
                metric_cols.append(col_prof.name)
            elif col_prof.semantic_role == "Categorical Dimension":
                cat_cols.append(col_prof.name)
            elif col_prof.semantic_role == "Identifier / Key":
                id_cols.append(col_prof.name)

        return TableProfile(
            table_name=table_name,
            clean_table_name=clean_tname,
            source_file=source_file,
            sheet_name=sheet_name,
            total_rows=total_rows,
            total_columns=total_columns,
            columns=col_profiles,
            primary_key_candidates=pk_candidates,
            date_columns=date_cols,
            metric_columns=metric_cols,
            categorical_columns=cat_cols,
            identifier_columns=id_cols
        )

    def _profile_column(self, series: pd.Series, col_name: str, total_rows: int) -> ColumnProfile:
        """Deeply inspects a single column and infers its true data type and semantic role."""
        clean_name = clean_identifier(col_name)
        col_name_lower = col_name.lower().replace("_", " ").replace("-", " ")

        # 1. Nullability & Counts
        # Filter out NaN, None, and empty/whitespace strings
        non_null_mask = series.notna()
        raw_non_null = series[non_null_mask]
        
        # Also treat empty strings and 'nan' strings as null
        clean_non_null = []
        for v in raw_non_null:
            s_val = str(v).strip()
            if s_val and s_val.lower() not in ("nan", "none", "null", "n/a", "--", "nil"):
                clean_non_null.append(v)

        non_null_count = len(clean_non_null)
        null_count = total_rows - non_null_count
        null_pct = round((null_count / total_rows * 100) if total_rows > 0 else 0.0, 2)

        # Handle entirely null column
        if non_null_count == 0:
            return ColumnProfile(
                name=col_name,
                clean_name=clean_name,
                inferred_type="EMPTY",
                sql_type="TEXT",
                semantic_role="Empty Column",
                total_rows=total_rows,
                non_null_count=0,
                null_count=total_rows,
                null_percentage=100.0,
                unique_count=0,
                is_unique=False,
                sample_values=[],
                llm_guidance="Entire column is null/empty. Do not filter or aggregate on this column."
            )

        # 2. Uniqueness & Sample Values
        series_clean = pd.Series(clean_non_null)
        unique_vals = series_clean.unique()
        unique_count = len(unique_vals)
        is_unique = (unique_count == non_null_count) and (non_null_count > 1)
        cardinality_ratio = unique_count / non_null_count if non_null_count > 0 else 0.0

        sample_vals = [self._serialize_val(x) for x in unique_vals[:5]]

        # 3. Type Inference & Heuristics
        inferred_type, sql_type, semantic_role, extra_meta = self._infer_type_and_semantics(
            series_clean, col_name, col_name_lower, non_null_count, unique_count, cardinality_ratio
        )

        # 4. Generate Specific LLM Guidance
        llm_guidance = self._generate_llm_guidance(
            col_name=col_name,
            inferred_type=inferred_type,
            sql_type=sql_type,
            semantic_role=semantic_role,
            unique_count=unique_count,
            null_pct=null_pct,
            extra_meta=extra_meta,
            sample_vals=sample_vals
        )

        return ColumnProfile(
            name=col_name,
            clean_name=clean_name,
            inferred_type=inferred_type,
            sql_type=sql_type,
            semantic_role=semantic_role,
            total_rows=total_rows,
            non_null_count=non_null_count,
            null_count=null_count,
            null_percentage=null_pct,
            unique_count=unique_count,
            is_unique=is_unique,
            sample_values=sample_vals,
            distinct_values=extra_meta.get("distinct_values"),
            value_frequencies=extra_meta.get("value_frequencies"),
            min_value=extra_meta.get("min_value"),
            max_value=extra_meta.get("max_value"),
            mean_value=extra_meta.get("mean_value"),
            median_value=extra_meta.get("median_value"),
            date_format=extra_meta.get("date_format"),
            min_date=extra_meta.get("min_date"),
            max_date=extra_meta.get("max_date"),
            llm_guidance=llm_guidance
        )

    def _infer_type_and_semantics(
        self,
        series: pd.Series,
        col_name: str,
        col_name_lower: str,
        non_null_count: int,
        unique_count: int,
        cardinality_ratio: float
    ) -> Tuple[str, str, str, Dict[str, Any]]:
        """Determines the most accurate type and business semantic role."""
        extra_meta: Dict[str, Any] = {}
        sample_size = min(non_null_count, 200)
        sample_series = series.iloc[:sample_size]

        # Check for explicitly known name patterns
        has_id_keyword = any(k in col_name_lower.split() or col_name_lower.endswith(k) or col_name_lower.startswith(k) for k in IDENTIFIER_KEYWORDS)
        has_financial_keyword = any(k in col_name_lower for k in FINANCIAL_KEYWORDS)
        has_metric_keyword = any(k in col_name_lower for k in METRIC_KEYWORDS) or has_financial_keyword
        has_status_keyword = any(k in col_name_lower for k in STATUS_KEYWORDS)
        has_date_keyword = any(k in col_name_lower for k in ["date", "dob", "created_at", "updated_at", "disbursal", "timestamp"])
        has_time_keyword = any(k in col_name_lower.split() for k in ["time", "timing", "hour"])
        # Check for coordinate keywords (latitude, longitude)
        coordinate_tokens = {"latitude", "longitude", "lat", "lon", "lng"}
        col_tokens = set(re.split(r"[\s_-]+", col_name_lower))
        has_coordinate_keyword = bool(col_tokens & coordinate_tokens) or col_name_lower in coordinate_tokens

        # Check 1: Boolean Check
        string_vals_lower = {str(x).strip().lower() for x in sample_series}
        if string_vals_lower.issubset(BOOLEAN_SET) and len(string_vals_lower) <= 2:
            return "BOOLEAN", "BOOLEAN", "Status / Boolean Flag", {
                "distinct_values": sorted(list({str(x).strip() for x in series.unique()}))
            }

        # Check 2: Time Check (HH:MM:SS)
        time_matches = sum(1 for v in sample_series if TIME_REGEX.match(str(v).strip()))
        if time_matches / sample_size >= 0.85 or (has_time_keyword and time_matches / sample_size >= 0.5):
            return "TIME", "TIME", "Time Dimension", extra_meta

        # Check 3: Date / Timestamp Detection
        date_matches = 0
        detected_date_format = None
        min_date_val = None
        max_date_val = None

        # If already datetime dtype
        if pd.api.types.is_datetime64_any_dtype(series):
            min_dt = series.min()
            max_dt = series.max()
            return "DATETIME", "DATETIME", "Date / Time Dimension", {
                "date_format": "ISO8601",
                "min_date": min_dt.isoformat() if pd.notna(min_dt) else None,
                "max_date": max_dt.isoformat() if pd.notna(max_dt) else None
            }

        # Inspect string date patterns
        for val in sample_series:
            d_res = detect_date_string(str(val))
            if d_res:
                date_matches += 1
                if not detected_date_format:
                    detected_date_format = d_res[0]

        if (date_matches / sample_size >= 0.85 or (has_date_keyword and date_matches / sample_size >= 0.5)) and not has_time_keyword:
            sql_t = "DATETIME" if detected_date_format == "DATETIME" else "DATE"
            # Try to compute min / max date
            sample_dates = []
            for val in series.iloc[:500]:
                d_res = detect_date_string(str(val))
                if d_res and d_res[1]:
                    sample_dates.append(d_res[1])
            if sample_dates:
                sample_dates.sort()
                min_date_val = sample_dates[0]
                max_date_val = sample_dates[-1]

            return "DATE" if sql_t == "DATE" else "DATETIME", sql_t, "Date / Time Dimension", {
                "date_format": detected_date_format,
                "min_date": min_date_val,
                "max_date": max_date_val
            }

        # Check 4: Numeric Check (Coordinates, Float, Integer, Currency, Percentage)
        numeric_count = 0
        parsed_numbers = []
        is_currency = False
        is_pct = False

        for val in sample_series:
            s_val = str(val).strip()
            if s_val.endswith("%"):
                is_pct = True
            if CURRENCY_PREFIX_REGEX.search(s_val):
                is_currency = True

            parsed = try_parse_numeric_string(s_val) if isinstance(val, str) else (val if isinstance(val, (int, float, np.number)) and not math.isnan(val) else None)
            if parsed is not None:
                numeric_count += 1
                parsed_numbers.append(parsed)

        if numeric_count / sample_size >= 0.85:
            # Full series numeric parse
            all_parsed = []
            for v in series:
                p = try_parse_numeric_string(str(v)) if isinstance(v, str) else (v if isinstance(v, (int, float, np.number)) and not math.isnan(v) else None)
                if p is not None:
                    all_parsed.append(p)

            all_parsed_series = pd.Series(all_parsed)
            min_v = float(all_parsed_series.min()) if not all_parsed_series.empty else None
            max_v = float(all_parsed_series.max()) if not all_parsed_series.empty else None
            mean_v = round(float(all_parsed_series.mean()), 2) if not all_parsed_series.empty else None
            median_v = round(float(all_parsed_series.median()), 2) if not all_parsed_series.empty else None

            extra_meta.update({
                "min_value": min_v,
                "max_value": max_v,
                "mean_value": mean_v,
                "median_value": median_v
            })

            # Check if coordinates (Latitude/Longitude)
            if has_coordinate_keyword:
                return "COORDINATE", "DECIMAL(10,6)", "Geographic Dimension", extra_meta

            # Check if all numbers are integers
            all_ints = all(isinstance(x, (int, np.integer)) or (isinstance(x, float) and x.is_integer()) for x in all_parsed[:500])

            # Is it an identifier / code or a mathematical metric?
            if has_id_keyword and not has_financial_keyword and unique_count > 10:
                return "IDENTIFIER", "BIGINT" if all_ints else "VARCHAR(64)", "Identifier / Key", extra_meta

            if is_pct:
                return "PERCENTAGE", "DECIMAL(5,2)", "Metric / Measure", extra_meta

            if is_currency or has_financial_keyword:
                return "CURRENCY", "DECIMAL(15,2)", "Metric / Measure", extra_meta

            if all_ints:
                # Small ranges could be categorical codes or discrete counts
                if unique_count <= 10 and not has_metric_keyword:
                    # Categorical codes (e.g., status 1, 2, 3)
                    val_counts = series.value_counts().head(self.max_categories).to_dict()
                    extra_meta["distinct_values"] = [str(k) for k in val_counts.keys()]
                    extra_meta["value_frequencies"] = {str(k): int(v) for k, v in val_counts.items()}
                    return "INTEGER", "INTEGER", "Categorical Dimension", extra_meta

                return "INTEGER", "INTEGER", "Metric / Measure", extra_meta
            else:
                return "FLOAT", "DECIMAL(12,2)", "Metric / Measure", extra_meta

        # Check 5: Contact / Pattern Formats (Email, Phone, URL, Pincode)
        email_matches = sum(1 for v in sample_series if EMAIL_REGEX.match(str(v).strip()))
        if email_matches / sample_size >= 0.7 or "email" in col_name_lower:
            return "EMAIL", "VARCHAR(255)", "Contact / PII", extra_meta

        phone_matches = sum(1 for v in sample_series if PHONE_REGEX.match(str(v).strip()))
        if phone_matches / sample_size >= 0.7 or any(k in col_name_lower for k in ["mobile", "phone", "contact_no"]):
            return "PHONE_NUMBER", "VARCHAR(30)", "Contact / PII", extra_meta

        url_matches = sum(1 for v in sample_series if URL_REGEX.match(str(v).strip()))
        if url_matches / sample_size >= 0.7 or "url" in col_name_lower or "link" in col_name_lower:
            return "URL", "VARCHAR(500)", "Web Link / Resource", extra_meta

        pincode_matches = sum(1 for v in sample_series if PINCODE_REGEX.match(str(v).strip()))
        if pincode_matches / sample_size >= 0.7 or "pincode" in col_name_lower or "zipcode" in col_name_lower:
            return "POSTAL_CODE", "VARCHAR(10)", "Geographic Dimension", extra_meta

        # Check 5: Identifiers / Codes (Alphanumeric IDs)
        if has_id_keyword or cardinality_ratio > 0.8:
            role = "Primary Key / Identifier" if unique_count == non_null_count else "Identifier / Key"
            return "IDENTIFIER", "VARCHAR(100)", role, extra_meta

        # Check 6: Categorical / Discrete Enums
        if unique_count <= self.max_categories or (unique_count <= 50 and cardinality_ratio < 0.15) or has_status_keyword:
            val_counts = series.value_counts().head(self.max_categories).to_dict()
            extra_meta["distinct_values"] = [str(k) for k in val_counts.keys()]
            extra_meta["value_frequencies"] = {str(k): int(v) for k, v in val_counts.items()}
            max_len = max((len(str(x)) for x in series.unique()[:50]), default=30)
            return "CATEGORICAL", f"VARCHAR({max(30, min(150, max_len))})", "Categorical Dimension", extra_meta

        # Check 7: Free Text / Long Description
        avg_len = sum(len(str(v)) for v in sample_series) / sample_size if sample_size > 0 else 0
        if avg_len > 60 or any(k in col_name_lower for k in ["remark", "comment", "description", "address", "note", "reason"]):
            return "FREE_TEXT", "TEXT", "Notes / Unstructured Text", extra_meta

        # Fallback String
        return "STRING", "VARCHAR(255)", "Text Dimension", extra_meta

    def _generate_llm_guidance(
        self,
        col_name: str,
        inferred_type: str,
        sql_type: str,
        semantic_role: str,
        unique_count: int,
        null_pct: float,
        extra_meta: Dict[str, Any],
        sample_vals: List[Any]
    ) -> str:
        """Generates clear, precise natural-language guidance for LLM SQL generation."""
        guidance_parts = []

        if inferred_type in ("DATE", "DATETIME"):
            fmt = extra_meta.get("date_format", "standard date")
            min_d = extra_meta.get("min_date")
            max_d = extra_meta.get("max_date")
            range_str = f" from {min_d} to {max_d}" if min_d and max_d else ""
            guidance_parts.append(f"Temporal column formatted as '{fmt}'{range_str}. Use appropriate date filters.")

        elif inferred_type == "CATEGORICAL":
            distinct_v = extra_meta.get("distinct_values", [])
            if distinct_v:
                shown = distinct_v[:8]
                vals_str = ", ".join([f"'{v}'" for v in shown])
                extra = f" (+{len(distinct_v) - 8} more)" if len(distinct_v) > 8 else ""
                guidance_parts.append(f"Discrete categorical column with {len(distinct_v)} unique values: [{vals_str}{extra}]. Filter using these exact literal strings.")

        elif inferred_type == "BOOLEAN":
            distinct_v = extra_meta.get("distinct_values", [])
            guidance_parts.append(f"Binary flag. Valid values: {distinct_v}.")

        elif inferred_type in ("CURRENCY", "FLOAT", "INTEGER", "PERCENTAGE") and semantic_role == "Metric / Measure":
            min_v = extra_meta.get("min_value")
            max_v = extra_meta.get("max_value")
            avg_v = extra_meta.get("mean_value")
            stats_str = f" (range: {min_v} to {max_v}, avg: {avg_v})" if min_v is not None and max_v is not None else ""
            guidance_parts.append(f"Numeric metric suitable for SUM(), AVG(), MIN(), MAX(){stats_str}.")

        elif inferred_type == "IDENTIFIER" or "Identifier" in semantic_role:
            guidance_parts.append("Unique/Alphanumeric Identifier. Do NOT perform SUM() or AVG(). Use for COUNT(DISTINCT ...), WHERE equality filters, or JOIN keys.")

        elif inferred_type in ("EMAIL", "PHONE_NUMBER", "POSTAL_CODE"):
            guidance_parts.append(f"Contact/PII field ({inferred_type}). Query with LIKE or exact matches.")

        elif inferred_type == "FREE_TEXT":
            guidance_parts.append("Free-text descriptions/comments. Query using LIKE '%keyword%'.")

        if null_pct > 20.0:
            guidance_parts.append(f"Note: {null_pct}% of rows are NULL. Use IS NOT NULL or COALESCE when calculating ratios.")

        return " ".join(guidance_parts)

    def _serialize_val(self, val: Any) -> Any:
        if pd.isna(val):
            return None
        if isinstance(val, (datetime, pd.Timestamp)):
            return val.isoformat()
        if isinstance(val, (np.integer, int)):
            return int(val)
        if isinstance(val, (np.floating, float)):
            return round(float(val), 4) if not math.isnan(val) else None
        return str(val)

    # ------------------------------------------------------------------
    # Formatted Exporters
    # ------------------------------------------------------------------

    def to_llm_markdown(self, table_profile: TableProfile) -> str:
        """
        Generates an LLM-optimized Markdown Data Dictionary schema context block
        designed to be injected directly into prompt contexts.
        """
        lines = []
        lines.append(f"### Table: `{table_profile.clean_table_name}` (Source: `{Path(table_profile.source_file).name}`)")
        if table_profile.sheet_name:
            lines.append(f"- **Sheet Name:** `{table_profile.sheet_name}`")
        lines.append(f"- **Total Records:** {table_profile.total_rows:,} rows | **Total Columns:** {table_profile.total_columns}")
        
        if table_profile.primary_key_candidates:
            lines.append(f"- **Primary Key Candidates:** {', '.join([f'`{c}`' for c in table_profile.primary_key_candidates])}")
        
        lines.append("\n| Column Name | SQL Type | Inferred Type | Role | Null % | Sample / Allowed Values | LLM Query Instructions |")
        lines.append("|---|---|---|---|---|---|---|")

        for col in table_profile.columns:
            samples_str = ""
            if col.inferred_type == "CATEGORICAL" and col.distinct_values:
                samples_str = ", ".join([f"`{v}`" for v in col.distinct_values[:4]])
                if len(col.distinct_values) > 4:
                    samples_str += f" (+{len(col.distinct_values) - 4} more)"
            elif col.sample_values:
                samples_str = ", ".join([f"`{v}`" for v in col.sample_values[:3]])

            # Clean markdown cell content
            samples_str = samples_str.replace("|", "/")
            guidance = col.llm_guidance.replace("|", "/")

            lines.append(
                f"| **`{col.clean_name}`**<br>*(orig: {col.name})* | `{col.sql_type}` | {col.inferred_type} | {col.semantic_role} | {col.null_percentage}% | {samples_str} | {guidance} |"
            )

        return "\n".join(lines)

    def to_sql_ddl(self, table_profile: TableProfile, dialect: str = "sqlite") -> str:
        """Generates an accurate SQL CREATE TABLE DDL statement with column comments."""
        col_defs = []
        for col in table_profile.columns:
            parts = [f"  `{col.clean_name}` {col.sql_type}"]
            if col.null_percentage == 0.0:
                parts.append("NOT NULL")
            if col.is_unique and col.semantic_role == "Primary Key / Identifier" and col.null_percentage == 0.0:
                parts.append("PRIMARY KEY")

            comment = f"/* orig: '{col.name}', type: {col.inferred_type}, {col.llm_guidance} */"
            col_defs.append(f"{' '.join(parts)} {comment}")

        ddl = f"CREATE TABLE `{table_profile.clean_table_name}` (\n" + ",\n".join(col_defs) + "\n);"
        return ddl

    def to_summary_table(self, table_profile: TableProfile) -> str:
        """Generates a clean terminal ASCII table summary."""
        lines = []
        header = f"=== DATASET PROFILE: {table_profile.table_name} ({table_profile.total_rows:,} rows, {table_profile.total_columns} cols) ==="
        lines.append("=" * len(header))
        lines.append(header)
        lines.append("=" * len(header))

        lines.append(f"{'#':<3} | {'COLUMN NAME':<35} | {'TYPE':<12} | {'SQL TYPE':<15} | {'NULL%':<7} | {'ROLE':<22} | {'SAMPLES / DISTINCT VALUES'}")
        lines.append("-" * 125)

        for i, col in enumerate(table_profile.columns, 1):
            name_disp = (col.name[:32] + "...") if len(col.name) > 35 else col.name
            samples = ", ".join([str(s) for s in (col.distinct_values[:3] if col.distinct_values else col.sample_values[:3])])
            samples_disp = (samples[:35] + "...") if len(samples) > 38 else samples

            lines.append(
                f"{i:<3} | {name_disp:<35} | {col.inferred_type:<12} | {col.sql_type:<15} | {col.null_percentage:<6.1f}% | {col.semantic_role:<22} | {samples_disp}"
            )

        return "\n".join(lines)
