"""Bank statement to SAP collection reconciliation."""
import re
from typing import Optional, Callable
from threading import Event

import pandas as pd

from ..core.cleaners import clean_signed_number, parse_date_series
from ..core.detector import find_best_col


BANK_UTR_COLUMNS = [
    "PNBTransactionID", "TransactionID", "Transaction ID", "Transaction Id", "Tran. Id", "Tran Id",
    "UTR", "UTR No", "Transaction"
]
BANK_DESCRIPTION_COLUMNS = ["Description", "Transaction Remarks", "Narration", "Transaction Details", "Particulars", "Remarks"]
BANK_AMOUNT_COLUMNS = [
    "Deposit Amt (INR)", "Deposit Amount", "Deposit", "Credit Amount", "Credit", "Amount (INR)", "Amount",
    "NetPayout", "Deno Total", "Deno Total", "Total"
]
BANK_DATE_COLUMNS = ["ActionDate", "Transaction Date", "Txn Date", "Date", "Value Date", "Transaction Posted Date", "Posting Date"]
BANK_STATUS_COLUMNS = ["Txn Status", "Transaction Status", "Status"]
BANK_BUSINESS_TYPE_COLUMNS = ["Business Type", "BusinessType", "Business Type ", "Channel Type"]
BANK_ACCOUNT_NUMBER_COLUMNS = ["Account Number", "Account No", "A/C No", "CMS_CCA_Account"]
SAP_OFFSET_ACCOUNT_COLUMNS = ["Offset Account", "OffsetAccount", "Offset Acct", "Account", "CardCode", "Card Code", "CustomerCode"]
SAP_DETAILS_COLUMNS = ["Details", "Detail"]
SAP_ORIGIN_COLUMNS = ["Origin No.", "Origin No", "OriginNo"]
SAP_REFERENCE_COLUMNS = ["Ref. 2", "Ref 2", "Ref. 1", "Ref 1", "Reference"]
SAP_AMOUNT_COLUMNS = ["C/D (LC)", "C/D(LC)", "CD LC", "Debit (LC)", "Amount (LC)", "LC Amount"]


def _normalise_utr(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper().strip())


def extract_scb_utr(value) -> str:
    """Extract the token after | or /, matching the SCB statement convention."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    first_word = text.split()[0] if text.split() else ""
    match = re.search(r"(?:\||/)([^\s|/]+)", first_word)
    return _normalise_utr(match.group(1) if match else "")


def detect_bank_type(df: pd.DataFrame) -> Optional[str]:
    from ..core.detector import is_sap_table
    if is_sap_table(df):
        return None

    cols_lower = [str(c).lower() for c in df.columns]
    cols_clean = [re.sub(r'[\s_\-\(\)\/]+', '', str(c).lower()) for c in df.columns]

    sales_indicators = ['taxableamount', 'cogscostingcode', 'totalvalueafterdisc', 'cardcode', 'docnum']
    if any(k in cols_clean for k in sales_indicators):
        return None

    if any('pnbtransactionid' in c or 'pnb' in c for c in cols_clean):
        return 'PNB'

    if any('cms' in c or 'transactionid' in c for c in cols_clean) and any('actiondate' in c or 'transactiondate' in c for c in cols_clean) and any('denototal' in c or 'total' in c for c in cols_clean):
        return 'CMS'

    # ICICI statements
    if any('tran. id' in c or 'tran id' in c or 'transaction id' in c for c in cols_lower) or any('icici' in c for c in cols_lower):
        if any('deposit amt' in c or 'deposit' in c for c in cols_lower):
            return 'ICICI'
    # SCB statements
    if any('scb' in c or 'standard chartered' in c for c in cols_lower) or (any(c.strip() == 'deposit' for c in cols_lower) and any('description' in c or 'particulars' in c for c in cols_lower)):
        return 'SCB'
    if any('deposit' in c or 'credit' in c for c in cols_clean) and any('tran' in c or 'utr' in c or 'narration' in c or 'remarks' in c or 'description' in c for c in cols_clean):
        return 'Bank'
    return None


def is_bank_table(df: pd.DataFrame) -> bool:
    return detect_bank_type(df) is not None


def _resolve_reversal_utrs(sap: pd.DataFrame, details_col: str, origin_col: Optional[str], amount_col: str) -> pd.DataFrame:
    sap = sap.copy()
    sap["_sap_utr"] = sap[details_col].apply(_normalise_utr)
    sap["_exclude_from_total"] = False
    sap["_reversal_note"] = ""
    if not origin_col:
        return sap

    sap["_origin"] = sap[origin_col].apply(_normalise_utr)
    for origin, group in sap[sap["_origin"] != ""].groupby("_origin"):
        if len(group) < 2:
            continue
        positive = group[group[amount_col].apply(clean_signed_number) >= 0]
        negative = group[group[amount_col].apply(clean_signed_number) < 0]
        if positive.empty or negative.empty:
            continue
        replacement = positive.iloc[0]["_sap_utr"]
        if not replacement:
            continue
        reversal_note = f"Reversal resolved through Origin No. {origin}"
        sap.loc[negative.index, "_sap_utr"] = replacement
        sap.loc[negative.index, "_reversal_note"] = reversal_note
        sap.loc[negative.index, "_exclude_from_total"] = True
        # Also add the reversal note to the positive row so it appears in the final remarks
        sap.loc[positive.index, "_reversal_note"] = sap.loc[positive.index, "_reversal_note"].apply(
            lambda x: f"{x}; {reversal_note}" if x else reversal_note
        )
    return sap


def _select_sap_candidates(candidates: list, bank_amount: float, bank_date: str) -> dict:
    """Select the smallest SAP entry combination matching a bank deposit."""
    usable = [candidate for candidate in candidates if candidate.get("amount", 0) > 0]
    if not usable:
        return candidates[0] if candidates else {"amount": 0.0, "details": "", "offset_account": "", "posting_date": "", "origin": "", "reversal": ""}

    # 1. Fast path: direct single candidate exact match
    exact_candidates = [c for c in usable if abs(c["amount"] - bank_amount) <= 0.05]
    if exact_candidates:
        same_date = [c for c in exact_candidates if c.get("posting_date") == bank_date]
        return (same_date[0] if same_date else exact_candidates[0]).copy()

    # 2. Check if total sum matches
    total_usable = sum(c["amount"] for c in usable)
    if abs(total_usable - bank_amount) <= 0.05:
        return {
            "amount": round(total_usable, 2),
            "details": "; ".join(dict.fromkeys(c["details"] for c in usable if c.get("details"))),
            "offset_account": "; ".join(dict.fromkeys(c["offset_account"] for c in usable if c.get("offset_account"))),
            "posting_date": "; ".join(dict.fromkeys(c["posting_date"] for c in usable if c.get("posting_date"))),
            "origin": "; ".join(dict.fromkeys(c["origin"] for c in usable if c.get("origin"))),
            "reversal": ""
        }

    # 3. For subset combination, bound candidates to at most top 8 closest
    subset_pool = sorted(usable, key=lambda c: (abs(c["amount"] - bank_amount), c.get("posting_date") != bank_date))[:8]
    best = None

    def search(start: int, selected: list, total: float) -> None:
        nonlocal best
        variance = abs(total - bank_amount)
        if selected and variance <= 0.05:
            score = (round(variance, 2), len(selected), sum(c.get("posting_date") != bank_date for c in selected))
            if best is None or score < best[0]:
                best = (score, selected.copy())
            return
        if total >= bank_amount + 0.05 or len(selected) >= 6:
            return
        for index in range(start, len(subset_pool)):
            search(index + 1, selected + [subset_pool[index]], total + subset_pool[index]["amount"])

    search(0, [], 0.0)
    if best:
        selected = best[1]
        return {
            "amount": round(sum(c["amount"] for c in selected), 2),
            "details": "; ".join(dict.fromkeys(c["details"] for c in selected if c.get("details"))),
            "offset_account": "; ".join(dict.fromkeys(c["offset_account"] for c in selected if c.get("offset_account"))),
            "posting_date": "; ".join(dict.fromkeys(c["posting_date"] for c in selected if c.get("posting_date"))),
            "origin": "; ".join(dict.fromkeys(c["origin"] for c in selected if c.get("origin"))),
            "reversal": ""
        }

    return min(
        usable,
        key=lambda c: (
            abs(c["amount"] - bank_amount) > 0.05,
            c.get("posting_date") != bank_date,
            abs(c["amount"] - bank_amount)
        )
    )


def reconcile_bank_to_sap(
    bank_df: pd.DataFrame,
    sap_df: pd.DataFrame,
    bank_type: Optional[str] = None,
    account_number: str = '',
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    cancel_event: Optional[Event] = None
) -> pd.DataFrame:
    """Reconcile bank deposits against SAP C/D amounts using UTRs."""
    def report(stage: str, current: int = 0, total: int = 0) -> None:
        if progress_callback:
            progress_callback(stage, current, total)

    def check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Reconciliation cancelled by user")

    bank_type = bank_type or detect_bank_type(bank_df) or "Bank"
    bank_df = bank_df.copy()
    sap_df = sap_df.copy()
    bank_utr_col = find_best_col(bank_df, BANK_UTR_COLUMNS)
    bank_desc_col = find_best_col(bank_df, BANK_DESCRIPTION_COLUMNS)
    bank_amt_col = find_best_col(bank_df, BANK_AMOUNT_COLUMNS)
    bank_date_col = find_best_col(bank_df, BANK_DATE_COLUMNS)
    bank_status_col = find_best_col(bank_df, BANK_STATUS_COLUMNS)
    bank_business_col = find_best_col(bank_df, BANK_BUSINESS_TYPE_COLUMNS)
    bank_account_col = find_best_col(bank_df, BANK_ACCOUNT_NUMBER_COLUMNS)
    # For CMS: only use account_number if it's explicitly passed as a parameter.
    # The extracted account_number from ZIP attrs may be incorrect (e.g., cell reference or report ID).
    if bank_type.upper() == "CMS" and not account_number:
        account_number = ""  # Don't use the attrs value for CMS
    else:
        account_number = account_number or str(bank_df.attrs.get('account_number', ''))
    sap_details_col = find_best_col(sap_df, SAP_DETAILS_COLUMNS)
    sap_origin_col = find_best_col(sap_df, SAP_ORIGIN_COLUMNS)
    sap_offset_col = find_best_col(sap_df, SAP_OFFSET_ACCOUNT_COLUMNS)
    sap_amt_col = find_best_col(sap_df, SAP_AMOUNT_COLUMNS)

    if not bank_amt_col or not sap_details_col or not sap_amt_col:
        raise ValueError("Could not identify bank amount, SAP Details, or SAP C/D (LC) columns.")

    report(f"Preparing {bank_type} bank statement")

    if bank_type.upper() == "PNB":
        bank_df = bank_df[bank_df[bank_status_col].astype(str).str.lower().eq('success')].copy() if bank_status_col else bank_df.copy()
        if bank_business_col:
            bank_df = bank_df[bank_df[bank_business_col].astype(str).str.lower().str.contains('omni', na=False)].copy()
        if bank_utr_col:
            bank_df["Bank_UTR"] = bank_df[bank_utr_col].apply(_normalise_utr)
        else:
            bank_df["Bank_UTR"] = ""
    elif bank_type.upper() == "CMS":
        if bank_account_col and account_number:
            account_pattern = str(account_number).strip()
            bank_df = bank_df[bank_df[bank_account_col].astype(str).str.contains(account_pattern, na=False)].copy()
        if bank_utr_col:
            bank_df["Bank_UTR"] = bank_df[bank_utr_col].apply(_normalise_utr)
        else:
            bank_df["Bank_UTR"] = ""
    elif bank_type.upper() == "ICICI" and bank_utr_col:
        bank_df["Bank_UTR"] = bank_df[bank_utr_col].apply(_normalise_utr)
    elif bank_desc_col:
        bank_df["Bank_UTR"] = bank_df[bank_desc_col].apply(extract_scb_utr)
    else:
        bank_df["Bank_UTR"] = ""

    bank_df["Bank_Amount"] = bank_df[bank_amt_col].apply(clean_signed_number).abs()
    bank_df["Bank_Date"] = parse_date_series(bank_df[bank_date_col], dayfirst=True) if bank_date_col else "Missing Bank Date"
    bank_df = bank_df[bank_df["Bank_Amount"] > 0].copy().reset_index(drop=True)

    report(f"Building SAP lookup for {bank_type}")
    sap_df["SAP_Amount_Signed"] = sap_df[sap_amt_col].apply(clean_signed_number)
    sap_date_col = find_best_col(sap_df, ["Posting Date", "Date"])
    sap_df["SAP_Posting_Date"] = parse_date_series(sap_df[sap_date_col], dayfirst=True) if sap_date_col else "Missing SAP Date"
    sap_df["SAP_Offset_Account_Clean"] = sap_df[sap_offset_col].fillna("").astype(str).str.strip() if sap_offset_col else ""
    sap_df = _resolve_reversal_utrs(sap_df, sap_details_col, sap_origin_col, sap_amt_col)
    if "_origin" not in sap_df:
        sap_df["_origin"] = ""
    sap_df["SAP_UTR"] = sap_df["_sap_utr"]
    sap_df["SAP_Details_Value"] = sap_df[sap_details_col].fillna("").astype(str)

    sap_lookup: dict = {}
    for utr, group in sap_df[(sap_df["SAP_UTR"] != "") & ~sap_df["_exclude_from_total"]].groupby("SAP_UTR", sort=False):
        records = group[["SAP_Amount_Signed", "SAP_Details_Value", "SAP_Posting_Date", "_origin", "SAP_Offset_Account_Clean"]].to_dict("records")
        candidates = [
            {
                "amount": abs(r["SAP_Amount_Signed"]),
                "details": r["SAP_Details_Value"],
                "posting_date": r["SAP_Posting_Date"],
                "origin": r["_origin"],
                "offset_account": r["SAP_Offset_Account_Clean"],
            }
            for r in records
        ]
        candidates.append({
            "amount": abs(group["SAP_Amount_Signed"].sum()),
            "details": "; ".join(group["SAP_Details_Value"].drop_duplicates()),
            "offset_account": "; ".join(group["SAP_Offset_Account_Clean"].drop_duplicates()),
            "posting_date": "; ".join(group["SAP_Posting_Date"].drop_duplicates()),
            "origin": "; ".join(group["_origin"].drop_duplicates()),
        })
        sap_lookup[utr] = {
            "candidates": candidates,
            "reversal": "; ".join(group["_reversal_note"].fillna("").astype(str).drop_duplicates())
        }

    total_bank_rows = len(bank_df)
    results = []
    report(f"Matching {bank_type} deposits against SAP", 0, total_bank_rows)
    batch_size = max(50, total_bank_rows // 20)

    for batch_start in range(0, total_bank_rows, batch_size):
        check_cancelled()
        batch = bank_df.iloc[batch_start:batch_start + batch_size]
        for _, bank_row in batch.iterrows():
            check_cancelled()
            # Use the Bank_UTR column we already populated during preprocessing
            bank_utr = bank_row.get("Bank_UTR", "") if "Bank_UTR" in bank_df.columns else (
                _normalise_utr(bank_row[bank_utr_col]) if bank_utr_col else ""
            )
            description = str(bank_row[bank_desc_col]) if bank_desc_col and not pd.isna(bank_row[bank_desc_col]) else ""
            entry = sap_lookup.get(bank_utr) if bank_utr else None
            fallback = False
            if entry is None and description:
                tokens = re.findall(r"[A-Za-z0-9]{4,}", str(description))
                for token in tokens:
                    norm_token = _normalise_utr(token)
                    if norm_token in sap_lookup:
                        entry = sap_lookup[norm_token]
                        bank_utr = norm_token
                        fallback = True
                        break

            bank_amount = float(clean_signed_number(bank_row[bank_amt_col])) if bank_amt_col else 0.0
            bank_amount = abs(bank_amount)
            bank_date = str(parse_date_series(pd.Series([bank_row[bank_date_col]]), dayfirst=True).iloc[0]) if bank_date_col else "Missing Bank Date"
            if entry and "candidates" in entry:
                selected_entry = _select_sap_candidates(entry["candidates"], bank_amount, bank_date)
                selected_entry["reversal"] = entry.get("reversal", "")
                entry = selected_entry
            sap_amount = entry["amount"] if entry else 0.0
            variance = round(bank_amount - sap_amount, 2)
            if not bank_utr:
                status = "Not Matched"
                remarks = "MISMATCHED: Bank UTR could not be extracted"
            elif not entry:
                status = "Not Matched"
                remarks = f"MISMATCHED: UTR {bank_utr} not found in SAP Details"
            elif abs(variance) > 0.05:
                status = "Not Matched"
                remarks = f"MISMATCHED: Amount variance ({variance}) for UTR {bank_utr}"
            else:
                status = "Matched"
                remarks = "MATCHED: UTR and amount agree"
                if fallback:
                    remarks += "; UTR resolved from bank description"
            if entry and entry.get("reversal"):
                remarks += f"; {entry['reversal']}"

            if bank_type.upper() in {"PNB", "CMS"}:
                account_display = f"{bank_type}_CCA_Account"
            else:
                account_display = (
                    f"{bank_type} - {bank_row[bank_account_col] if bank_account_col and not pd.isna(bank_row[bank_account_col]) and re.search(r'\d{8,}', str(bank_row[bank_account_col])) else account_number}".strip(' -')
                )

            results.append({
                "Bank_Name": bank_type,
                "Bank_Account_Number": account_display,
                "Bank_Date": bank_date,
                "Bank_UTR": bank_utr,
                "Bank_Description": description,
                "Bank_Amount": bank_amount,
                "SAP_UTR": bank_utr if entry else "Missing in SAP",
                "SAP_Offset_Account": entry.get("offset_account", "") if (entry and entry.get("offset_account")) else ("Missing in SAP" if not entry else "N/A"),
                "SAP_Details": entry["details"] if entry else "Missing in SAP",
                "SAP_Origin_No": entry["origin"] if entry else "Missing in SAP",
                "SAP_Posting_Date": entry["posting_date"] if entry else "Missing in SAP",
                "SAP_Amount": sap_amount,
                "Amount_Variance": variance,
                "Overall_Status": status,
                "Reconciliation_Remarks": remarks,
            })
        report(f"Matching {bank_type} deposits against SAP", min(batch_start + batch_size, total_bank_rows), total_bank_rows)

    return pd.DataFrame(results)
