"""Unit tests for detector module."""
import pandas as pd
from src.core.detector import find_best_col, find_best_sheet, is_sap_table, is_customer_mapping_table, detect_format

def test_find_best_col():
    df = pd.DataFrame(columns=["Ref. 2", "Posting Date", "C/D (LC)", "Offset Account"])
    assert find_best_col(df, ["Ref 2", "Ref. 2", "Reference"]) == "Ref. 2"
    assert find_best_col(df, ["Date", "Posting Date"]) == "Posting Date"
    assert find_best_col(df, ["NonExistent"]) is None

def test_find_best_sheet():
    sheets = ["Summary", "SAP_Journal", "DB_Result"]
    assert find_best_sheet(sheets, ["SAP", "Journal"]) == "SAP_Journal"
    assert find_best_sheet(sheets, ["DB", "Result"]) == "DB_Result"

def test_is_sap_table():
    df_sap = pd.DataFrame(columns=["Trans. No.", "Posting Date", "C/D (LC)", "Offset Account", "Ref. 2"])
    assert is_sap_table(df_sap) is True

    df_sales = pd.DataFrame(columns=["Invoice_Number", "Invoice_Date", "TotalValue_After_Disc"])
    assert is_sap_table(df_sales) is False

def test_is_customer_mapping_table():
    df_map = pd.DataFrame(columns=["Customer_Id", "SAP Code"])
    assert is_customer_mapping_table(df_map) is True

    df_other = pd.DataFrame(columns=["Product_Id", "Price"])
    assert is_customer_mapping_table(df_other) is False

def test_detect_format():
    df_bu = pd.DataFrame(columns=["Ref. 2", "Posting Date", "C/D (LC)"])
    df_db = pd.DataFrame(columns=["Invoice_Number", "Invoice_Date", "TotalValue_After_Disc"])
    assert detect_format(df_bu, df_db, mode="Auto") == "format2"

    df_bu1 = pd.DataFrame(columns=["Ref. 1", "Posting Date", "TAXABLEAMOUNT"])
    df_db1 = pd.DataFrame(columns=["RefId", "DocDate", "TAXABLEAMOUNT"])
    assert detect_format(df_bu1, df_db1, mode="Auto") == "format1"

