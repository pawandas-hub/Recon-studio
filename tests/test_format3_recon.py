"""Unit and integration tests for Format 3 (AFC / Sales with Freight & GRN) Reconciliation."""
import os
import pandas as pd
import pytest

from src.core.cleaners import clean_afc_id
from src.core.detector import detect_format
from src.services.recon_engine import reconcile_dataframes, process_file_list


def test_clean_afc_id():
    """Verify clean_afc_id strips various AFC prefix patterns and normalizes IDs."""
    assert clean_afc_id("AFC1458247") == "1458247"
    assert clean_afc_id("afc-987654") == "987654"
    assert clean_afc_id("AFC_12345") == "12345"
    assert clean_afc_id("AFC 55555") == "55555"
    assert clean_afc_id("12345.0") == "12345"
    assert clean_afc_id("99999") == "99999"
    assert clean_afc_id(None) == ""
    assert clean_afc_id("") == ""


def test_detect_format_format3():
    """Verify detect_format identifies Format 3 accurately without affecting Format 1 or Format 2."""
    df_sap_afc = pd.DataFrame({
        'Ref. 2': ['AFC1001', 'AFC1002'],
        'Ref. 1': ['GRN1', 'GRN2'],
        'Deb./Cred. (LC)': [500.0, 600.0],
        'Offset Account': ['CU101', 'CU102'],
        'Posting Date': ['01/09/26', '02/09/26'],
    })

    df_db_f3 = pd.DataFrame({
        'InvoiceId': ['1001', '1002'],
        'GRNID': ['GRN1', 'GRN2'],
        'Sales': [600.0, 700.0],
        'Discounts': [50.0, 50.0],
        'UPI_Discount': [20.0, 20.0],
        'Wallet_Discount': [10.0, 10.0],
        'packingcharges': [20.0, 20.0],
        'CardCode': ['CU101', 'CU102'],
        'DocDate': ['2026-09-01', '2026-09-02'],
    })

    # Auto detect should return format3 because of GRNID and discounts
    assert detect_format(df_sap_afc, df_db_f3, mode="Auto") == "format3"

    # Explicit mode
    assert detect_format(df_sap_afc, df_db_f3, mode="Format 3 (AFC / Sales with Freight & GRN)") == "format3"

    # Preserves Format 1
    df_bu_f1 = pd.DataFrame({'Ref. 1': ['1001'], 'Posting Date': ['01/08/26'], 'C/D (LC)': [100.0], 'Offset Account': ['A1']})
    df_db_f1 = pd.DataFrame({'RefId': ['1001'], 'DocDate': ['01/08/26'], 'TAXABLEAMOUNT': [100.0], 'CardCode': ['A1']})
    assert detect_format(df_bu_f1, df_db_f1, mode="Auto") == "format1"

    # Preserves Format 2
    df_bu_f2 = pd.DataFrame({'Ref. 2': ['2001'], 'Posting Date': ['01/08/26'], 'C/D (LC)': [100.0], 'Offset Account': ['A1']})
    df_db_f2 = pd.DataFrame({'Invoice_Number': ['2001'], 'TotalValue_After_Disc': [100.0], 'Customer_Id': ['A1'], 'Invoice_Date': ['2026-08-01']})
    assert detect_format(df_bu_f2, df_db_f2, mode="Auto") == "format2"


def test_format3_reconciliation_all_matched():
    """Verify Format 3 matches all 5 criteria: Net Sales, Customer, Date, GRN, and Freight."""
    df_sap = pd.DataFrame({
        'Ref. 2': ['AFC1001', 'AFC1002'],
        'Ref. 1': ['GRN-555', 'GRN-666'],
        'Deb./Cred. (LC)': [-900.0, -1800.0],
        'Offset Account': ['DOM0000101', '102'],
        'Posting Date': ['01/09/26', '02/09/26'],
        'Business Unit': ['BU_Kolkata', 'BU_Kolkata'],
    })

    # Net sales:
    # 1001: 1000 - (50 + 20 + 10 + 20) = 900.0
    # 1002: 2000 - (100 + 40 + 30 + 30) = 1800.0
    df_db = pd.DataFrame({
        'InvoiceId': ['1001', 'AFC-1002'],
        'GRNID': ['GRN-555', 'GRN-666'],
        'Sales': [1000.0, 2000.0],
        'Discounts': [50.0, 100.0],
        'UPI_Discount': [20.0, 40.0],
        'Wallet_Discount': [10.0, 30.0],
        'packingcharges': [20.0, 30.0],
        'Freight': [150.0, 250.0],
        'CardCode': ['101', '102'],
        'DocDate': ['2026-09-01', '2026-09-02'],
    })

    df_freight_sap = pd.DataFrame({
        'Ref. 2': ['AFC1001', 'AFC1002'],
        'Deb./Cred. (LC)': [-150.0, -250.0],
    })

    recon = reconcile_dataframes(df_sap, df_db, mode="format3", df_freight_sap=df_freight_sap)

    assert len(recon) == 2
    assert (recon['Overall_Status'] == 'Matched').all()
    assert (recon['Reconciliation_Remarks'] == 'MATCHED').all()

    # Verify amounts
    row1 = recon[recon['InvoiceId'] == '1001'].iloc[0]
    assert row1['Total_CD_LC'] == 900.0
    assert row1['Total_Sales_Value'] == 900.0
    assert row1['Amount_Variance'] == 0.0
    assert row1['SAP_Freight_Amount'] == 150.0
    assert row1['DB_Freight_Amount'] == 150.0
    assert row1['Freight_Variance'] == 0.0
    assert row1['SAP_GRN_ID'] == '555'
    assert row1['DB_GRN_ID'] == '555'


def test_format3_reconciliation_individual_mismatches():
    """Verify that each individual mismatch (Amount, Date, Customer, GRN, Freight) is flagged correctly."""
    df_sap = pd.DataFrame({
        'Ref. 2': ['AFC101', 'AFC102', 'AFC103', 'AFC104', 'AFC105'],
        'Ref. 1': ['GRN-A',  'GRN-B',  'GRN-C',  'GRN-WRONG', 'GRN-E'],
        'Deb./Cred. (LC)': [-900.0,  -1000.0, -1000.0,  -1000.0,     -1000.0],
        'Offset Account': ['CU101',  'CU102', 'CU-DIFF', 'CU104',     'CU105'],
        'Posting Date': ['01/09/26', '01/09/26', '01/09/26', '01/09/26', '01/09/26'],
        'Business Unit': ['BU_1', 'BU_1', 'BU_1', 'BU_1', 'BU_1'],
    })

    df_db = pd.DataFrame({
        'InvoiceId': ['101', '102', '103', '104', '105'],
        'GRNID': ['GRN-A', 'GRN-B', 'GRN-C', 'GRN-CORRECT', 'GRN-E'],
        'Sales': [1000.0, 1000.0, 1000.0, 1000.0, 1000.0],
        'Discounts': [0.0, 0.0, 0.0, 0.0, 0.0],
        'UPI_Discount': [0.0, 0.0, 0.0, 0.0, 0.0],
        'Wallet_Discount': [0.0, 0.0, 0.0, 0.0, 0.0],
        'packingcharges': [0.0, 0.0, 0.0, 0.0, 0.0],
        'Freight': [100.0, 100.0, 100.0, 100.0, 500.0],
        'CardCode': ['101', '102', '999', '104', '105'],
        'DocDate': ['2026-09-01', '2026-09-15', '2026-09-01', '2026-09-01', '2026-09-01'],
    })

    df_freight = pd.DataFrame({
        'Ref. 2': ['AFC101', 'AFC102', 'AFC103', 'AFC104', 'AFC105'],
        'Deb./Cred. (LC)': [-100.0, -100.0, -100.0, -100.0, -100.0],
    })

    recon = reconcile_dataframes(df_sap, df_db, mode="format3", df_freight_sap=df_freight)

    # 101: Amount Mismatch (SAP: 900 vs DB: 1000)
    r101 = recon[recon['InvoiceId'] == '101'].iloc[0]
    assert r101['Overall_Status'] == 'Not Matched'
    assert 'Amount Variance' in r101['Reconciliation_Remarks']

    # 102: Date Mismatch (2026-09-01 vs 2026-09-15)
    r102 = recon[recon['InvoiceId'] == '102'].iloc[0]
    assert r102['Overall_Status'] == 'Not Matched'
    assert 'Date Mismatch' in r102['Reconciliation_Remarks']

    # 103: Customer Mismatch (CU-DIFF vs 999)
    r103 = recon[recon['InvoiceId'] == '103'].iloc[0]
    assert r103['Overall_Status'] == 'Not Matched'
    assert 'Customer Mismatch' in r103['Reconciliation_Remarks']

    # 104: GRN Mismatch (GRN-WRONG vs GRN-CORRECT)
    r104 = recon[recon['InvoiceId'] == '104'].iloc[0]
    assert r104['Overall_Status'] == 'Not Matched'
    assert 'GRN Mismatch' in r104['Reconciliation_Remarks']

    # 105: Freight Mismatch (SAP: 100 vs DB: 500)
    r105 = recon[recon['InvoiceId'] == '105'].iloc[0]
    assert r105['Overall_Status'] == 'Not Matched'
    assert 'Freight Mismatch' in r105['Reconciliation_Remarks']


def test_format3_end_to_end_process_file_list(tmp_path):
    """Verify process_file_list automatically separates 4020101013 freight file and reconciles Format 3."""
    sap_sales_csv = tmp_path / "4020101003_Sales.csv"
    sap_freight_csv = tmp_path / "4020101013_Freight.csv"
    db_sales_csv = tmp_path / "Sales_DB_Export.csv"

    df_sap_sales = pd.DataFrame({
        'Ref. 2': ['AFC2001'],
        'Ref. 1': ['GRN-777'],
        'Deb./Cred. (LC)': [-1500.0],
        'Offset Account': ['CU200'],
        'Posting Date': ['05/09/26'],
        'Business Unit': ['BU_Delhi'],
    })
    df_sap_freight = pd.DataFrame({
        'Ref. 2': ['AFC2001'],
        'Deb./Cred. (LC)': [-300.0],
    })
    df_db_sales = pd.DataFrame({
        'InvoiceId': ['2001'],
        'GRNID': ['GRN-777'],
        'Sales': [1800.0],
        'Discounts': [100.0],
        'UPI_Discount': [100.0],
        'Wallet_Discount': [50.0],
        'packingcharges': [50.0],
        'Freight': [300.0],
        'CardCode': ['200'],
        'DocDate': ['2026-09-05'],
    })

    df_sap_sales.to_csv(sap_sales_csv, index=False)
    df_sap_freight.to_csv(sap_freight_csv, index=False)
    df_db_sales.to_csv(db_sales_csv, index=False)

    files = [str(sap_sales_csv), str(sap_freight_csv), str(db_sales_csv)]
    results = process_file_list(files, mode="Auto")

    assert not results.empty
    assert len(results) == 1
    assert results.iloc[0]['Overall_Status'] == 'Matched'
    assert results.iloc[0]['Total_CD_LC'] == 1500.0
    assert results.iloc[0]['Total_Sales_Value'] == 1500.0
    assert results.iloc[0]['SAP_Freight_Amount'] == 300.0
    assert results.iloc[0]['DB_Freight_Amount'] == 300.0
    assert results.iloc[0]['Freight_Variance'] == 0.0


def test_format3_header_variations_and_empty_top_rows():
    """Verify that SAP headers with '(Header)' and empty row metadata are recognized accurately."""
    from src.readers.file_reader import _find_table_header
    from src.core.detector import find_best_col
    from src.core.constants import FORMAT3_BU_COLS

    # 1. Test header row finder with row 0 empty
    raw_df = pd.DataFrame([
        [None, None, None, None, None],
        ['Posting Date', 'Doc. No.', 'Trans. No.', 'Offset Acct', 'Deb./Cred. (LC)'],
        ['01/08/26', 'IN 100', '123', 'CUST01', 500.0]
    ])
    assert _find_table_header(raw_df) == 1

    # 2. Test column finder matching 'Ref. 2 (Header)' to 'Ref. 2' candidate
    sap_cols_df = pd.DataFrame(columns=[
        'Posting Date', 'Offset Acct', 'Deb./Cred. (LC)',
        'Ref. 1 (Header)', 'Ref. 2 (Header)', 'Ref. 3 (Header)'
    ])
    assert find_best_col(sap_cols_df, FORMAT3_BU_COLS['ref']) == 'Ref. 2 (Header)'
    assert find_best_col(sap_cols_df, FORMAT3_BU_COLS['grn']) == 'Ref. 1 (Header)'

