"""Reconciliation Engine implementing Format 1 (Standard) and Format 2 (Retailer/FnV) algorithms."""
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from typing import Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from ..core.cleaners import clean_id, clean_card, clean_number, clean_signed_number, parse_date_series
from ..core.constants import FORMAT1_BU_COLS, FORMAT1_DB_COLS, FORMAT2_BU_COLS, FORMAT2_DB_COLS
from ..core.detector import find_best_col, detect_format, is_sap_table
from ..readers.file_reader import read_file_tables
from .customer_service import CustomerMappingService
from .bank_recon import reconcile_bank_to_sap, detect_bank_type, is_bank_table


class ReconciliationEngine:
    """Core engine to aggregate, match, and reconcile SAP and Sales/DB dataframes."""

    def __init__(self, mode: str = "Auto", customer_service: Optional[CustomerMappingService] = None):
        self.mode = mode
        self.customer_service = customer_service or CustomerMappingService.load_from_sources()

    def reconcile(
        self,
        df_bu_raw: pd.DataFrame,
        df_db_raw: pd.DataFrame,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> pd.DataFrame:
        def report(stage: str, current: int = 0, total: int = 0) -> None:
            if progress_callback:
                progress_callback(stage, current, total)

        df_bu = df_bu_raw.copy()
        df_db = df_db_raw.copy()

        df_bu.columns = [str(c).replace('\n', ' ').strip() for c in df_bu.columns]
        df_db.columns = [str(c).replace('\n', ' ').strip() for c in df_db.columns]

        fmt = detect_format(df_bu, df_db, self.mode)

        if fmt == "format2":
            bu_cols = FORMAT2_BU_COLS
            db_cols = FORMAT2_DB_COLS
            ref_col_name = 'Ref2_Invoice_No'
            format_label = 'Format 2 (Ref.2 / Retailer FnV)'
        else:
            bu_cols = FORMAT1_BU_COLS
            db_cols = FORMAT1_DB_COLS
            ref_col_name = 'RefId_Ref1'
            format_label = 'Format 1 (Ref.1 / Standard SAP)'

        report("Finding column mappings", 0, 5)
        bu_ref = find_best_col(df_bu, bu_cols['ref']) or df_bu.columns[0]
        bu_date = find_best_col(df_bu, bu_cols['date'])
        bu_amt = find_best_col(df_bu, bu_cols['amt'])
        bu_acc = find_best_col(df_bu, bu_cols['acc'])
        bu_unit = find_best_col(df_bu, bu_cols['unit'])

        db_ref = find_best_col(df_db, db_cols['ref']) or df_db.columns[0]
        db_date = find_best_col(df_db, db_cols['date'])
        db_taxable = find_best_col(df_db, db_cols['taxable'])
        db_card = find_best_col(df_db, db_cols['card'])
        db_unit = find_best_col(df_db, db_cols['unit'])

        report("Aggregating SAP ledger", 1, 5)
        # BU (SAP) aggregation
        df_bu['Ref_Clean'] = df_bu[bu_ref].apply(clean_id)
        df_bu_valid = df_bu[df_bu['Ref_Clean'] != ''].copy()
        df_bu_valid['PostingDate_Std'] = parse_date_series(df_bu_valid[bu_date], dayfirst=True) if bu_date else 'Missing Date'
        df_bu_valid['Offset_Clean'] = df_bu_valid[bu_acc].apply(clean_card) if bu_acc else ''
        df_bu_valid['BU_Clean'] = df_bu_valid[bu_unit].astype(str) if bu_unit else 'Default_BU'
        # Net debit/credit lines before taking the absolute ledger total.
        # Taking abs() per row incorrectly doubles reversal entries.
        df_bu_valid['Amt_Clean'] = (
            df_bu_valid[bu_amt].apply(clean_signed_number) if bu_amt else 0.0
        )

        bu_groups = df_bu_valid.groupby('Ref_Clean', sort=False)
        bu_agg = bu_groups.agg({
            'BU_Clean': 'first',
            'PostingDate_Std': 'first',
            'Offset_Clean': 'first',
            'Amt_Clean': 'sum'
        }).rename(columns={
            'BU_Clean': 'Business_Unit',
            'PostingDate_Std': 'Posting_Date',
            'Offset_Clean': 'SAP_Offset_Account',
            'Amt_Clean': 'Total_CD_LC'
        })
        bu_agg['Total_CD_LC'] = bu_agg['Total_CD_LC'].abs().round(2)

        # In a reversal group, the first offset account can belong to the
        # reversed entry. Keep the final account on the net transaction side.
        def effective_offset(group: pd.DataFrame) -> str:
            net_amount = group['Amt_Clean'].sum()
            if net_amount and (group['Amt_Clean'] < 0).any() and (group['Amt_Clean'] > 0).any():
                matching = group[group['Amt_Clean'].apply(np.sign) == np.sign(net_amount)]
                if not matching.empty:
                    return matching.iloc[-1]['Offset_Clean']
            return group.iloc[0]['Offset_Clean']

        offsets = bu_groups.apply(effective_offset, include_groups=False).rename('SAP_Offset_Account')
        bu_agg = bu_agg.drop(columns=['SAP_Offset_Account']).join(offsets, on='Ref_Clean')

        report("Aggregating sales records", 2, 5)
        # DB (Sales) aggregation
        df_db['Ref_Clean'] = df_db[db_ref].apply(clean_id)
        df_db_valid = df_db[df_db['Ref_Clean'] != ''].copy()
        df_db_valid['DocDate_Std'] = parse_date_series(df_db_valid[db_date], dayfirst=True) if db_date else 'Missing Date'
        df_db_valid['CardCode_Clean'] = df_db_valid[db_card].apply(clean_card) if db_card else ''
        df_db_valid['DB_BU_Clean'] = df_db_valid[db_unit].astype(str) if db_unit else ''
        df_db_valid['Taxable_Clean'] = df_db_valid[db_taxable].apply(clean_number) if db_taxable else 0.0

        db_agg = df_db_valid.groupby('Ref_Clean', as_index=False).agg({
            'DB_BU_Clean': 'first',
            'DocDate_Std': 'first',
            'CardCode_Clean': 'first',
            'Taxable_Clean': 'sum'
        }).rename(columns={
            'DB_BU_Clean': 'COGSCostingCode',
            'DocDate_Std': 'Sales_DocDate',
            'CardCode_Clean': 'Customer_Id',
            'Taxable_Clean': 'Total_Sales_Value'
        })

        report("Merging and computing variances", 3, 5)
        # Right Join: Target based on Sales records (drop extra SAP IDs)
        recon = pd.merge(bu_agg, db_agg, on='Ref_Clean', how='right').rename(columns={'Ref_Clean': ref_col_name})
        recon['Business_Unit'] = recon['Business_Unit'].fillna('Missing in SAP').replace('', 'Missing in SAP')
        recon['Total_CD_LC'] = recon['Total_CD_LC'].fillna(0.0)
        recon['Total_Sales_Value'] = recon['Total_Sales_Value'].fillna(0.0)
        recon['Posting_Date'] = recon['Posting_Date'].fillna('Missing in SAP')
        recon['Sales_DocDate'] = recon['Sales_DocDate'].fillna('Missing in Sales/DB')
        recon['SAP_Offset_Account'] = recon['SAP_Offset_Account'].fillna('Missing in SAP')
        recon['Customer_Id'] = recon['Customer_Id'].fillna('Missing in Sales/DB')

        # Code 2: Mapped SAP Code
        recon['Mapped_SAP_Code'] = recon['Customer_Id'].apply(self.customer_service.get_mapped_sap_code)

        # Variances and Matches
        recon['Amount_Variance'] = (recon['Total_CD_LC'] - recon['Total_Sales_Value']).round(2)
        recon['Abs_Variance'] = recon['Amount_Variance'].abs()

        recon['Amount_Match'] = recon['Abs_Variance'] <= 0.05
        recon['Date_Match'] = (
            (recon['Posting_Date'] == recon['Sales_DocDate'])
            & (recon['Posting_Date'] != 'Missing in SAP')
            & (recon['Sales_DocDate'] != 'Missing in Sales/DB')
        )

        # 2-Step Customer Match
        direct_match = (
            (recon['SAP_Offset_Account'] == recon['Customer_Id'])
            & (recon['SAP_Offset_Account'] != 'Missing in SAP')
        )
        mapped_match = (
            (recon['SAP_Offset_Account'] == recon['Mapped_SAP_Code'])
            & (recon['SAP_Offset_Account'] != 'Missing in SAP')
        )
        recon['Customer_Match'] = direct_match | mapped_match

        report("Computing reconciliation remarks", 4, 5)
        # Vectorised remarks using np.select — replaces slow apply(build_remarks, axis=1)
        missing_sap = (
            (recon['Posting_Date'] == 'Missing in SAP')
            | (recon['SAP_Offset_Account'] == 'Missing in SAP')
        )
        missing_db = (
            (recon['Sales_DocDate'] == 'Missing in Sales/DB')
            | (recon['Customer_Id'] == 'Missing in Sales/DB')
        )
        # Build individual issue flags for rows that have both SAP and DB
        has_both = ~missing_sap & ~missing_db
        amt_issue = has_both & ~recon['Amount_Match']
        date_issue = has_both & ~recon['Date_Match']
        cust_issue = has_both & ~recon['Customer_Match']

        # Format variance string for amount issues
        var_str = recon['Amount_Variance'].map(lambda v: f"Amount Variance ({v})")
        date_str = ("Date Mismatch (" + recon['Posting_Date'].astype(str) + " vs " + recon['Sales_DocDate'].astype(str) + ")")
        cust_str = ("Customer Mismatch (SAP: " + recon['SAP_Offset_Account'].astype(str)
                    + " vs DB: " + recon['Customer_Id'].astype(str)
                    + " [Mapped: " + recon['Mapped_SAP_Code'].astype(str) + "])")

        # Build remarks by concatenating active issue strings per row
        remarks_parts = pd.DataFrame({
            'amt': np.where(amt_issue, var_str, ''),
            'date': np.where(date_issue, date_str, ''),
            'cust': np.where(cust_issue, cust_str, ''),
        })
        combined_issues = remarks_parts.apply(
            lambda r: ' | '.join(x for x in [r['amt'], r['date'], r['cust']] if x), axis=1
        )

        conditions = [
            missing_sap,
            missing_db,
            has_both & (amt_issue | date_issue | cust_issue),
        ]
        choices = [
            'MISMATCHED: Missing in SAP',
            'MISMATCHED: Missing in Sales/DB',
            'MISMATCHED: ' + combined_issues,
        ]
        recon['Reconciliation_Remarks'] = np.select(conditions, choices, default='MATCHED')
        recon['Overall_Status'] = np.where(
            recon['Reconciliation_Remarks'].str.startswith('MATCHED'),
            'Matched',
            'Not Matched',
        )
        recon['Format_Used'] = format_label

        report("Sales reconciliation complete", 5, 5)
        cols = [
            'Business_Unit', ref_col_name,
            'Total_CD_LC', 'Total_Sales_Value', 'Amount_Variance',
            'Posting_Date', 'Sales_DocDate',
            'Customer_Id', 'Mapped_SAP_Code', 'SAP_Offset_Account',
            'Overall_Status', 'Reconciliation_Remarks', 'Format_Used'
        ]
        return recon[cols].copy()


# ---------------------------------------------------------------------------
# Functional convenience wrappers for compatibility
# ---------------------------------------------------------------------------

def reconcile_dataframes(
    df_bu_raw: pd.DataFrame,
    df_db_raw: pd.DataFrame,
    mode: str = "Auto",
    cust_map: Optional[Union[Dict[str, str], CustomerMappingService]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> pd.DataFrame:
    if isinstance(cust_map, dict):
        cust_service = CustomerMappingService(cust_map)
    elif isinstance(cust_map, CustomerMappingService):
        cust_service = cust_map
    else:
        cust_service = CustomerMappingService.load_from_sources()

    engine = ReconciliationEngine(mode=mode, customer_service=cust_service)
    return engine.reconcile(df_bu_raw, df_db_raw, progress_callback=progress_callback)


def process_single_file(
    file_path: str,
    mode: str = "Auto",
    cust_map: Optional[Union[Dict[str, str], CustomerMappingService]] = None,
) -> pd.DataFrame:
    df_bu, df_db = read_file_tables(file_path)
    return reconcile_dataframes(df_bu, df_db, mode=mode, cust_map=cust_map)


def process_file_list(
    files: List[str],
    mode: str = "Auto",
    recon_model: str = "Auto",
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    cancel_event: Optional[Event] = None,
) -> pd.DataFrame:
    """Process a list of files, routing to Sales and/or Collection reconciliation.

    Args:
        files: Paths to all input files (SAP ledgers, sales DB exports, bank statements,
               optional customer mapping file).
        mode: Format hint passed to reconcile_dataframes ('Auto', 'Format 1 ...', 'Format 2 ...').
        recon_model: 'Sales Reconciliation', 'Collection Reconciliation', 'Both (Combined)',
                     or 'Auto' (inferred from detected file types).
        progress_callback: Optional (stage, current, total) callable for progress reporting.
        cancel_event: Optional threading.Event; set it to cancel mid-run.
    """
    def report(stage: str, current: int = 0, total: int = 0) -> None:
        if progress_callback:
            progress_callback(stage, current, total)

    def check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Reconciliation cancelled by user")

    def label_result(result: pd.DataFrame, recon_type: str) -> pd.DataFrame:
        result = result.copy()
        result.insert(0, "Recon_Type", recon_type)
        return result

    # ------------------------------------------------------------------
    # Step 1: Filter out temp / mapping files
    # ------------------------------------------------------------------
    report("Preparing input files", 0, len(files))
    data_files: List[str] = []
    for f in files:
        fname = os.path.basename(f).lower()
        if fname.startswith('~$'):
            continue
        if fname in {
            'reconciliation_summary_report.xlsx',
            'debug_reconciliation_output.xlsx',
        }:
            continue
        if 'customer' in fname and ('id' in fname or 'code' in fname or 'map' in fname):
            continue
        data_files.append(f)

    if not data_files:
        data_files = list(files)

    # ------------------------------------------------------------------
    # Step 2: Parallel file I/O — read every file exactly once
    # ------------------------------------------------------------------
    total_files = len(data_files)
    report("Reading files (parallel)", 0, total_files)
    parsed: List[tuple] = [None] * total_files  # type: ignore[assignment]
    completed = [0]

    def _read(idx_path):
        idx, path = idx_path
        frame, _ = read_file_tables(path)  # cache hit on 2nd call
        return idx, path, frame

    with ThreadPoolExecutor(max_workers=min(4, total_files or 1)) as executor:
        futures = {executor.submit(_read, (i, p)): i for i, p in enumerate(data_files)}
        for future in as_completed(futures):
            check_cancelled()
            idx, path, frame = future.result()
            parsed[idx] = (path, frame)
            completed[0] += 1
            report("Reading files (parallel)", completed[0], total_files)

    # ------------------------------------------------------------------
    # Step 3: Classify files
    # ------------------------------------------------------------------
    sap_files = [(p, f) for p, f in parsed if is_sap_table(f)]
    bank_files = [(p, f) for p, f in parsed if not is_sap_table(f) and is_bank_table(f)]
    sales_files = [(p, f) for p, f in parsed if not is_sap_table(f) and not is_bank_table(f)]

    # ------------------------------------------------------------------
    # Step 4: Resolve recon_model
    # ------------------------------------------------------------------
    if recon_model == "Auto":
        if bank_files and sales_files:
            recon_model = "Both (Combined)"
        elif bank_files:
            recon_model = "Collection Reconciliation"
        else:
            recon_model = "Sales Reconciliation"

    use_sales = recon_model in ("Sales Reconciliation", "Both (Combined)")
    use_collection = recon_model in ("Collection Reconciliation", "Both (Combined)")

    def is_sales_sap_file(path: str) -> bool:
        fn = os.path.basename(path).lower()
        return bool(re.search(r'^(402|401|sales)', fn) or '4020101' in fn or '401' in fn)

    def is_bank_sap_file(path: str) -> bool:
        fn = os.path.basename(path).lower()
        return bool(re.search(r'^(101|account balance|bank|icici|scb)', fn) or '1010202' in fn or 'account balance' in fn)

    sales_sap_frames = [f for p, f in sap_files if is_sales_sap_file(p)]
    if not sales_sap_frames:
        sales_sap_frames = [f for _, f in sap_files]

    bank_sap_frames = [f for p, f in sap_files if is_bank_sap_file(p)]
    if not bank_sap_frames:
        bank_sap_frames = [f for _, f in sap_files]

    cust_service = CustomerMappingService.load_from_sources(files)
    results: List[pd.DataFrame] = []

    # ------------------------------------------------------------------
    # Step 5: Sales reconciliation
    # ------------------------------------------------------------------
    if use_sales and sap_files:
        check_cancelled()
        sales_sap = pd.concat(sales_sap_frames, ignore_index=True)
        if sales_files:
            # Keep different sales export schemas separate. Concatenating an
            # invoice export with a RefId export creates null columns and lets
            # one format's detector hide the other format's records.
            sales_groups: Dict[str, List[pd.DataFrame]] = {}
            for _, sales_frame in sales_files:
                frame_format = detect_format(sales_sap, sales_frame, mode)
                sales_groups.setdefault(frame_format, []).append(sales_frame)
        else:
            # Fall back: treat the second parsed frame of any 2-file set as the DB side
            if len(parsed) == 2:
                other = parsed[1][1] if is_sap_table(parsed[0][1]) else parsed[0][1]
                sales_groups = {detect_format(sales_sap, other, mode): [other]}
            else:
                sales_groups = {}

        total_sales_groups = len(sales_groups)
        for group_index, grouped_frames in enumerate(sales_groups.values(), 1):
            check_cancelled()
            sales_db = pd.concat(grouped_frames, ignore_index=True)
            if sales_db.empty:
                continue
            report("Reconciling sales records", group_index - 1, total_sales_groups)
            result = reconcile_dataframes(
                sales_sap,
                sales_db,
                mode=mode,
                cust_map=cust_service,
                progress_callback=progress_callback,
            )
            results.append(label_result(result, "Sales"))
            report("Reconciling sales records", group_index, total_sales_groups)

    # ------------------------------------------------------------------
    # Step 6: Collection reconciliation
    # ------------------------------------------------------------------
    if use_collection and sap_files and bank_files:
        sap_frame = pd.concat(bank_sap_frames, ignore_index=True)
        for index, (bank_file, bank_frame) in enumerate(bank_files, 1):
            check_cancelled()
            bank_type = detect_bank_type(bank_frame) or "Bank"
            # For CMS, don't use the extracted account_number from ZIP metadata (unreliable).
            # Only use it for other bank types like ICICI, SCB, PNB.
            account_number = "" if bank_type and bank_type.upper() == "CMS" else bank_frame.attrs.get('account_number', '')
            result = reconcile_bank_to_sap(
                bank_frame,
                sap_frame,
                bank_type,
                account_number,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
            result['Source_File'] = (
                f"{os.path.basename(bank_file)} + {len(bank_sap_frames)} SAP ledger(s)"
            )
            results.append(label_result(result, "Collection"))
            report("Reconciling collection records", index, len(bank_files))

    if results:
        combined = pd.concat(results, ignore_index=True, sort=False)
        if sales_sap_frames and use_sales:
            combined.attrs['raw_sales_sap'] = pd.concat(sales_sap_frames, ignore_index=True)
        if sales_files and use_sales:
            combined.attrs['raw_sales_db'] = pd.concat([f for _, f in sales_files], ignore_index=True)
        if bank_sap_frames and use_collection:
            combined.attrs['raw_collection_sap'] = pd.concat(bank_sap_frames, ignore_index=True)
        if bank_files and use_collection:
            combined.attrs['raw_collection_bank'] = pd.concat([f for _, f in bank_files], ignore_index=True)
        return combined

    # ------------------------------------------------------------------
    # Step 7: Last-resort 2-file fallback (single SAP + single other)
    # ------------------------------------------------------------------
    if len(parsed) == 2 and is_sap_table(parsed[0][1]) != is_sap_table(parsed[1][1]):
        first_path, first_frame = parsed[0]
        second_path, second_frame = parsed[1]
        sap_frame, other_frame = (
            (first_frame, second_frame) if is_sap_table(first_frame) else (second_frame, first_frame)
        )
        result = reconcile_dataframes(sap_frame, other_frame, mode=mode, cust_map=cust_service)
        result['Source_File'] = (
            f"{os.path.basename(first_path)} + {os.path.basename(second_path)}"
        )
        result.attrs['raw_sales_sap'] = sap_frame
        result.attrs['raw_sales_db'] = other_frame
        return label_result(result, "Sales")

    return pd.DataFrame()
