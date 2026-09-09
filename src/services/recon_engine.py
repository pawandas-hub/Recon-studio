"""Reconciliation Engine implementing Format 1 (Standard) and Format 2 (Retailer/FnV) algorithms."""
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from typing import Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from ..core.cleaners import (
    clean_id, clean_afc_id, clean_card, clean_number, clean_signed_number,
    clean_number_series, clean_signed_number_series, parse_date_series
)
from ..core.constants import FORMAT1_BU_COLS, FORMAT1_DB_COLS, FORMAT2_BU_COLS, FORMAT2_DB_COLS, FORMAT3_BU_COLS, FORMAT3_DB_COLS
from ..core.detector import find_best_col, detect_format, is_sap_table
from ..readers.file_reader import read_file_tables
from .customer_service import CustomerMappingService
from .bank_recon import reconcile_bank_to_sap, detect_bank_type, is_bank_table


def _vectorized_join_remarks(parts: List[Union[pd.Series, np.ndarray]], index: pd.Index, sep: str = ' | ') -> pd.Series:
    """Vectorized string joining of non-empty remarks parts."""
    if not parts:
        return pd.Series('', index=index, dtype=str)
    res = pd.Series('', index=index, dtype=str)
    for p in parts:
        p_s = pd.Series(p, index=index, dtype=str) if not isinstance(p, pd.Series) else p
        has_res = res != ''
        has_p = p_s != ''
        combined = np.where(has_res & has_p, res + sep + p_s, np.where(has_p, p_s, res))
        res = pd.Series(combined, index=index, dtype=str)
    return res


def compute_effective_offsets(df_bu_valid: pd.DataFrame) -> pd.Series:
    """Fast vectorized effective offset computation for SAP ledger groups.

    For 99.5%+ single-row or single-sign groups, the first offset account is used.
    For groups with mixed positive and negative rows (reversals), the offset from
    the final transaction matching the net group sign is selected.
    """
    if df_bu_valid.empty:
        return pd.Series(dtype=str, name='SAP_Offset_Account')

    bu_agg_offsets = df_bu_valid.groupby('Ref_Clean', sort=False)['Offset_Clean'].first()

    has_pos = df_bu_valid['Amt_Clean'] > 0
    has_neg = df_bu_valid['Amt_Clean'] < 0
    pos_refs = set(df_bu_valid.loc[has_pos, 'Ref_Clean'])
    neg_refs = set(df_bu_valid.loc[has_neg, 'Ref_Clean'])
    mixed_refs = pos_refs.intersection(neg_refs)

    if mixed_refs:
        mixed_df = df_bu_valid[df_bu_valid['Ref_Clean'].isin(mixed_refs)]
        net_amounts = mixed_df.groupby('Ref_Clean', sort=False)['Amt_Clean'].sum()
        active_net = net_amounts[net_amounts != 0]
        if not active_net.empty:
            net_signs = np.sign(active_net).rename('Net_Sign')
            m_rows = mixed_df.merge(net_signs, on='Ref_Clean')
            m_matching = m_rows[np.sign(m_rows['Amt_Clean']) == m_rows['Net_Sign']]
            if not m_matching.empty:
                special_offsets = m_matching.groupby('Ref_Clean', sort=False)['Offset_Clean'].last()
                bu_agg_offsets.update(special_offsets)

    return bu_agg_offsets.rename('SAP_Offset_Account')


class ReconciliationEngine:
    """Core engine to aggregate, match, and reconcile SAP and Sales/DB dataframes."""

    def __init__(self, mode: str = "Auto", customer_service: Optional[CustomerMappingService] = None):
        self.mode = mode
        self.customer_service = customer_service or CustomerMappingService.load_from_sources()

    def reconcile(
        self,
        df_bu_raw: pd.DataFrame,
        df_db_raw: pd.DataFrame,
        df_freight_sap_raw: Optional[pd.DataFrame] = None,
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

        if fmt == "format3":
            return self._reconcile_format3(df_bu, df_db, df_freight_sap_raw, report)

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
        df_bu_valid['PostingDate_Std'] = parse_date_series(df_bu_valid[bu_date], dayfirst=True, missing_label='Missing in SAP') if bu_date else 'Missing in SAP'
        df_bu_valid['Offset_Clean'] = df_bu_valid[bu_acc].apply(clean_card) if bu_acc else ''
        df_bu_valid['BU_Clean'] = df_bu_valid[bu_unit].astype(str) if bu_unit else 'Default_BU'
        # Net debit/credit lines before taking the absolute ledger total.
        # Taking abs() per row incorrectly doubles reversal entries.
        df_bu_valid['Amt_Clean'] = (
            clean_signed_number_series(df_bu_valid[bu_amt]) if bu_amt else 0.0
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

        offsets = compute_effective_offsets(df_bu_valid)
        bu_agg = bu_agg.drop(columns=['SAP_Offset_Account']).join(offsets, on='Ref_Clean')

        report("Aggregating sales records", 2, 5)
        # DB (Sales) aggregation
        df_db['Ref_Clean'] = df_db[db_ref].apply(clean_id)
        df_db_valid = df_db[df_db['Ref_Clean'] != ''].copy()
        df_db_valid['DocDate_Std'] = parse_date_series(df_db_valid[db_date], dayfirst=True, missing_label='Missing in Sales/DB') if db_date else 'Missing in Sales/DB'
        df_db_valid['CardCode_Clean'] = df_db_valid[db_card].apply(clean_card) if db_card else ''
        df_db_valid['DB_BU_Clean'] = df_db_valid[db_unit].astype(str) if db_unit else ''
        df_db_valid['Taxable_Clean'] = clean_number_series(df_db_valid[db_taxable]) if db_taxable else 0.0

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

        has_issues = amt_issue | date_issue | cust_issue
        combined_issues = pd.Series('', index=recon.index)
        if has_issues.any():
            part_amt = np.where(amt_issue, var_str, '')
            part_date = np.where(date_issue, date_str, '')
            part_cust = np.where(cust_issue, cust_str, '')
            combined_issues = _vectorized_join_remarks([part_amt, part_date, part_cust], recon.index)

        conditions = [
            missing_sap,
            missing_db,
            has_both & has_issues,
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

    def _reconcile_format3(
        self,
        df_bu: pd.DataFrame,
        df_db: pd.DataFrame,
        df_freight_sap: Optional[pd.DataFrame],
        report: Callable[[str, int, int], None],
    ) -> pd.DataFrame:
        bu_cols = FORMAT3_BU_COLS
        db_cols = FORMAT3_DB_COLS
        format_label = 'Format 3 (AFC / Sales with Freight & GRN)'
        ref_col_name = 'InvoiceId'

        report("Finding Format 3 column mappings", 0, 5)
        bu_ref = find_best_col(df_bu, bu_cols['ref']) or df_bu.columns[0]
        bu_grn = find_best_col(df_bu, bu_cols['grn'])
        bu_date = find_best_col(df_bu, bu_cols['date'])
        bu_amt = find_best_col(df_bu, bu_cols['amt'])
        bu_acc = find_best_col(df_bu, bu_cols['acc'])
        bu_unit = find_best_col(df_bu, bu_cols['unit'])

        db_ref = find_best_col(df_db, db_cols['ref']) or df_db.columns[0]
        db_grn = find_best_col(df_db, db_cols['grn'])
        db_date = find_best_col(df_db, db_cols['date'])
        db_card = find_best_col(df_db, db_cols['card'])
        db_unit = find_best_col(df_db, db_cols['unit'])

        # DB Amount breakdown columns
        db_sales_col = find_best_col(df_db, db_cols['sales'])
        db_disc_col = find_best_col(df_db, db_cols['discount'])
        db_upi_col = find_best_col(df_db, db_cols['upi_discount'])
        db_wallet_col = find_best_col(df_db, db_cols['wallet_discount'])
        db_packing_col = find_best_col(df_db, db_cols['packing'])
        db_freight_col = find_best_col(df_db, db_cols['freight'])

        report("Aggregating SAP sales ledger (AFC normalized)", 1, 5)
        df_bu['Ref_Clean'] = df_bu[bu_ref].apply(clean_afc_id)
        df_bu_valid = df_bu[df_bu['Ref_Clean'] != ''].copy()
        df_bu_valid['PostingDate_Std'] = parse_date_series(df_bu_valid[bu_date], dayfirst=True, missing_label='Missing in SAP') if bu_date else 'Missing in SAP'
        df_bu_valid['Offset_Clean'] = df_bu_valid[bu_acc].apply(clean_card) if bu_acc else ''
        df_bu_valid['BU_Clean'] = df_bu_valid[bu_unit].astype(str) if bu_unit else 'Default_BU'
        df_bu_valid['SAP_GRN_Clean'] = df_bu_valid[bu_grn].apply(clean_id) if bu_grn else ''
        df_bu_valid['Amt_Clean'] = clean_signed_number_series(df_bu_valid[bu_amt]) if bu_amt else 0.0

        bu_groups = df_bu_valid.groupby('Ref_Clean', sort=False)
        bu_agg = bu_groups.agg({
            'BU_Clean': 'first',
            'PostingDate_Std': 'first',
            'Offset_Clean': 'first',
            'SAP_GRN_Clean': 'first',
            'Amt_Clean': 'sum'
        }).rename(columns={
            'BU_Clean': 'Business_Unit',
            'PostingDate_Std': 'Posting_Date',
            'Offset_Clean': 'SAP_Offset_Account',
            'SAP_GRN_Clean': 'SAP_GRN_ID',
            'Amt_Clean': 'Total_CD_LC'
        })
        bu_agg['Total_CD_LC'] = bu_agg['Total_CD_LC'].abs().round(2)

        offsets = compute_effective_offsets(df_bu_valid)
        bu_agg = bu_agg.drop(columns=['SAP_Offset_Account']).join(offsets, on='Ref_Clean')

        report("Aggregating sales DB records & calculating net sales", 2, 5)
        df_db['Ref_Clean'] = df_db[db_ref].apply(clean_afc_id)
        df_db_valid = df_db[df_db['Ref_Clean'] != ''].copy()
        df_db_valid['DocDate_Std'] = parse_date_series(df_db_valid[db_date], dayfirst=True, missing_label='Missing in Sales/DB') if db_date else 'Missing in Sales/DB'
        df_db_valid['CardCode_Clean'] = df_db_valid[db_card].apply(clean_card) if db_card else ''
        df_db_valid['DB_BU_Clean'] = df_db_valid[db_unit].astype(str) if db_unit else ''
        df_db_valid['DB_GRN_Clean'] = df_db_valid[db_grn].apply(clean_id) if db_grn else ''

        # Calculate DB Net Sales: sales - (Discounts + UPI_Discount + Wallet_Discount + packingcharges)
        s_val = clean_number_series(df_db_valid[db_sales_col]) if db_sales_col else 0.0
        disc_val = clean_number_series(df_db_valid[db_disc_col]) if db_disc_col else 0.0
        upi_val = clean_number_series(df_db_valid[db_upi_col]) if db_upi_col else 0.0
        wallet_val = clean_number_series(df_db_valid[db_wallet_col]) if db_wallet_col else 0.0
        pack_val = clean_number_series(df_db_valid[db_packing_col]) if db_packing_col else 0.0
        freight_val = clean_number_series(df_db_valid[db_freight_col]) if db_freight_col else 0.0

        df_db_valid['Net_Sales_Clean'] = (s_val - (disc_val + upi_val + wallet_val + pack_val)).round(2)
        df_db_valid['DB_Freight_Clean'] = freight_val.round(2)

        db_agg = df_db_valid.groupby('Ref_Clean', as_index=False).agg({
            'DB_BU_Clean': 'first',
            'DocDate_Std': 'first',
            'CardCode_Clean': 'first',
            'DB_GRN_Clean': 'first',
            'Net_Sales_Clean': 'sum',
            'DB_Freight_Clean': 'sum',
        }).rename(columns={
            'DB_BU_Clean': 'COGSCostingCode',
            'DocDate_Std': 'Sales_DocDate',
            'CardCode_Clean': 'Customer_Id',
            'DB_GRN_Clean': 'DB_GRN_ID',
            'Net_Sales_Clean': 'Total_Sales_Value',
            'DB_Freight_Clean': 'DB_Freight_Amount',
        })
        db_agg['Total_Sales_Value'] = db_agg['Total_Sales_Value'].round(2)
        db_agg['DB_Freight_Amount'] = db_agg['DB_Freight_Amount'].round(2)

        report("Processing Freight SAP ledger (4020101013)", 3, 5)
        if df_freight_sap is not None and not df_freight_sap.empty:
            df_fr = df_freight_sap.copy()
            df_fr.columns = [str(c).replace('\n', ' ').strip() for c in df_fr.columns]
            fr_ref = find_best_col(df_fr, bu_cols['ref']) or df_fr.columns[0]
            fr_amt = find_best_col(df_fr, bu_cols['amt'])
            df_fr['Ref_Clean'] = df_fr[fr_ref].apply(clean_afc_id)
            df_fr_valid = df_fr[df_fr['Ref_Clean'] != ''].copy()
            df_fr_valid['Amt_Clean'] = clean_signed_number_series(df_fr_valid[fr_amt]) if fr_amt else 0.0
            fr_agg = df_fr_valid.groupby('Ref_Clean', as_index=False).agg({
                'Amt_Clean': 'sum'
            }).rename(columns={'Amt_Clean': 'SAP_Freight_Amount'})
            fr_agg['SAP_Freight_Amount'] = fr_agg['SAP_Freight_Amount'].abs().round(2)
        else:
            fr_agg = pd.DataFrame(columns=['Ref_Clean', 'SAP_Freight_Amount'])

        report("Merging records and computing 5-way reconciliation", 4, 5)
        recon = pd.merge(bu_agg, db_agg, on='Ref_Clean', how='right')
        if not fr_agg.empty:
            recon = pd.merge(recon, fr_agg, on='Ref_Clean', how='left')
        else:
            recon['SAP_Freight_Amount'] = 0.0

        recon = recon.rename(columns={'Ref_Clean': ref_col_name})

        # Fill missing values
        recon['Business_Unit'] = recon['Business_Unit'].fillna('Missing in SAP').replace('', 'Missing in SAP')
        recon['Total_CD_LC'] = recon['Total_CD_LC'].fillna(0.0)
        recon['Total_Sales_Value'] = recon['Total_Sales_Value'].fillna(0.0)
        recon['SAP_Freight_Amount'] = recon['SAP_Freight_Amount'].fillna(0.0)
        recon['DB_Freight_Amount'] = recon['DB_Freight_Amount'].fillna(0.0)
        recon['Posting_Date'] = recon['Posting_Date'].fillna('Missing in SAP')
        recon['Sales_DocDate'] = recon['Sales_DocDate'].fillna('Missing in Sales/DB')
        recon['SAP_Offset_Account'] = recon['SAP_Offset_Account'].fillna('Missing in SAP')
        recon['Customer_Id'] = recon['Customer_Id'].fillna('Missing in Sales/DB')
        recon['SAP_GRN_ID'] = recon['SAP_GRN_ID'].fillna('')
        recon['DB_GRN_ID'] = recon['DB_GRN_ID'].fillna('')

        # Code mapping
        recon['Mapped_SAP_Code'] = recon['Customer_Id'].apply(self.customer_service.get_mapped_sap_code)

        # 1. Sales Amount Match
        recon['Amount_Variance'] = (recon['Total_CD_LC'] - recon['Total_Sales_Value']).round(2)
        recon['Amount_Match'] = recon['Amount_Variance'].abs() <= 1.0

        # 2. Date Match
        recon['Date_Match'] = (
            (recon['Posting_Date'] == recon['Sales_DocDate'])
            & (recon['Posting_Date'] != 'Missing in SAP')
            & (recon['Sales_DocDate'] != 'Missing in Sales/DB')
        )

        # 3. Customer Match (Exact or leading-zero normalized)
        sap_c = recon['SAP_Offset_Account'].astype(str).str.lstrip('0')
        db_c = recon['Customer_Id'].astype(str).str.lstrip('0')
        mapped_c = recon['Mapped_SAP_Code'].astype(str).str.lstrip('0')

        direct_match = (
            ((recon['SAP_Offset_Account'] == recon['Customer_Id']) | ((sap_c == db_c) & (sap_c != '')))
            & (recon['SAP_Offset_Account'] != 'Missing in SAP')
        )
        mapped_match = (
            ((recon['SAP_Offset_Account'] == recon['Mapped_SAP_Code']) | ((sap_c == mapped_c) & (sap_c != '')))
            & (recon['SAP_Offset_Account'] != 'Missing in SAP')
        )
        recon['Customer_Match'] = direct_match | mapped_match

        # 4. GRN Match
        recon['GRN_Match'] = (
            (recon['SAP_GRN_ID'] == recon['DB_GRN_ID'])
            & (recon['SAP_GRN_ID'] != '')
            & (recon['DB_GRN_ID'] != '')
        )

        # 5. Freight Match
        recon['Freight_Variance'] = (recon['SAP_Freight_Amount'] - recon['DB_Freight_Amount']).round(2)
        recon['Freight_Match'] = recon['Freight_Variance'].abs() <= 1.0

        # Build Remarks
        missing_sap = (
            (recon['Posting_Date'] == 'Missing in SAP')
            | (recon['SAP_Offset_Account'] == 'Missing in SAP')
        )
        missing_db = (
            (recon['Sales_DocDate'] == 'Missing in Sales/DB')
            | (recon['Customer_Id'] == 'Missing in Sales/DB')
        )
        has_both = ~missing_sap & ~missing_db

        amt_issue = has_both & ~recon['Amount_Match']
        date_issue = has_both & ~recon['Date_Match']
        cust_issue = has_both & ~recon['Customer_Match']
        grn_issue = has_both & ~recon['GRN_Match']
        has_any_freight = (recon['SAP_Freight_Amount'] > 0) | (recon['DB_Freight_Amount'] > 0)
        freight_issue = has_both & has_any_freight & ~recon['Freight_Match']

        var_str = recon['Amount_Variance'].map(lambda v: f"Amount Variance ({v})")
        date_str = ("Date Mismatch (" + recon['Posting_Date'].astype(str) + " vs " + recon['Sales_DocDate'].astype(str) + ")")
        cust_str = ("Customer Mismatch (SAP: " + recon['SAP_Offset_Account'].astype(str)
                    + " vs DB: " + recon['Customer_Id'].astype(str)
                    + " [Mapped: " + recon['Mapped_SAP_Code'].astype(str) + "])")
        grn_str = ("GRN Mismatch (SAP: " + recon['SAP_GRN_ID'].astype(str) + " vs DB: " + recon['DB_GRN_ID'].astype(str) + ")")
        fr_str = ("Freight Mismatch (SAP: " + recon['SAP_Freight_Amount'].astype(str) + " vs DB: " + recon['DB_Freight_Amount'].astype(str) + " [Var: " + recon['Freight_Variance'].astype(str) + "])")

        has_issues = amt_issue | date_issue | cust_issue | grn_issue | freight_issue
        combined_issues = pd.Series('', index=recon.index)
        if has_issues.any():
            part_amt = np.where(amt_issue, var_str, '')
            part_date = np.where(date_issue, date_str, '')
            part_cust = np.where(cust_issue, cust_str, '')
            part_grn = np.where(grn_issue, grn_str, '')
            part_fr = np.where(freight_issue, fr_str, '')
            combined_issues = _vectorized_join_remarks(
                [part_amt, part_date, part_cust, part_grn, part_fr],
                recon.index
            )

        has_issues = amt_issue | date_issue | cust_issue | grn_issue | freight_issue
        conditions = [
            missing_sap,
            missing_db,
            has_both & has_issues,
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

        report("Format 3 reconciliation complete", 5, 5)
        cols = [
            'Business_Unit', ref_col_name,
            'Total_CD_LC', 'Total_Sales_Value', 'Amount_Variance',
            'SAP_Freight_Amount', 'DB_Freight_Amount', 'Freight_Variance',
            'SAP_GRN_ID', 'DB_GRN_ID',
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
    df_freight_sap: Optional[pd.DataFrame] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> pd.DataFrame:
    if isinstance(cust_map, dict):
        cust_service = CustomerMappingService(cust_map)
    elif isinstance(cust_map, CustomerMappingService):
        cust_service = cust_map
    else:
        cust_service = CustomerMappingService.load_from_sources()

    engine = ReconciliationEngine(mode=mode, customer_service=cust_service)
    return engine.reconcile(df_bu_raw, df_db_raw, df_freight_sap_raw=df_freight_sap, progress_callback=progress_callback)


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

    def is_freight_sap_file(path: str) -> bool:
        fn = os.path.basename(path).lower()
        return '4020101013' in fn or 'freight' in fn

    def is_sales_sap_file(path: str) -> bool:
        if is_freight_sap_file(path):
            return False
        fn = os.path.basename(path).lower()
        return bool(re.search(r'^(402|401|sales)', fn) or '4020101' in fn or '401' in fn)

    def is_bank_sap_file(path: str) -> bool:
        fn = os.path.basename(path).lower()
        return bool(re.search(r'^(101|account balance|bank|icici|scb)', fn) or '1010202' in fn or 'account balance' in fn)

    freight_sap_frames = [f for p, f in sap_files if is_freight_sap_file(p)]
    freight_sap = pd.concat(freight_sap_frames, ignore_index=True) if freight_sap_frames else None

    sales_sap_frames = [f for p, f in sap_files if is_sales_sap_file(p)]
    if not sales_sap_frames:
        sales_sap_frames = [f for p, f in sap_files if not is_freight_sap_file(p)]
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

        # Check if freight GL account 4020101013 is embedded in sales_sap
        if freight_sap is None and not sales_sap.empty:
            acc_cols = [c for c in sales_sap.columns if any(k in re.sub(r'[\s_\-\(\)\/]+', '', str(c).lower()) for k in ['glaccount', 'account', 'glacc'])]
            for ac in acc_cols:
                mask = sales_sap[ac].astype(str).str.contains('4020101013', na=False)
                if mask.any():
                    freight_sap = sales_sap[mask].copy()
                    sales_sap = sales_sap[~mask].copy()
                    break

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
                df_freight_sap=freight_sap,
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
