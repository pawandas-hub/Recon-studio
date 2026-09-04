"""Desktop GUI entrypoint."""
import sys
import os

# Ensure package root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.cleaners import clean_id, clean_card, clean_number, parse_date_series
from src.core.detector import find_best_col, find_best_sheet, is_sap_table, is_customer_mapping_table, detect_format
from src.readers.file_reader import read_file_tables
from src.services.customer_service import CustomerMappingService, load_customer_mapping
from src.services.recon_engine import ReconciliationEngine, reconcile_dataframes, process_file_list, process_single_file
from src.export.excel_exporter import ExcelReportExporter, save_styled_reconciliation_excel
from src.ui.app_gui import ReconApp, main

if __name__ == "__main__":
    main()