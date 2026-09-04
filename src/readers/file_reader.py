"""Robust file reader for Excel, TSV, CSV, and HTML tables with automatic encoding fallbacks.

Session-level cache ensures each file is read at most once per reconciliation run,
preventing the 2-3x redundant reads that slow down large file processing.
"""
import io
import os
import zipfile
from typing import Tuple, Dict
import pandas as pd
from ..core.detector import find_best_sheet

# Session cache: maps (abs_path, mtime) -> (df_bu, df_db)
_FILE_CACHE: Dict[Tuple[str, float], Tuple[pd.DataFrame, pd.DataFrame]] = {}


def clear_cache() -> None:
    """Clear the session file cache. Call between reconciliation runs if needed."""
    _FILE_CACHE.clear()

def read_file_tables(file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Reads a data file (.xlsx, .xls, .tsv, .csv, .html) and extracts primary and secondary tables.
    Returns (df_bu, df_db).

    Results are cached for the duration of the Python session keyed by (abs_path, mtime).
    Subsequent calls for the same unchanged file return instantly.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: '{file_path}'")

    abs_path = os.path.abspath(file_path)
    mtime = os.path.getmtime(abs_path)
    cache_key = (abs_path, mtime)

    if cache_key in _FILE_CACHE:
        df_bu, df_db = _FILE_CACHE[cache_key]
        return df_bu.copy(), df_db.copy()

    result = _read_uncached(abs_path)
    _FILE_CACHE[cache_key] = (result[0].copy(), result[1].copy())
    return result


def _read_uncached(file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Internal: actually reads the file without caching."""
    basename = os.path.basename(file_path)

    # Sniff magic bytes
    magic = b""
    try:
        with open(file_path, "rb") as f:
            magic = f.read(16)
    except Exception:
        pass

    # 1. ZIP archive: accept a nested spreadsheet inside the archive without creating a locked temp file on Windows
    if file_path.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(file_path) as zf:
                members = [n for n in zf.namelist() if not n.endswith('/')]
                for name in members:
                    lower = name.lower()
                    if not lower.endswith(('.xls', '.xlsx', '.xlsm', '.csv', '.tsv')):
                        continue
                    payload = zf.read(name)
                    if lower.endswith(('.csv', '.tsv')):
                        sep = '\t' if lower.endswith('.tsv') else ','
                        for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                            try:
                                df = pd.read_csv(io.BytesIO(payload), sep=sep, encoding=enc, low_memory=False)
                                df.columns = [str(c).replace('\ufeff', '').strip() for c in df.columns]
                                if len(df.columns) > 1:
                                    return df, df.copy()
                            except Exception:
                                continue
                        continue
                    if lower.endswith(('.xls', '.xlsx', '.xlsm')):
                        for engine in [None, 'openpyxl', 'calamine', 'xlrd']:
                            try:
                                excel_file = pd.ExcelFile(io.BytesIO(payload), engine=engine)
                                sheets = excel_file.sheet_names
                                if len(sheets) > 1:
                                    bu_sheet = find_best_sheet(sheets, ["BU", "SAP", "Journal", "24", "14"], fallback_idx=0)
                                    db_sheet = find_best_sheet(sheets, ["result", "DB", "Sales", "Database", "Raw", "Retailer", "FnV", "Sheet1"], fallback_idx=1)
                                    df_bu = pd.read_excel(excel_file, sheet_name=bu_sheet)
                                    df_db = pd.read_excel(excel_file, sheet_name=db_sheet)
                                else:
                                    raw = pd.read_excel(excel_file, sheet_name=sheets[0], header=None)
                                    header_row = _find_table_header(raw)
                                    df_bu = pd.read_excel(excel_file, sheet_name=sheets[0], header=header_row)
                                    df_db = df_bu.copy()
                                    account_number = _find_account_number(raw)
                                    if account_number:
                                        df_bu.attrs["account_number"] = account_number
                                        df_db.attrs["account_number"] = account_number
                                return df_bu, df_db
                            except Exception:
                                continue
        except Exception:
            pass

    # 2. Fast path: UTF-16 BOM detection (SAP .xls export is actually a UTF-16 TSV)
    if magic.startswith(b"\xff\xfe") or magic.startswith(b"\xfe\xff"):
        encoding = "utf-16le" if magic.startswith(b"\xff\xfe") else "utf-16be"
        try:
            df = pd.read_csv(file_path, sep="\t", encoding=encoding, low_memory=False)
            df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
            if len(df.columns) > 1 and not df.columns[0].startswith("ÿþ"):
                return df, df.copy()
        except Exception:
            pass

    # 3. Fast path: Standard OpenXML / Excel (.xlsx, .xlsm)
    if magic.startswith(b"PK\x03\x04") or file_path.lower().endswith((".xlsx", ".xlsm")):
        for engine in [None, "openpyxl", "calamine"]:
            try:
                excel_file = pd.ExcelFile(file_path, engine=engine)
                sheets = excel_file.sheet_names
                if len(sheets) > 1:
                    bu_sheet = find_best_sheet(sheets, ["BU", "SAP", "Journal", "24", "14"], fallback_idx=0)
                    db_sheet = find_best_sheet(sheets, ["result", "DB", "Sales", "Database", "Raw", "Retailer", "FnV", "Sheet1"], fallback_idx=1)
                    df_bu = pd.read_excel(excel_file, sheet_name=bu_sheet)
                    df_db = pd.read_excel(excel_file, sheet_name=db_sheet)
                else:
                    raw = pd.read_excel(file_path, sheet_name=sheets[0], header=None)
                    header_row = _find_table_header(raw)
                    df_bu = pd.read_excel(file_path, sheet_name=sheets[0], header=header_row)
                    df_db = df_bu.copy()
                    account_number = _find_account_number(raw)
                    if account_number:
                        df_bu.attrs["account_number"] = account_number
                        df_db.attrs["account_number"] = account_number
                return df_bu, df_db
            except Exception:
                continue

    # 4. Fast path: HTML disguised as .xls
    if magic.lstrip().startswith((b"<html", b"<!DOCTYPE", b"<!doctype", b"<table", b"<HTML")):
        try:
            tables = pd.read_html(file_path)
            if tables:
                df_bu = tables[0]
                df_db = tables[1] if len(tables) > 1 else tables[0]
                return df_bu, df_db
        except Exception:
            pass

    # 5. Standard CSV/TSV with UTF-8 / latin1
    for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
        for sep in ["\t", ","]:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding=enc, low_memory=False)
                df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
                if len(df.columns) > 1:
                    return df, df.copy()
            except Exception:
                pass

    # 6. General fallback Excel engines
    for engine in [None, "openpyxl", "xlrd", "pyxlsb", "calamine"]:
        try:
            excel_file = pd.ExcelFile(file_path, engine=engine)
            sheets = excel_file.sheet_names
            if len(sheets) > 1:
                bu_sheet = find_best_sheet(sheets, ["BU", "SAP", "Journal", "24", "14"], fallback_idx=0)
                db_sheet = find_best_sheet(sheets, ["result", "DB", "Sales", "Database", "Raw", "Retailer", "FnV", "Sheet1"], fallback_idx=1)
                df_bu = pd.read_excel(excel_file, sheet_name=bu_sheet)
                df_db = pd.read_excel(excel_file, sheet_name=db_sheet)
            else:
                raw = pd.read_excel(file_path, sheet_name=sheets[0], header=None)
                header_row = _find_table_header(raw)
                df_bu = pd.read_excel(file_path, sheet_name=sheets[0], header=header_row)
                df_db = df_bu.copy()
                account_number = _find_account_number(raw)
                if account_number:
                    df_bu.attrs["account_number"] = account_number
                    df_db.attrs["account_number"] = account_number
            return df_bu, df_db
        except Exception:
            continue

    raise ValueError(
        f"Could not parse '{basename}'. "
        f"Supported formats: .xlsx, .xls, .xlsm, .tsv, .csv. "
        f"Check the file is not open in Excel and is not corrupted."
    )


def _find_table_header(raw: pd.DataFrame) -> int:
    """Find a bank-table header in workbooks with report metadata above it."""
    for index, row in raw.head(40).iterrows():
        values = {str(value).strip().lower() for value in row if not pd.isna(value)}
        if any('tran' in value and 'id' in value for value in values) and any('deposit' in value for value in values):
            return int(index)
        if any('description' in value for value in values) and any(value == 'deposit' or 'deposit' in value for value in values):
            return int(index)
    return 0


def _find_account_number(raw: pd.DataFrame) -> str:
    """Read an account number from bank metadata above the transaction table."""
    for _, row in raw.head(40).iterrows():
        values = [str(value).strip() for value in row if not pd.isna(value)]
        for position, value in enumerate(values[:-1]):
            if value.lower() in {'a/c no:', 'a/c no', 'account number'}:
                for candidate in values[position + 1:]:
                    if candidate.isdigit() and len(candidate) >= 8:
                        return candidate
    for value in raw.head(40).astype(str).stack():
        candidate = str(value).strip()
        if candidate.isdigit() and len(candidate) >= 8:
            return candidate
    return ''

