#!/usr/bin/env python
"""Inspect real CMS bank and SAP files."""
from src.readers.file_reader import read_file_tables
from src.services.bank_recon import reconcile_bank_to_sap
import traceback

try:
    print("=== Reading Bank ZIP ===")
    bank_path = r"D:\Sales code\test_data\omni&farmer\collection\GenericReport_63IDEAS03_010926162632.zip"
    bank_df, _ = read_file_tables(bank_path)
    print(f"Bank shape: {bank_df.shape}")
    print(f"Bank columns: {bank_df.columns.tolist()}")
    print(f"Bank account_number attr: {bank_df.attrs.get('account_number', 'NOT SET')}")
    print(f"\nBank first 3 rows:")
    for idx, row in bank_df.head(3).iterrows():
        print(f"  Row {idx}: TransactionID={row.get('TransactionID')}, Deno Total={row.get('Deno Total')}, ActionDate={row.get('ActionDate')}")
except Exception as e:
    print(f"Error reading bank: {e}")
    traceback.print_exc()

try:
    print("\n=== Reading SAP XLS ===")
    sap_path = r"D:\Sales code\test_data\omni&farmer\collection\Account Balance - 1010204012, CMS - Omnichannel.xls"
    sap_df, _ = read_file_tables(sap_path)
    print(f"SAP shape: {sap_df.shape}")
    print(f"SAP columns: {sap_df.columns.tolist()}")
    print(f"\nSAP first 3 rows:")
    for idx, row in sap_df.head(3).iterrows():
        print(f"  Row {idx}: Details={row.get('Details')}, C/D (LC)={row.get('C/D (LC)')}")
except Exception as e:
    print(f"Error reading SAP: {e}")
    traceback.print_exc()

try:
    print("\n=== Running Reconciliation ===")
    result = reconcile_bank_to_sap(bank_df, sap_df, 'CMS', '')
    print(f"Result shape: {result.shape}")
    print(f"Result columns: {result.columns.tolist()}")
    if len(result) > 0:
        print(f"Result first 3 rows:")
        for idx, row in result.head(3).iterrows():
            print(f"  Row {idx}: Bank_UTR={row.get('Bank_UTR')}, Overall_Status={row.get('Overall_Status')}, Variance={row.get('Amount_Variance')}")
    else:
        print("Result is empty!")
except Exception as e:
    print(f"Error running reconciliation: {e}")
    traceback.print_exc()
