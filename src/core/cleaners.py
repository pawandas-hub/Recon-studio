"""Data cleaning and normalization utilities for IDs, Card Codes, Numbers, and Dates."""
import re
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
            remainder = s[len(prefix):]
            if remainder.isdigit() or len(prefix) in [2, 3]:
                s = remainder
                break
    return s.strip()

def clean_number(val) -> float:
    """Converts mixed number types (strings with commas, floats, ints) to absolute float."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return abs(float(val))
    s = str(val).replace(',', '').strip()
    try:
        return abs(float(s))
    except ValueError:
        return 0.0

def clean_signed_number(val) -> float:
    """Converts mixed number types to float while preserving the source sign."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_date_series(series: pd.Series, dayfirst: bool = True, missing_label: str = 'Missing Date') -> pd.Series:
    """Parses date series into standard YYYY-MM-DD string format safely without swapping ISO dates."""
    if series is None or len(series) == 0:
        return pd.Series(missing_label, index=series.index if series is not None else None)
    
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

