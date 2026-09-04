import pandas as pd

from src.export.excel_exporter import ExcelReportExporter
from src.export.report_verifier import verify_workbook


def _results():
    return pd.DataFrame({
        "Recon_Type": ["Sales", "Sales"],
        "Ref2_Invoice_No": ["1001", "1002"],
        "Total_CD_LC": [100.0, 250.0],
        "Total_Sales_Value": [100.0, 200.0],
        "Amount_Variance": [0.0, 50.0],
        "Overall_Status": ["Matched", "Not Matched"],
        "Reconciliation_Remarks": ["MATCHED", "MISMATCHED: Amount Variance (50.0)"],
    })


def test_verifier_accepts_valid_export(tmp_path):
    report = tmp_path / "report.xlsx"
    ExcelReportExporter().export(str(report), _results())
    verification = verify_workbook(str(report))
    assert verification.passed, verification.errors
    assert verification.warnings


def test_verifier_rejects_changed_amount(tmp_path):
    report = tmp_path / "report.xlsx"
    ExcelReportExporter().export(str(report), _results())
    changed = pd.read_excel(str(report), sheet_name="Recon Detailed Results")
    changed.loc[1, "Total_Sales_Value"] = 210.0
    with pd.ExcelWriter(str(report), engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
        changed.to_excel(writer, sheet_name="Recon Detailed Results", index=False)
    verification = verify_workbook(str(report))
    assert not verification.passed
    assert any("Amount_Variance" in error for error in verification.errors)