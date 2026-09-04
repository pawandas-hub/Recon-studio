"""Schema and format detector utilities."""
import re
from typing import List, Optional
import pandas as pd

def find_best_sheet(sheet_names: List[str], keywords: List[str], fallback_idx: int = 0) -> str:
    """Finds the sheet name that best matches a list of keywords."""
    for sheet in sheet_names:
        for kw in keywords:
            if kw.lower() in sheet.lower():
                return sheet
    if len(sheet_names) > fallback_idx:
        return sheet_names[fallback_idx]
    return sheet_names[0] if sheet_names else ""

def find_best_col(df: pd.DataFrame, candidate_list: List[str]) -> Optional[str]:
    """Finds the best matching column name in a DataFrame using fuzzy and keyword heuristics."""
    cols = list(df.columns)
    clean_cols_map = {re.sub(r'[\s_\-\(\)\/]+', '', str(col).lower()): col for col in cols}
    
    # Exact clean match
    for cand in candidate_list:
        cand_clean = re.sub(r'[\s_\-\(\)\/]+', '', cand.lower())
        if cand_clean in clean_cols_map:
            return clean_cols_map[cand_clean]

    # Substring search avoiding conflicting keywords
    excluded_col_kw = ['waived', 'tax', 'freight', 'discount']
    excluded_cand_kw = ['date', 'docdate', 'postingdate', 'taxdate', 'id', 'num', 'ref', 'code', 'branch']
    
    for cand in candidate_list:
        cand_clean = re.sub(r'[\s_\-\(\)\/]+', '', cand.lower())
        for key, orig_col in clean_cols_map.items():
            if any(ex in key for ex in excluded_col_kw) and 'waived' not in cand_clean:
                continue
            if any(ex in key for ex in excluded_cand_kw) and 'amt' not in cand_clean and 'cd' not in cand_clean:
                continue
            if cand_clean in key or key in cand_clean:
                return orig_col
    return None

def is_sap_table(df: pd.DataFrame) -> bool:
    """Detects whether a given DataFrame is an SAP general ledger table."""
    cols_clean = [re.sub(r'[\s_\-\(\)\/]+', '', str(c).lower()) for c in df.columns]
    sap_indicators = ['cdlc', 'offsetaccount', 'transno', 'journalvoucher', 'postingdate', 'ref1', 'ref2']
    match_count = sum(1 for ind in sap_indicators if any(ind in c for c in cols_clean))
    return match_count >= 2

def is_customer_mapping_table(df: pd.DataFrame) -> bool:
    """Detects whether a given DataFrame is a Customer ID to SAP Code mapping table."""
    cols_clean = [re.sub(r'[\s_\-\(\)\/]+', '', str(c).lower()) for c in df.columns]
    has_cust_id = any(c in ['customerid', 'retailercustomerid', 'clientid', 'custid'] for c in cols_clean)
    has_sap_code = any(c in ['sapcode', 'sapcustomercode', 'sapcustomerno', 'sapcodeclean', 'sapid'] for c in cols_clean)
    return has_cust_id and has_sap_code

def is_bank_table(df: pd.DataFrame) -> bool:
    """Detects a bank statement using transaction, amount, and date columns."""
    if is_sap_table(df):
        return False
    cols_clean = [re.sub(r'[\s_\-\(\)/]+', '', str(c).lower()) for c in df.columns]
    sales_indicators = ['taxableamount', 'cogscostingcode', 'totalvalueafterdisc', 'cardcode', 'docnum']
    if any(k in cols_clean for k in sales_indicators):
        return False

    has_transaction = any(k in c for c in cols_clean for k in ['transactionid', 'tranid', 'utr', 'transaction'])
    has_amount = any(k in c for c in cols_clean for k in ['depositamt', 'depositamount', 'deposit', 'creditamount', 'credit', 'denototal'])
    has_date = any(k in c for c in cols_clean for k in ['actiondate', 'transactiondate', 'txndate', 'date'])
    has_description = any(k in c for c in cols_clean for k in ['description', 'narration', 'particulars'])
    return (has_transaction and has_amount and has_date) or (has_description and has_amount)

def detect_format(df_bu: pd.DataFrame, df_db: pd.DataFrame, mode: str = "Auto") -> str:
    """Detects reconciliation mode: 'format1' (Standard / Ref 1) or 'format2' (Retailer / Ref 2)."""
    if mode == "Format 1 (Legacy / Ref. 1 vs DB)":
        return "format1"
    if mode == "Format 2 (Retailer / Ref. 2 vs Invoice No)":
        return "format2"
    
    bu_cols_clean = [re.sub(r'[\s_\-\(\)\/]+', '', str(c).lower()) for c in df_bu.columns]
    db_cols_clean = [re.sub(r'[\s_\-\(\)\/]+', '', str(c).lower()) for c in df_db.columns]

    f2_db_indicators = ['invoicenumber', 'invoiceid', 'totalvalueafterdisc', 'totalvalueafterdiscount', 'totalvalue', 'customerid']
    f2_bu_indicators = ['ref2']

    if any(k in db_cols_clean for k in f2_db_indicators) or any(k in bu_cols_clean for k in f2_bu_indicators):
        return "format2"

    return "format1"

