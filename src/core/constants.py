"""Constants, column mapping dictionaries, and style presets for reconciliation."""

# Format 1 (Standard / Legacy SAP vs DB) Column Candidates
FORMAT1_BU_COLS = {
    'ref': ['Ref. 1', 'Ref1', 'Ref 1', 'Reference', 'DocNum', 'RefId'],
    'date': ['Posting Date', 'DocDate', 'Date'],
    'amt': ['TAXABLEAMOUNT', 'Gross_Sale_value', 'C/D (LC)', 'C/D(LC)', 'CD LC', 'Debit (LC)', 'LineTotal', 'DocTotal', 'Debit', 'Amount (LC)', 'LC Amount'],
    'acc': ['Offset Account', 'OffsetAccount', 'Account', 'CardCode'],
    'unit': ['Business Unit', 'BU', 'Branch', 'Unit', 'COGSCostingCode']
}

FORMAT1_DB_COLS = {
    'ref': ['RefId', 'Ref Id', 'Ref. 1', 'DocNum', 'Reference'],
    'date': ['DocDate', 'Posting Date', 'Date'],
    'taxable': ['TAXABLEAMOUNT', 'TaxableAmount', 'Taxable Amount', 'C/D (LC)', 'C/D(LC)', 'Debit (LC)', 'LineTotal', 'DocTotal'],
    'card': ['CardCode', 'Card Code', 'CustomerCode', 'Offset Account', 'OffsetAccount'],
    'unit': ['COGSCostingCode', 'Business Unit', 'BU', 'Branch']
}

# Format 2 (Retailer / FnV vs SAP) Column Candidates
FORMAT2_BU_COLS = {
    'ref': ['Ref. 2', 'Ref 2', 'Ref.2', 'Ref2', 'Origin No.', 'Ref. 1', 'Ref1', 'Reference', 'DocNum', 'RefId'],
    'date': ['Posting Date', 'PostingDate', 'DocDate', 'Date'],
    'amt': ['C/D (LC)', 'C/D(LC)', 'CD LC', 'Debit (LC)', 'Amount (LC)', 'LC Amount', 'TAXABLEAMOUNT', 'Gross_Sale_value', 'DocTotal', 'LineTotal'],
    'acc': ['Offset Account', 'OffsetAccount', 'Account', 'CardCode'],
    'unit': ['Business Unit', 'BU', 'Branch', 'Unit', 'COGSCostingCode']
}

FORMAT2_DB_COLS = {
    'ref': ['Invoice_Number', 'Invoice_ID', 'Invoice Number', 'Invoice ID', 'Invoice_Link', 'RefId', 'Ref Id', 'Ref. 2', 'Ref. 1', 'DocNum'],
    'date': ['Invoice_Date', 'InvoiceDate', 'Sale_Date', 'SaleDate', 'DocDate', 'Posting Date', 'Date'],
    'taxable': ['TotalValue_After_Disc', 'TotalValue_After_Discount', 'TotalValue', 'TAXABLEAMOUNT', 'TaxableAmount', 'Gross_Sale_value', 'DocTotal', 'LineTotal', 'C/D (LC)'],
    'card': ['Customer_Id', 'Customer Id', 'CustomerId', 'Customer_Name', 'CardCode', 'Card Code', 'CustomerCode', 'Offset Account'],
    'unit': ['SO_Project', 'COGSCostingCode', 'Business Unit', 'BU', 'Branch', 'Shipping State', 'Shipping City']
}

# Customer Mapping Candidates
CUSTOMER_MAP_COLS = {
    'cust_id': ['Customer_Id', 'CustomerId', 'Customer Id', 'CustId'],
    'sap_code': ['SAP Code', 'SAPCode', 'SAP Customer Code', 'SAP_Code']
}

# Style Configuration
STYLE_CONFIG = {
    'header_fill': '1F4E78',      # Navy Blue
    'header_font_color': 'FFFFFF', # White
    'red_fill': 'FFD6D6',         # Soft Red
    'red_font_color': '9C0006',    # Dark Red
    'green_fill': 'D6FFD6',       # Soft Green
    'green_font_color': '006100',  # Dark Green
    'border_color': 'DDDDDD'
}

