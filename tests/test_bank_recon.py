"""Tests for ICICI and SCB bank-to-SAP collection reconciliation."""
import io
import zipfile
from pathlib import Path

import pandas as pd

from src.readers.file_reader import read_file_tables
from src.services.bank_recon import extract_scb_utr, reconcile_bank_to_sap


def test_extract_scb_utr_from_description():
    assert extract_scb_utr("NEFT|UTR12345 25/08/26") == "UTR12345"
    assert extract_scb_utr("TRANSFER/SCB9988 25/08/26") == "SCB9988"
    assert extract_scb_utr("TRANSFER|PART1/PART2 25/08/26") == "PART1"


def test_icici_matches_transaction_id_and_amount():
    bank = pd.DataFrame({
        "Transaction ID": ["ICICI-UTR-1001"],
        "Description": ["Collection"],
        "Deposit Amt (INR)": [1000.00]
    })
    bank.attrs['account_number'] = '107505004792'
    sap = pd.DataFrame({
        "Details": ["ICICI-UTR-1001"],
        "Offset Account": ["CUST_OFFSET_999"],
        "Origin No.": ["9001"],
        "C/D (LC)": [-1000.00]
    })

    result = reconcile_bank_to_sap(bank, sap, "ICICI")
    assert result.loc[0, "Overall_Status"] == "Matched"
    assert result.loc[0, "Amount_Variance"] == 0.0
    assert result.loc[0, "Bank_Account_Number"] == "ICICI - 107505004792"
    assert result.loc[0, "SAP_Offset_Account"] == "CUST_OFFSET_999"


def test_collection_reconciliation_captures_offset_account():
    bank = pd.DataFrame({
        "Transaction ID": ["UTR-OFFSET-1", "UTR-OFFSET-2"],
        "Deposit Amt (INR)": [500.00, 800.00]
    })
    sap = pd.DataFrame({
        "Details": ["UTR-OFFSET-1"],
        "Offset Account": ["ACCOUNT_ABC"],
        "C/D (LC)": [-500.00]
    })
    result = reconcile_bank_to_sap(bank, sap, "ICICI")
    assert result.loc[0, "SAP_Offset_Account"] == "ACCOUNT_ABC"
    assert result.loc[1, "SAP_Offset_Account"] == "Missing in SAP"


def test_scb_resolves_reversal_and_reports_amount_mismatch():
    bank = pd.DataFrame({
        "Description": ["NEFT|SCB-UTR-2002 25/08/26"],
        "Deposit Amt (INR)": [900.00]
    })
    sap = pd.DataFrame({
        "Details": ["", "SCB-UTR-2002"],
        "Origin No.": ["9002", "9002"],
        "C/D (LC)": [-1000.00, 1000.00]
    })

    result = reconcile_bank_to_sap(bank, sap, "SCB")
    assert result.loc[0, "Overall_Status"] == "Not Matched"
    assert result.loc[0, "Amount_Variance"] == -100.0
    assert "Amount variance" in result.loc[0, "Reconciliation_Remarks"]
    assert "Origin No." in result.loc[0, "Reconciliation_Remarks"]


def test_collection_ignores_non_deposit_rows():
    bank = pd.DataFrame({
        "Transaction ID": ["UTR-1", "UTR-2"],
        "Description": ["Deposit", "Withdrawal"],
        "Deposit Amt (INR)": [500.00, None]
    })
    sap = pd.DataFrame({"Details": ["UTR-1"], "C/D (LC)": [-500.00]})

    result = reconcile_bank_to_sap(bank, sap, "ICICI")
    assert len(result) == 1
    assert result.loc[0, "Bank_Amount"] == 500.00


def test_duplicate_sap_utr_prefers_matching_amount():
    bank = pd.DataFrame({
        "Description": ["NEFT/UTR-1"],
        "Deposit": [900.00]
    })
    sap = pd.DataFrame({
        "Details": ["UTR-1", "UTR-1"],
        "Posting Date": ["2026-08-25", "2026-08-25"],
        "C/D (LC)": [1000.00, 900.00]
    })

    result = reconcile_bank_to_sap(bank, sap, "SCB")
    assert result.loc[0, "SAP_Amount"] == 900.00
    assert result.loc[0, "Overall_Status"] == "Matched"


def test_multiple_sap_rows_can_form_bank_amount():
    bank = pd.DataFrame({"Transaction ID": ["UTR-2"], "Description": ["NEFT/UTR-2"], "Deposit": [300.00]})
    sap = pd.DataFrame({
        "Details": ["UTR-2", "UTR-2", "UTR-2"],
        "Posting Date": ["2026-08-25"] * 3,
        "C/D (LC)": [100.00, 200.00, 500.00]
    })

    result = reconcile_bank_to_sap(bank, sap, "SCB")
    assert result.loc[0, "SAP_Amount"] == 300.00
    assert result.loc[0, "Overall_Status"] == "Matched"


def test_paynearby_pnb_filters_success_omni_rows_and_matches_utr_amount_and_date():
    bank = pd.DataFrame({
        "PNBTransactionID": ["CC1001", "CC1002", "CC1003"],
        "Business Type": ["Omni Channel", "FnV", "Omni Channel"],
        "Txn Status": ["Success", "Success", "Fail"],
        "Amount": [500.00, 700.00, 900.00],
        "Txn Date": ["2026-07-30", "2026-07-30", "2026-07-30"],
    })
    sap = pd.DataFrame({
        "Details": ["CC1001", "CC1001"],
        "Posting Date": ["2026-07-30", "2026-07-30"],
        "C/D (LC)": [-500.00, 0.00],
    })

    result = reconcile_bank_to_sap(bank, sap, "PNB")

    assert len(result) == 1
    assert result.loc[0, "Bank_UTR"] == "CC1001"
    assert result.loc[0, "Bank_Account_Number"] == "PNB_CCA_Account"
    assert result.loc[0, "Overall_Status"] == "Matched"
    assert result.loc[0, "Amount_Variance"] == 0.0


def test_zip_archive_with_csv_table_is_supported(tmp_path):
    zip_path = tmp_path / "statement.zip"
    csv_payload = "Account Number,TransactionID,Deno Total,ActionDate\n107505004797,CMSUTR12345,2500,2026-08-20\n"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GenericReport_1748731_010926162632.csv", csv_payload)

    df_bu, df_db = read_file_tables(str(zip_path))

    assert not df_bu.empty
    assert df_bu.columns.tolist()[0] == "Account Number"
    assert "CMSUTR12345" in str(df_bu.iloc[0].to_dict())


def test_cms_matches_transaction_id_amount_and_date_and_labels_account():
    bank = pd.DataFrame({
        "Account Number": ["107505004797"],
        "TransactionID": ["CMSUTR12345"],
        "Deno Total": [2500.00],
        "ActionDate": ["2026-08-20"],
    })
    bank.attrs['account_number'] = '107505004797'
    sap = pd.DataFrame({
        "Details": ["CMSUTR12345"],
        "Posting Date": ["2026-08-20"],
        "C/D (LC)": [-2500.00],
    })

    result = reconcile_bank_to_sap(bank, sap, "CMS")

    assert result.loc[0, "Bank_UTR"] == "CMSUTR12345"
    assert result.loc[0, "Bank_Account_Number"] == "CMS_CCA_Account"
    assert result.loc[0, "Overall_Status"] == "Matched"
    assert result.loc[0, "Amount_Variance"] == 0.0


def test_real_cms_zip_and_ledger_produce_matched_results():
    bank_path = Path("test_data/omni&farmer/collection/GenericReport_63IDEAS03_010926162632.zip")
    sap_path = Path("test_data/omni&farmer/collection/Account Balance - 1010204012, CMS - Omnichannel.xls")

    bank_df, _ = read_file_tables(str(bank_path))
    sap_df, _ = read_file_tables(str(sap_path))

    result = reconcile_bank_to_sap(bank_df, sap_df, "CMS")

    assert not result.empty
    assert "Matched" in result["Overall_Status"].unique()
    assert result["Bank_Name"].eq("CMS").all()
    assert result["Bank_UTR"].notna().any()