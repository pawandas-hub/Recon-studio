"""Integration tests for Reconciliation Engine."""
import os
import pandas as pd
from src.services.recon_engine import process_file_list, reconcile_dataframes
from src.readers.file_reader import read_file_tables

def test_format2_reconciliation(sap_ledger_file, retailer_file, customer_map_file):
    assert os.path.exists(sap_ledger_file)
    assert os.path.exists(retailer_file)
    assert os.path.exists(customer_map_file)

    files = [sap_ledger_file, retailer_file, customer_map_file]
    results = process_file_list(files, mode="Auto Detect")

    assert not results.empty
    # Exactly 373 Retailer invoices reconciled
    assert len(results) == 373

    # Check that all 3 customer code columns exist and are populated
    assert 'Customer_Id' in results.columns
    assert 'Mapped_SAP_Code' in results.columns
    assert 'SAP_Offset_Account' in results.columns

    # Verify matching status counts
    matched_count = (results['Overall_Status'] == 'Matched').sum()
    mismatched_count = (results['Overall_Status'] == 'Not Matched').sum()
    assert matched_count == 156
    assert mismatched_count == 217

def test_synthetic_reconciliation():
    df_bu = pd.DataFrame({
        'Ref. 2': ['INV-1001', 'INV-1002'],
        'Posting Date': ['01/08/26', '02/08/26'],
        'C/D (LC)': [1500.0, 2000.0],
        'Offset Account': ['CU5001', 'CU5002'],
        'Business Unit': ['BU_Kolkata', 'BU_Kolkata']
    })
    df_sales = pd.DataFrame({
        'Invoice_Number': ['INV-1001', 'INV-1002', 'INV-1003'],
        'Invoice_Date': ['2026-08-01', '2026-08-02', '2026-08-03'],
        'TotalValue_After_Disc': [1500.0, 1900.0, 3000.0],
        'Customer_Id': ['5001', '5002', '5003'],
        'SO_Project': ['BU_Kolkata', 'BU_Kolkata', 'BU_Kolkata']
    })

    recon = reconcile_dataframes(df_bu, df_sales, mode='Format 2 (Retailer / Ref. 2 vs Invoice No)')
    assert len(recon) == 3
    assert recon.loc[recon['Ref2_Invoice_No'] == '1001', 'Overall_Status'].values[0] == 'Matched'
    assert recon.loc[recon['Ref2_Invoice_No'] == '1002', 'Overall_Status'].values[0] == 'Not Matched'
    assert 'Amount Variance' in recon.loc[recon['Ref2_Invoice_No'] == '1002', 'Reconciliation_Remarks'].values[0]
    assert recon.loc[recon['Ref2_Invoice_No'] == '1003', 'Overall_Status'].values[0] == 'Not Matched'
    assert 'Missing in SAP' in recon.loc[recon['Ref2_Invoice_No'] == '1003', 'Reconciliation_Remarks'].values[0]

def test_sales_model_can_be_selected_explicitly(sap_ledger_file, retailer_file, customer_map_file):
    results = process_file_list(
        [sap_ledger_file, retailer_file, customer_map_file],
        mode="Auto Detect",
        recon_model="Sales Reconciliation"
    )
    assert 'Ref2_Invoice_No' in results.columns
    assert 'Bank_UTR' not in results.columns

def test_sales_model_combines_multiple_sap_and_sales_files(project_root):
    files = [
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', '4020101003.xls'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', '4020101022.xls'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', 'SAPOmni.xlsx')
    ]
    results = process_file_list(files, recon_model="Sales Reconciliation")
    assert not results.empty
    assert 'Bank_UTR' not in results.columns


def test_sales_model_keeps_mixed_sales_export_formats(tmp_path):
    sap = pd.DataFrame({
        'Ref. 1': ['1001'],
        'Ref. 2': ['2001'],
        'Posting Date': ['01/08/26'],
        'C/D (LC)': [100.0],
        'Offset Account': ['A1'],
        'Business Unit': ['BU1'],
    })
    ref_id_sales = pd.DataFrame({
        'RefId': ['1001'], 'DocDate': ['01/08/26'],
        'TAXABLEAMOUNT': [100.0], 'CardCode': ['A1'],
    })
    invoice_sales = pd.DataFrame({
        'Invoice_Number': ['2001'], 'Invoice_Date': ['01/08/26'],
        'TotalValue_After_Disc': [100.0], 'Customer_Id': ['A1'],
    })

    sap_path = tmp_path / '4020101003.csv'
    ref_id_path = tmp_path / 'SAPOmni.csv'
    invoice_path = tmp_path / 'RetailerFnV.csv'
    sap.to_csv(sap_path, index=False)
    ref_id_sales.to_csv(ref_id_path, index=False)
    invoice_sales.to_csv(invoice_path, index=False)

    results = process_file_list(
        [str(sap_path), str(ref_id_path), str(invoice_path)],
        recon_model='Sales Reconciliation',
    )

    assert len(results) == 2
    assert set(results['Overall_Status']) == {'Matched'}


def test_combined_sales_result_uses_populated_reference_column():
    from src.ui.app_gui import _sales_reference

    row = pd.Series({'Ref2_Invoice_No': float('nan'), 'RefId_Ref1': '1458247'})

    assert _sales_reference(row) == '1458247'

def test_sales_status_handles_missing_remarks():
    df_bu = pd.DataFrame({'Ref. 1': ['1001'], 'Posting Date': ['01/08/26'], 'C/D (LC)': [100.0], 'Offset Account': ['A1']})
    df_sales = pd.DataFrame({'RefId': ['1001'], 'DocDate': ['01/08/26'], 'TAXABLEAMOUNT': [100.0], 'CardCode': ['A1']})
    result = reconcile_dataframes(df_bu, df_sales, mode='Format 1 (Legacy / Ref. 1 vs DB)')
    assert result.loc[0, 'Overall_Status'] == 'Matched'


def test_sales_reconciliation_nets_reversal_entries():
    df_bu = pd.DataFrame({
        'Ref. 1': ['1472709', '1472709', '1472709'],
        'Posting Date': ['14/08/26', '14/08/26', '14/08/26'],
        'C/D (LC)': [-202389.15, 202389.15, -202389.15],
        'Offset Account': ['DOM0000184', 'DOM0000184', 'OM1834451'],
        'Business Unit': ['BU_14', 'BU_14', 'BU_14'],
    })
    df_sales = pd.DataFrame({
        'RefId': ['1472709'], 'DocDate': ['14/08/26'],
        'TAXABLEAMOUNT': [202389.15], 'CardCode': ['1834451'],
    })

    result = reconcile_dataframes(df_bu, df_sales, mode='Format 1 (Legacy / Ref. 1 vs DB)')

    assert result.loc[0, 'Total_CD_LC'] == 202389.15
    assert result.loc[0, 'Amount_Variance'] == 0
    assert result.loc[0, 'SAP_Offset_Account'] == '1834451'
    assert result.loc[0, 'Overall_Status'] == 'Matched'


def test_combined_both_model(project_root):
    files = [
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', '4020101003.xls'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', 'SAPOmni.xlsx'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'collection', 'Account Balance - 1010202089, ICICI- 107505004792.xls'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'collection', '4792 DetailedStatement.xlsx'),
    ]
    results = process_file_list(files, recon_model="Both (Combined)")
    assert not results.empty
    assert 'Recon_Type' in results.columns
    recon_types = set(results['Recon_Type'].unique())
    assert 'Sales' in recon_types
    assert 'Collection' in recon_types


def test_cancellation_event(project_root):
    from threading import Event
    import pytest
    cancel_evt = Event()
    cancel_evt.set()
    files = [
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', 'SAPOmni.xlsx'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', '4020101003.xls'),
    ]
    with pytest.raises(RuntimeError, match="cancelled"):
        process_file_list(files, cancel_event=cancel_evt)


def test_progress_callback_emitted(project_root):
    stages = []
    def callback(stage, cur, tot):
        stages.append((stage, cur, tot))

    files = [
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', 'SAPOmni.xlsx'),
        os.path.join(project_root, 'test_data', 'omni&farmer', 'sales', '4020101022.xls'),
    ]
    results = process_file_list(files, progress_callback=callback)
    assert not results.empty
    assert len(stages) > 0


def test_generated_report_is_ignored_when_reusing_input_folder(project_root):
    sales_dir = os.path.join(project_root, 'test_data', 'omni&farmer', 'sales')
    files = [
        os.path.join(sales_dir, '4020101003.xls'),
        os.path.join(sales_dir, 'SAPOmni.xlsx'),
        os.path.join(sales_dir, 'Reconciliation_Summary_Report.xlsx'),
    ]

    results = process_file_list(files, recon_model='Sales Reconciliation')

    assert not results.empty
    assert set(results['Recon_Type']) == {'Sales'}


