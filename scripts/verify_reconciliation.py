"""CLI for verifying a reconciliation report after a manual run."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.export.report_verifier import verify_workbook


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a reconciliation Excel report")
    parser.add_argument("report", help="Path to Reconciliation_Summary_Report.xlsx")
    parser.add_argument("--input", action="append", dest="input_files", help="Source file; repeat for every input")
    parser.add_argument("--mode", default="Auto Detect")
    parser.add_argument("--model", default="Auto", dest="recon_model")
    args = parser.parse_args()
    verification = verify_workbook(args.report, args.input_files, args.mode, args.recon_model)
    for warning in verification.warnings:
        print(f"WARNING: {warning}")
    for error in verification.errors:
        print(f"ERROR: {error}")
    if verification.passed:
        print("PASS: reconciliation report verified")
        return 0
    print(f"FAIL: {len(verification.errors)} verification error(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())