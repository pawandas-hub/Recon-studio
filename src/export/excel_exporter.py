"""Excel Report Exporter with openpyxl styling — separate Sales and Collection sheets."""
import shutil
from typing import Callable, List, Optional

import numpy as np
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ..core.constants import STYLE_CONFIG

try:
    import xlsxwriter
    HAS_XLSXWRITER = True
except ImportError:
    HAS_XLSXWRITER = False

def _sanitize_cell_value(value):
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
        return f"'{value}"
    return value


class ExcelReportExporter:
    """Exports structured reconciliation results and KPI summaries to styled Excel workbooks."""

    # Columns that belong to the SAP side of a Sales reconciliation
    _SAP_SIDE_COLS = [
        'Assignment', 'Document_Number', 'Reference', 'Doc_Header_Text', 'Posting_Date',
        'Document_Date', 'Profit_Center', 'Total_CD_LC', 'Amount_in_Doc_Curr',
        'Sales_Organization', 'Distribution_Channel', 'Division', 'Customer_Code',
        'Customer_Name', 'City', 'Region', 'Material_Number', 'Material_Description',
        'Billing_Quantity', 'Billing_Unit', 'Net_Value', 'Tax_Amount', 'Document_Currency',
        'Business_Unit', 'InvoiceId', 'RefId_Ref1', 'Ref2_Invoice_No', 'SO_ID', 'CN_Reference',
        'SAP_Freight_Amount', 'SAP_GRN_ID', 'SAP_Offset_Account',
        'Mapped_SAP_Code', 'Format_Used',
    ]
    # Columns that belong to the DB side of a Sales reconciliation
    _DB_SIDE_COLS = [
        'Business_Unit', 'InvoiceId', 'RefId_Ref1', 'Ref2_Invoice_No', 'Reference',
        'SO_ID', 'CN_Reference', 'DB_SAP_ID',
        'Sales_DocDate', 'Total_Sales_Value', 'DB_Freight_Amount', 'Freight_Variance', 'DB_GRN_ID',
        'Customer_Id', 'Retailer_Customer_Id',
        'COGSCostingCode', 'Format_Used',
    ]
    # Columns that belong to the SAP side of a Collection reconciliation
    _COLL_SAP_SIDE_COLS = [
        'SAP_Doc_Number', 'SAP_Posting_Date', 'SAP_Amount', 'SAP_Offset_Account',
        'Bank_UTR', 'Origin_No', 'Details', 'C/D (LC)', 'Offset Account',
    ]
    # Columns that belong to the Bank side of a Collection reconciliation
    _COLL_BANK_SIDE_COLS = [
        'Bank_Name', 'Bank_Account_Number', 'Bank_UTR', 'Bank_Date', 'Bank_Amount',
        'Bank_Description', 'Transaction ID', 'TransactionID', 'PNBTransactionID', 'Deposit Amt (INR)',
    ]

    def __init__(self, style_config: Optional[dict] = None):
        self.config = style_config or STYLE_CONFIG

    # ------------------------------------------------------------------
    # Sales executive summary table builder
    # ------------------------------------------------------------------
    @staticmethod
    def _build_sales_summary_table(sales_df: pd.DataFrame) -> pd.DataFrame:
        """Build a Sales/CN × BU breakdown table for the Executive Summary.

        Rows are classified as **Sales** (positive amount) or **CN** (negative amount).
        BU is dynamically determined from all distinct Business_Unit values in the data.
        """
        if sales_df.empty:
            return pd.DataFrame()

        # Determine the amount column available
        sap_col = 'Total_CD_LC' if 'Total_CD_LC' in sales_df.columns else None
        db_col = 'Total_Sales_Value' if 'Total_Sales_Value' in sales_df.columns else None
        var_col = 'Amount_Variance' if 'Amount_Variance' in sales_df.columns else None

        sales_df = sales_df.copy()

        # Classify Sales vs CN by sign of amount (negative -> CN, positive/zero -> Sales)
        if sap_col and db_col:
            sap_amt = pd.to_numeric(sales_df[sap_col], errors='coerce').fillna(0)
            db_amt = pd.to_numeric(sales_df[db_col], errors='coerce').fillna(0)
            is_cn = (sap_amt < 0) | (db_amt < 0)
            sales_df['_Particulars'] = np.where(is_cn, 'CN', 'Sales')
        elif sap_col:
            sap_amt = pd.to_numeric(sales_df[sap_col], errors='coerce').fillna(0)
            sales_df['_Particulars'] = np.where(sap_amt < 0, 'CN', 'Sales')
        elif db_col:
            db_amt = pd.to_numeric(sales_df[db_col], errors='coerce').fillna(0)
            sales_df['_Particulars'] = np.where(db_amt < 0, 'CN', 'Sales')
        else:
            sales_df['_Particulars'] = 'Sales'

        # Override: rows with explicit Particulars='CN' from CN recon pipeline
        if 'Particulars' in sales_df.columns:
            explicit_cn = sales_df['Particulars'].astype(str).str.strip().str.upper() == 'CN'
            sales_df.loc[explicit_cn, '_Particulars'] = 'CN'

        # Extract all distinct BU values dynamically from SAP records
        bu_col = 'Business_Unit'
        if bu_col in sales_df.columns:
            cleaned_bus = sales_df[bu_col].fillna('').astype(str).str.strip()
            sales_df['_BU_Clean'] = cleaned_bus
            excluded_bus = {'nan', 'none', 'null', '<na>', '', 'missing in sap', 'missing', 'n/a'}
            valid_bus = [b for b in cleaned_bus.unique() if b and b.lower() not in excluded_bus]
            if not valid_bus:
                valid_bus = ['N/A']
            else:
                def sort_key(x):
                    try:
                        return (0, int(x))
                    except ValueError:
                        return (1, str(x))
                valid_bus = sorted(valid_bus, key=sort_key)
        else:
            sales_df['_BU_Clean'] = 'N/A'
            valid_bus = ['N/A']

        rows: List[dict] = []
        for particulars in ('Sales', 'CN'):
            for bu in valid_bus:
                subset = sales_df[
                    (sales_df['_Particulars'] == particulars)
                    & (sales_df['_BU_Clean'] == bu)
                ]
                rows.append({
                    'Particulars': particulars,
                    'BU': bu,
                    'Total line item as per DB': len(subset),
                    'DB Amount': round(float(pd.to_numeric(subset[db_col], errors='coerce').fillna(0).sum()), 2) if db_col else 0.0,
                    'SAP Amount': round(float(pd.to_numeric(subset[sap_col], errors='coerce').fillna(0).sum()), 2) if sap_col else 0.0,
                    'Amount Variance': round(float(pd.to_numeric(subset[var_col], errors='coerce').fillna(0).sum()), 2) if var_col else 0.0,
                })

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Collection executive summary table builder
    # ------------------------------------------------------------------
    @staticmethod
    def _build_collection_summary_table(coll_df: pd.DataFrame) -> pd.DataFrame:
        """Build a Collection breakdown table by Bank Name and Account Number.

        Columns: Particulars (Bank Name), Account Number, Total line item as per Bank,
        Bank Amount, SAP Amount, Amount Variance.
        """
        if coll_df.empty:
            return pd.DataFrame()

        import re

        coll_df = coll_df.copy()
        bank_name_col = 'Bank_Name' if 'Bank_Name' in coll_df.columns else None
        bank_acc_col = 'Bank_Account_Number' if 'Bank_Account_Number' in coll_df.columns else None
        db_col = 'Bank_Amount' if 'Bank_Amount' in coll_df.columns else None
        sap_col = 'SAP_Amount' if 'SAP_Amount' in coll_df.columns else None
        var_col = 'Amount_Variance' if 'Amount_Variance' in coll_df.columns else None

        coll_df['_Bank'] = coll_df[bank_name_col].fillna('Bank').astype(str).str.strip() if bank_name_col else 'Bank'

        def clean_acc(val):
            s = str(val).strip() if val is not None and not pd.isna(val) else ''
            if not s or s.lower() in ('nan', 'none', 'null', '<na>'):
                return 'N/A'
            m = re.search(r'\d{6,}', s)
            if m:
                return m.group(0)
            return s

        coll_df['_Account'] = coll_df[bank_acc_col].apply(clean_acc) if bank_acc_col else 'N/A'

        groups = coll_df.groupby(['_Bank', '_Account'], sort=False)
        rows: List[dict] = []
        for (bank, acc), subset in groups:
            db_amt = round(float(pd.to_numeric(subset[db_col], errors='coerce').fillna(0).sum()), 2) if db_col else 0.0
            sap_amt = round(float(pd.to_numeric(subset[sap_col], errors='coerce').fillna(0).sum()), 2) if sap_col else 0.0
            var_amt = round(float(pd.to_numeric(subset[var_col], errors='coerce').fillna(0).sum()), 2) if var_col else round(db_amt - sap_amt, 2)
            rows.append({
                'Particulars': bank,
                'Account Number': acc,
                'Total line item as per Bank': len(subset),
                'Bank Amount': db_amt,
                'SAP Amount': sap_amt,
                'Amount Variance': var_amt,
            })

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Split Sales data into SAP-side and DB-side DataFrames
    # ------------------------------------------------------------------
    @staticmethod
    def _split_sales_sides(sales_df: pd.DataFrame):
        """Return (sap_df, db_df) containing only the relevant columns."""
        sap_cols = [c for c in ExcelReportExporter._SAP_SIDE_COLS if c in sales_df.columns]
        db_cols = [c for c in ExcelReportExporter._DB_SIDE_COLS if c in sales_df.columns]
        if not sap_cols and not sales_df.empty:
            sap_cols = [c for c in sales_df.columns if c not in ExcelReportExporter._DB_SIDE_COLS]
        if not db_cols and not sales_df.empty:
            db_cols = [c for c in sales_df.columns if c not in ExcelReportExporter._SAP_SIDE_COLS]
        return (
            sales_df[sap_cols].copy() if sap_cols else sales_df.copy(),
            sales_df[db_cols].copy() if db_cols else sales_df.copy(),
        )

    # ------------------------------------------------------------------
    # Split Collection data into SAP-side and Bank-side DataFrames
    # ------------------------------------------------------------------
    @staticmethod
    def _split_collection_sides(coll_df: pd.DataFrame):
        """Return (sap_df, bank_df) containing relevant columns."""
        sap_cols = [c for c in ExcelReportExporter._COLL_SAP_SIDE_COLS if c in coll_df.columns]
        bank_cols = [c for c in ExcelReportExporter._COLL_BANK_SIDE_COLS if c in coll_df.columns]
        if not sap_cols and not coll_df.empty:
            sap_cols = [c for c in coll_df.columns if c not in ExcelReportExporter._COLL_BANK_SIDE_COLS]
        if not bank_cols and not coll_df.empty:
            bank_cols = [c for c in coll_df.columns if c not in ExcelReportExporter._COLL_SAP_SIDE_COLS]
        return (
            coll_df[sap_cols].copy() if sap_cols else coll_df.copy(),
            coll_df[bank_cols].copy() if bank_cols else coll_df.copy(),
        )

    def export(
        self,
        save_path: str,
        results_df: pd.DataFrame,
        kpi_summary: Optional[pd.DataFrame] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        raw_sales_sap: Optional[pd.DataFrame] = None,
        raw_sales_db: Optional[pd.DataFrame] = None,
        raw_collection_sap: Optional[pd.DataFrame] = None,
        raw_collection_bank: Optional[pd.DataFrame] = None,
        engine: Optional[str] = "auto",
    ) -> None:
        def report(stage: str, current: int = 0, total: int = 0) -> None:
            if progress_callback:
                progress_callback(stage, current, total)

        report("Preparing Excel report")

        if kpi_summary is None:
            sap_total = (
                results_df['Total_CD_LC'].sum()
                if 'Total_CD_LC' in results_df
                else results_df.get('SAP_Amount', pd.Series(dtype=float)).sum()
            )
            sales_total = (
                results_df['Total_Sales_Value'].sum()
                if 'Total_Sales_Value' in results_df
                else results_df.get('Bank_Amount', pd.Series(dtype=float)).sum()
            )
            var_total = results_df['Amount_Variance'].sum() if 'Amount_Variance' in results_df else 0.0
            total_count = len(results_df)
            matched_count = int((results_df['Overall_Status'] == 'Matched').sum()) if 'Overall_Status' in results_df.columns else 0
            kpi_summary = pd.DataFrame([{
                'Total Records Reconciled': total_count,
                'Fully Matched Count': matched_count,
                'Mismatched Count': total_count - matched_count,
                'Match Rate (%)': round(matched_count / total_count * 100, 1) if total_count else 0,
                'Total SAP Amount': round(sap_total, 2),
                'Total Sales/Bank Amount': round(sales_total, 2),
                'Total Net Variance': round(var_total, 2),
            }])

        # Style helpers
        red_fill = PatternFill(start_color=self.config['red_fill'], end_color=self.config['red_fill'], fill_type='solid')
        green_fill = PatternFill(start_color=self.config['green_fill'], end_color=self.config['green_fill'], fill_type='solid')
        header_fill = PatternFill(start_color=self.config['header_fill'], end_color=self.config['header_fill'], fill_type='solid')
        header_font = Font(color=self.config['header_font_color'], bold=True)
        thin_side = Side(style='thin', color=self.config['border_color'])
        thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        def _style_sheet(ws: object, df_len: int, sheet_label: str) -> None:
            """Apply header style, frozen pane, autofilter, row colours, and column widths."""
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions

            # Header row
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')

            # Find Overall_Status column index (0-indexed within row tuple)
            status_col_idx = None
            status_col_letter = None
            for idx, cell in enumerate(ws[1]):
                if str(cell.value or '').strip() == 'Overall_Status':
                    status_col_idx = idx
                    status_col_letter = get_column_letter(idx + 1)
                    break

            total_rows = max(ws.max_row - 1, 1)

            # Fast path for large sheets (> 3,000 rows): use native Excel conditional formatting
            # to avoid generating millions of Python cell style objects
            if total_rows > 3000 and status_col_letter:
                from openpyxl.formatting.rule import FormulaRule
                rule_green = FormulaRule(
                    formula=[f'${status_col_letter}2="Matched"'],
                    fill=green_fill
                )
                rule_red = FormulaRule(
                    formula=[f'AND(${status_col_letter}2<>"", ${status_col_letter}2<>"Matched")'],
                    fill=red_fill
                )
                last_col_letter = get_column_letter(ws.max_column)
                cell_range = f'A2:{last_col_letter}{ws.max_row}'
                ws.conditional_formatting.add(cell_range, rule_green)
                ws.conditional_formatting.add(cell_range, rule_red)
                report(f"Styling {sheet_label}", total_rows, total_rows)
            else:
                row_num = 0
                for row in ws.iter_rows(min_row=2):
                    row_num += 1
                    status_val = str(row[status_col_idx].value if status_col_idx is not None else '').strip()
                    is_matched = status_val.lower() == 'matched'
                    row_fill = green_fill if is_matched else red_fill
                    row_font_color = self.config['green_font_color'] if is_matched else self.config['red_font_color']
                    for idx, cell in enumerate(row):
                        cell.border = thin_border
                        cell.fill = row_fill
                        if idx == status_col_idx:
                            cell.font = Font(color=row_font_color, bold=True)
                    if row_num % max(total_rows // 10, 1) == 0:
                        report(f"Styling {sheet_label}", row_num, total_rows)

            # Fast auto column widths (sample up to 25 rows on large tables)
            sample_limit = min(ws.max_row, 25 if total_rows > 3000 else ws.max_row)
            for col_idx in range(1, ws.max_column + 1):
                col_letter = get_column_letter(col_idx)
                header_val = str(ws.cell(row=1, column=col_idx).value or '')
                max_len = max(len(header_val), 10)
                for r in range(2, sample_limit + 1):
                    val_str = str(ws.cell(row=r, column=col_idx).value or '')
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

            report(f"Styling {sheet_label}", total_rows, total_rows)

        def _style_plain_sheet(ws: object, sheet_label: str) -> None:
            """Style a data sheet that has no Overall_Status column (e.g. exact SAP/DB data)."""
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions

            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')

            total_rows = max(ws.max_row - 1, 1)
            # Only apply individual borders if rows are reasonably sized (<= 3000)
            if total_rows <= 3000:
                for row in ws.iter_rows(min_row=2):
                    for cell in row:
                        cell.border = thin_border

            sample_limit = min(ws.max_row, 300) if total_rows > 3000 else ws.max_row
            for col_idx in range(1, ws.max_column + 1):
                col_letter = get_column_letter(col_idx)
                max_len = 10
                for r in range(1, sample_limit + 1):
                    val_str = str(ws.cell(row=r, column=col_idx).value or '')
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

            report(f"Styling {sheet_label}", 1, 1)

        # ----------------------------------------------------------
        # Extract Sales & Collection data for summary tables & raw sheets
        # ----------------------------------------------------------
        sales_df = pd.DataFrame()
        coll_df = pd.DataFrame()
        if 'Recon_Type' in results_df.columns:
            sales_df = results_df[results_df['Recon_Type'] == 'Sales'].copy()
            coll_df = results_df[results_df['Recon_Type'] == 'Collection'].copy()
        elif 'Total_CD_LC' in results_df.columns:
            sales_df = results_df.copy()
        elif 'Bank_UTR' in results_df.columns:
            coll_df = results_df.copy()

        sales_summary_table = self._build_sales_summary_table(sales_df) if not sales_df.empty else pd.DataFrame()
        coll_summary_table = self._build_collection_summary_table(coll_df) if not coll_df.empty else pd.DataFrame()

        # Raw Sales Data (exact uploaded data)
        raw_sap_s = raw_sales_sap if raw_sales_sap is not None else results_df.attrs.get('raw_sales_sap')
        raw_db_s = raw_sales_db if raw_sales_db is not None else results_df.attrs.get('raw_sales_db')

        if raw_sap_s is not None and isinstance(raw_sap_s, pd.DataFrame) and not raw_sap_s.empty:
            sales_sap_side_df = raw_sap_s.copy()
            sales_sap_side_df = raw_sap_s
        elif not sales_df.empty:
            sales_sap_side_df, _ = self._split_sales_sides(sales_df)
        else:
            sales_sap_side_df = pd.DataFrame()

        if raw_db_s is not None and isinstance(raw_db_s, pd.DataFrame) and not raw_db_s.empty:
            sales_db_side_df = raw_db_s.copy()
            sales_db_side_df = raw_db_s
        elif not sales_df.empty:
            _, sales_db_side_df = self._split_sales_sides(sales_df)
        else:
            sales_db_side_df = pd.DataFrame()

        # Raw Collection Data (exact uploaded data)
        raw_sap_c = raw_collection_sap if raw_collection_sap is not None else results_df.attrs.get('raw_collection_sap')
        raw_bank_c = raw_collection_bank if raw_collection_bank is not None else results_df.attrs.get('raw_collection_bank')

        if raw_sap_c is not None and isinstance(raw_sap_c, pd.DataFrame) and not raw_sap_c.empty:
            coll_sap_side_df = raw_sap_c.copy()
            coll_sap_side_df = raw_sap_c
        elif not coll_df.empty:
            coll_sap_side_df, _ = self._split_collection_sides(coll_df)
        else:
            coll_sap_side_df = pd.DataFrame()

        if raw_bank_c is not None and isinstance(raw_bank_c, pd.DataFrame) and not raw_bank_c.empty:
            coll_bank_side_df = raw_bank_c.copy()
            coll_bank_side_df = raw_bank_c
        elif not coll_df.empty:
            _, coll_bank_side_df = self._split_collection_sides(coll_df)
        else:
            coll_bank_side_df = pd.DataFrame()

        # Check whether to use fast xlsxwriter engine
        use_fast = False
        if engine == "xlsxwriter":
            use_fast = HAS_XLSXWRITER
        elif engine == "openpyxl":
            use_fast = False
        else:  # auto
            use_fast = HAS_XLSXWRITER and len(results_df) > 3000

        if use_fast:
            self._export_fast_xlsxwriter(
                save_path=save_path,
                results_df=results_df,
                kpi_summary=kpi_summary,
                sales_summary_table=sales_summary_table,
                coll_summary_table=coll_summary_table,
                sales_sap_side_df=sales_sap_side_df,
                sales_db_side_df=sales_db_side_df,
                coll_sap_side_df=coll_sap_side_df,
                coll_bank_side_df=coll_bank_side_df,
                report=report,
            )
            return

        with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
            report("Writing Executive Summary sheet", 0, 1)
            kpi_summary.to_excel(writer, sheet_name='Executive Summary', index=False)

            report("Writing Recon Detailed Results sheet", 0, 1)
            results_df.to_excel(writer, sheet_name='Recon Detailed Results', index=False)

            # Per-type sheets (Sales / Collection)
            if 'Recon_Type' in results_df.columns:
                for recon_type, frame in results_df.groupby('Recon_Type', sort=False):
                    sheet_name = str(recon_type)[:31] or 'Results'
                    report(f"Writing {sheet_name} sheet", 0, 1)
                    frame.to_excel(writer, sheet_name=sheet_name, index=False)

            # Raw data sheets (exact uploaded or side-split data)
            if not sales_sap_side_df.empty:
                report("Writing Sales - SAP Data sheet", 0, 1)
                sales_sap_side_df.to_excel(writer, sheet_name='Sales - SAP Data', index=False)
            if not sales_db_side_df.empty:
                report("Writing Sales - DB Data sheet", 0, 1)
                sales_db_side_df.to_excel(writer, sheet_name='Sales - DB Data', index=False)
            if not coll_sap_side_df.empty:
                report("Writing Collection - SAP Data sheet", 0, 1)
                coll_sap_side_df.to_excel(writer, sheet_name='Collection - SAP Data', index=False)
            if not coll_bank_side_df.empty:
                report("Writing Collection - Bank Data sheet", 0, 1)
                coll_bank_side_df.to_excel(writer, sheet_name='Collection - Bank Data', index=False)

            # "Data Not Available in DB" sheet — SAP rows with no matching DB record
            data_not_in_db = results_df.attrs.get('data_not_in_db') if hasattr(results_df, 'attrs') else None
            if data_not_in_db is not None and isinstance(data_not_in_db, pd.DataFrame) and not data_not_in_db.empty:
                report("Writing 'data not available in DB' sheet", 0, 1)
                data_not_in_db.to_excel(writer, sheet_name='data not available in DB', index=False)

            wb = writer.book

            # ----------------------------------------------------------
            # Style Executive Summary — KPI row + Summary tables
            # ----------------------------------------------------------
            ws_summary = wb['Executive Summary']
            for col_idx in range(1, ws_summary.max_column + 1):
                cell = ws_summary.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            for col in ws_summary.columns:
                max_len = max((len(str(c.value or '')) for c in col), default=10)
                ws_summary.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 14)

            def _write_section_table(title: str, table_df: pd.DataFrame) -> None:
                if table_df.empty:
                    return
                start_row = ws_summary.max_row + 2
                title_cell = ws_summary.cell(row=start_row, column=1, value=title)
                title_cell.font = Font(bold=True, size=12)
                start_row += 1

                summary_headers = list(table_df.columns)
                for col_idx, header in enumerate(summary_headers, 1):
                    cell = ws_summary.cell(row=start_row, column=col_idx, value=header)
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = thin_border

                for row_idx, (_, row_data) in enumerate(table_df.iterrows(), start_row + 1):
                    for col_idx, value in enumerate(row_data, 1):
                        cell = ws_summary.cell(row=row_idx, column=col_idx, value=_sanitize_cell_value(value))
                        cell.border = thin_border
                        cell.alignment = Alignment(horizontal='center', vertical='center')

                for col_idx, header in enumerate(summary_headers, 1):
                    col_letter = get_column_letter(col_idx)
                    current_width = ws_summary.column_dimensions[col_letter].width or 0
                    new_width = max(len(header) + 3, 14)
                    ws_summary.column_dimensions[col_letter].width = max(current_width, new_width)

            # Write the Sales summary table below the KPI row
            if not sales_summary_table.empty:
                _write_section_table('Sales Reconciliation Summary', sales_summary_table)

            # Write the Collection summary table below
            if not coll_summary_table.empty:
                _write_section_table('Collection Reconciliation Summary', coll_summary_table)

            # Style all data sheets
            sheets_to_style = ['Recon Detailed Results']
            if 'Recon_Type' in results_df.columns:
                for rt in results_df['Recon_Type'].dropna().unique():
                    sn = str(rt)[:31]
                    if sn in wb.sheetnames:
                        sheets_to_style.append(sn)

            for sheet_name in sheets_to_style:
                if sheet_name in wb.sheetnames:
                    df_rows = (
                        len(results_df) if sheet_name == 'Recon Detailed Results'
                        else len(results_df[results_df['Recon_Type'] == sheet_name])
                    )
                    _style_sheet(wb[sheet_name], df_rows, sheet_name)

            # Style the plain raw data sheets (no status colouring)
            for plain_sheet in ('Sales - SAP Data', 'Sales - DB Data', 'Collection - SAP Data', 'Collection - Bank Data', 'data not available in DB'):
                if plain_sheet in wb.sheetnames:
                    _style_plain_sheet(wb[plain_sheet], plain_sheet)

        report("Excel export complete", 1, 1)

    def _export_fast_xlsxwriter(
        self,
        save_path: str,
        results_df: pd.DataFrame,
        kpi_summary: pd.DataFrame,
        sales_summary_table: pd.DataFrame,
        coll_summary_table: pd.DataFrame,
        sales_sap_side_df: pd.DataFrame,
        sales_db_side_df: pd.DataFrame,
        coll_sap_side_df: pd.DataFrame,
        coll_bank_side_df: pd.DataFrame,
        report: Callable[[str, int, int], None],
    ) -> None:
        """High-performance streaming export using xlsxwriter with constant_memory."""
        report("Initializing fast Excel stream", 0, 1)
        wb = xlsxwriter.Workbook(
            save_path,
            {
                'constant_memory': True,
                'default_date_format': 'yyyy-mm-dd',
                'strings_to_numbers': False,
                'nan_inf_to_errors': True,
            }
        )

        header_bg = '#' + self.config.get('header_fill', '1F4E78')
        header_font_color = '#' + self.config.get('header_font_color', 'FFFFFF')
        border_col = '#' + self.config.get('border_color', 'D9D9D9')

        fmt_header = wb.add_format({
            'bold': True,
            'bg_color': header_bg,
            'font_color': header_font_color,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'border_color': border_col,
        })
        fmt_section_title = wb.add_format({
            'bold': True,
            'font_size': 12,
        })
        fmt_cell = wb.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'border_color': border_col,
        })
        fmt_green = wb.add_format({'bg_color': '#' + self.config.get('green_fill', 'D6FFD6')})
        fmt_red = wb.add_format({'bg_color': '#' + self.config.get('red_fill', 'FFD6D6')})

        # ----------------------------------------------------------
        # 1. Executive Summary
        # ----------------------------------------------------------
        report("Writing Executive Summary sheet", 0, 1)
        ws_exec = wb.add_worksheet('Executive Summary')
        kpi_cols = list(kpi_summary.columns)
        ws_exec.write_row(0, 0, kpi_cols, fmt_header)
        ws_exec.write_row(1, 0, [_sanitize_cell_value(v) for v in kpi_summary.iloc[0]], fmt_cell)

        exec_r = 3
        if not sales_summary_table.empty:
            ws_exec.write(exec_r, 0, 'Sales Reconciliation Summary', fmt_section_title)
            exec_r += 1
            ws_exec.write_row(exec_r, 0, list(sales_summary_table.columns), fmt_header)
            exec_r += 1
            for row in sales_summary_table.itertuples(index=False, name=None):
                ws_exec.write_row(exec_r, 0, [_sanitize_cell_value(v) for v in row], fmt_cell)
                exec_r += 1
            exec_r += 1

        if not coll_summary_table.empty:
            ws_exec.write(exec_r, 0, 'Collection Reconciliation Summary', fmt_section_title)
            exec_r += 1
            ws_exec.write_row(exec_r, 0, list(coll_summary_table.columns), fmt_header)
            exec_r += 1
            for row in coll_summary_table.itertuples(index=False, name=None):
                ws_exec.write_row(exec_r, 0, [_sanitize_cell_value(v) for v in row], fmt_cell)
                exec_r += 1

        for c_idx, c_name in enumerate(kpi_cols):
            ws_exec.set_column(c_idx, c_idx, max(len(str(c_name)) + 4, 15))

        # ----------------------------------------------------------
        # Helpers: Vectorized stream & Instant XML sheet clone
        # ----------------------------------------------------------
        def _prepare_df_for_stream(df: pd.DataFrame) -> list:
            """Ultra-fast vectorized sanitization and conversion of DataFrame to list of rows."""
            if df.empty:
                return []
            arr = df.to_numpy(dtype=object, na_value=None)
            for c_idx in range(arr.shape[1]):
                col_vals = arr[:, c_idx]
                first_val = next((v for v in col_vals if v is not None), None)
                if isinstance(first_val, str):
                    for r_idx in range(arr.shape[0]):
                        val = col_vals[r_idx]
                        if isinstance(val, str) and val and val[0] in ('=', '+', '-', '@'):
                            col_vals[r_idx] = "'" + val
            return arr.tolist()

        def _stream_sheet(sheet_name: str, df: pd.DataFrame, apply_status_color: bool = True):
            if df.empty:
                return None
            report(f"Writing {sheet_name} sheet", 0, len(df))
            ws = wb.add_worksheet(sheet_name)
            ws.freeze_panes(1, 0)

            cols = list(df.columns)
            num_c = len(cols)
            num_r = len(df)
            ws.autofilter(0, 0, num_r, num_c - 1)
            ws.write_row(0, 0, cols, fmt_header)

            if apply_status_color and 'Overall_Status' in cols:
                stat_idx = cols.index('Overall_Status')
                stat_letter = get_column_letter(stat_idx + 1)
                ws.conditional_format(
                    1, 0, num_r, num_c - 1,
                    {'type': 'formula', 'criteria': f'=${stat_letter}2="Matched"', 'format': fmt_green}
                )
                ws.conditional_format(
                    1, 0, num_r, num_c - 1,
                    {'type': 'formula', 'criteria': f'=AND(${stat_letter}2<>"", ${stat_letter}2<>"Matched")', 'format': fmt_red}
                )

            # Auto column widths: sample first 30 rows + header
            sample = df.iloc[:30]
            for c_i, c_n in enumerate(cols):
                m_l = len(str(c_n))
                for v in sample[c_n]:
                    if v is not None and not pd.isna(v):
                        l_v = len(str(v))
                        if l_v > m_l:
                            m_l = l_v
                ws.set_column(c_i, c_i, min(max(m_l + 3, 12), 60))

            chunk = 20000
            for r_i, row in enumerate(df.itertuples(index=False, name=None), start=1):
                clean = [
                    None if (v is None or pd.isna(v))
                    else (f"'{v}" if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v)
                    for v in row
                ]
                ws.write_row(r_i, 0, clean)
            rows = _prepare_df_for_stream(df)
            chunk = 25000
            for r_i, row in enumerate(rows, 1):
                ws.write_row(r_i, 0, row)
                if r_i % chunk == 0:
                    report(f"Writing {sheet_name}", r_i, num_r)

            report(f"Writing {sheet_name}", num_r, num_r)
            return ws

        def _clone_identical_sheet(source_ws, target_sheet_name: str, df: pd.DataFrame, apply_status_color: bool = True):
            """Instantly clones a worksheet's XML stream in <1s instead of re-streaming 100k+ rows."""
            report(f"Writing {target_sheet_name} sheet", 0, len(df))
            ws_target = wb.add_worksheet(target_sheet_name)
            ws_target.freeze_panes(1, 0)
            cols = list(df.columns)
            num_c = len(cols)
            num_r = len(df)
            ws_target.autofilter(0, 0, num_r, num_c - 1)
            ws_target.write_row(0, 0, cols, fmt_header)

            if apply_status_color and 'Overall_Status' in cols:
                stat_idx = cols.index('Overall_Status')
                stat_letter = get_column_letter(stat_idx + 1)
                ws_target.conditional_format(
                    1, 0, num_r, num_c - 1,
                    {'type': 'formula', 'criteria': f'=${stat_letter}2="Matched"', 'format': fmt_green}
                )
                ws_target.conditional_format(
                    1, 0, num_r, num_c - 1,
                    {'type': 'formula', 'criteria': f'=AND(${stat_letter}2<>"", ${stat_letter}2<>"Matched")', 'format': fmt_red}
                )

            sample = df.iloc[:30]
            for c_i, c_n in enumerate(cols):
                m_l = len(str(c_n))
                for v in sample[c_n]:
                    if v is not None and not pd.isna(v):
                        l_v = len(str(v))
                        if l_v > m_l:
                            m_l = l_v
                ws_target.set_column(c_i, c_i, min(max(m_l + 3, 12), 60))

            try:
                # Flush source worksheet
                source_ws._write_single_row(num_r + 1)
                source_ws.row_data_fh.flush()

                # Sync dimensions
                ws_target.dim_rowmin = source_ws.dim_rowmin
                ws_target.dim_rowmax = source_ws.dim_rowmax
                ws_target.dim_colmin = source_ws.dim_colmin
                ws_target.dim_colmax = source_ws.dim_colmax
                ws_target.previous_row = source_ws.previous_row

                # Fast file copy
                ws_target.row_data_fh.seek(0)
                with open(source_ws.row_data_filename, 'r', encoding='utf-8') as f_src:
                    shutil.copyfileobj(f_src, ws_target.row_data_fh)
                ws_target.row_data_fh.flush()
                report(f"Writing {target_sheet_name}", num_r, num_r)
                return ws_target
            except Exception:
                # Fallback to standard streaming if file copy fails for any reason
                return _stream_sheet(target_sheet_name, df, apply_status_color=apply_status_color)

        # ----------------------------------------------------------
        # 2. Recon Detailed Results
        # ----------------------------------------------------------
        ws_recon = _stream_sheet('Recon Detailed Results', results_df, apply_status_color=True)

        # ----------------------------------------------------------
        # 3. Per-type sheets (Sales, Collection)
        # ----------------------------------------------------------
        if 'Recon_Type' in results_df.columns:
            recon_types = results_df['Recon_Type'].dropna().unique()
            if len(recon_types) == 1 and ws_recon is not None:
                # When all rows are single type (e.g. 100% Sales or 100% Collection),
                # sheet is identical to Recon Detailed Results — clone instantly!
                single_type = str(recon_types[0])[:31] or 'Results'
                _clone_identical_sheet(ws_recon, single_type, results_df, apply_status_color=True)
            else:
                for recon_type, frame in results_df.groupby('Recon_Type', sort=False):
                    sheet_name = str(recon_type)[:31] or 'Results'
                    _stream_sheet(sheet_name, frame, apply_status_color=True)

        # ----------------------------------------------------------
        # 4. Raw sheets (exact uploaded or side-split data)
        # ----------------------------------------------------------
        if not sales_sap_side_df.empty:
            _stream_sheet('Sales - SAP Data', sales_sap_side_df, apply_status_color=False)
        if not sales_db_side_df.empty:
            _stream_sheet('Sales - DB Data', sales_db_side_df, apply_status_color=False)
        if not coll_sap_side_df.empty:
            _stream_sheet('Collection - SAP Data', coll_sap_side_df, apply_status_color=False)
        if not coll_bank_side_df.empty:
            _stream_sheet('Collection - Bank Data', coll_bank_side_df, apply_status_color=False)

        # ----------------------------------------------------------
        # 5. "Data Not Available in DB" sheet
        # ----------------------------------------------------------
        data_not_in_db = results_df.attrs.get('data_not_in_db') if hasattr(results_df, 'attrs') else None
        if data_not_in_db is not None and isinstance(data_not_in_db, pd.DataFrame) and not data_not_in_db.empty:
            _stream_sheet('data not available in DB', data_not_in_db, apply_status_color=False)

        report("Finalizing Excel workbook", 0, 1)
        wb.close()
        report("Excel export complete", 1, 1)



def save_styled_reconciliation_excel(
    save_path: str, kpi_summary: pd.DataFrame, results_df: pd.DataFrame
) -> None:
    """Helper wrapper for backward compatibility."""
    ExcelReportExporter().export(save_path, results_df, kpi_summary)
