"""Data cleaning and normalization utilities for IDs, Card Codes, Numbers, and Dates."""
import re
from typing import Optional
import pandas as pd

def clean_id(val) -> str:
    """Extracts numeric sequence from alphanumeric IDs (e.g., 'AR-OMNI-1458247' -> '1458247')."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    digits = re.findall(r'\d+', s)
    return digits[-1] if digits else s

def clean_afc_id(val) -> str:
    """Extracts clean invoice id by stripping 'AFC' prefix (e.g. 'AFC12345' -> '12345')."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    s_cleaned = re.sub(r'^afc[-_\s]*', '', s, flags=re.IGNORECASE).strip()
    digits = re.findall(r'\d+', s_cleaned)
    return digits[-1] if digits else s_cleaned


def clean_card(val) -> str:
    """Normalizes customer/card codes by stripping prefixes like OM, CU, DOM, BP, C."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    s_upper = s.upper()
    for prefix in ['OM', 'CU', 'DOM', 'BP', 'C']:
        if s_upper.startswith(prefix):
            remainder = s[len(prefix):].lstrip('-_ ')
            # Only strip prefix when the remainder is purely numeric
            if remainder.isdigit():
                s = remainder
                break
    return s.strip()

def clean_signed_number(val) -> float:
    """Converts mixed number types to float while preserving the source sign.

    Supports standard formats and SAP accounting formats:
      - Currency prefixes: "INR (2,223.41)" → -2223.41, "INR 2,223.41" → 2223.41
      - Trailing minus:    "50000.00-"       → -50000.0
      - Parentheses (CR):  "(1,234.50)"      → -1234.5
      - CR/DR notation:    "1,234.50 CR"     → -1234.5
    """
    if val is None or pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        import math
        return 0.0 if math.isnan(val) else float(val)
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'null', '<na>', ''):
        return 0.0

    # Strip currency prefixes (e.g. INR, RS, RS., USD, EUR, GBP, ₹, $, €, £)
    s = re.sub(r'^(?:INR|RS\.?|USD|EUR|GBP|AUD|CAD|₹|\$|€|£)\s*', '', s, flags=re.IGNORECASE).strip()
    s = s.replace(',', '').strip()

    # Trailing minus: '123.45-'
    if s.endswith('-'):
        s = '-' + s[:-1].strip()
    # Accounting parentheses format: '(123.45)' or '(INR 123.45)'
    elif s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1].strip()

    is_neg = s.startswith('-')
    if is_neg:
        s = s[1:].strip()
    # Strip any inner currency code if it was inside parentheses e.g. -(INR 123.45)
    s = re.sub(r'^(?:INR|RS\.?|USD|EUR|GBP|AUD|CAD|₹|\$|€|£)\s*', '', s, flags=re.IGNORECASE).strip()

    if s.upper().endswith('CR'):
        is_neg = True
        s = s[:-2].strip()
    elif s.upper().endswith('DR'):
        s = s[:-2].strip()

    try:
        val_float = float(s)
        return -val_float if is_neg else val_float
    except ValueError:
        return 0.0

def clean_number(val) -> float:
    """Converts mixed number types (strings with commas, currency prefixes, floats, ints) to absolute float."""
    return abs(clean_signed_number(val))


def clean_number_series(s: Optional[pd.Series]) -> pd.Series:
    """Vectorized helper: converts a Series to absolute float quickly."""
    if s is None or s.empty:
        return pd.Series(0.0)
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0.0).abs().astype(float)
    return s.apply(clean_number)

def clean_signed_number_series(s: Optional[pd.Series]) -> pd.Series:
    """Vectorized helper: converts a Series to signed float quickly."""
    if s is None or s.empty:
        return pd.Series(0.0)
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0.0).astype(float)
    return s.apply(clean_signed_number)

def parse_date_series(series: pd.Series, dayfirst: bool = True, missing_label: str = 'Missing Date') -> pd.Series:
    """Parses date series into standard YYYY-MM-DD string format safely without swapping ISO dates."""
    if series is None:
        return pd.Series([], dtype=object)
    if len(series) == 0:
        return pd.Series(missing_label, index=series.index)
    
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime('%Y-%m-%d').fillna(missing_label)

    unique_vals = series.dropna().unique()
    def parse_dt(v):
        s = str(v).strip()
        if not s or s.lower() in ('nan', 'none', 'nat', '<na>'):
            return missing_label
        if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', s):
            dt = pd.to_datetime(s, errors='coerce')
        else:
            dt = pd.to_datetime(s, dayfirst=dayfirst, errors='coerce')
        return dt.strftime('%Y-%m-%d') if pd.notna(dt) else missing_label

    date_map = {v: parse_dt(v) for v in unique_vals}
    return series.map(date_map).fillna(missing_label)

