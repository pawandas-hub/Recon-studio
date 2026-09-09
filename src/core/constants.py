"""Constants, column mapping dictionaries, and style presets for reconciliation."""

# Format 1 (Standard / Legacy SAP vs DB) Column Candidates
FORMAT1_BU_COLS = {
    'ref': ['Ref. 1', 'Ref1', 'Ref 1', 'Reference', 'DocNum', 'RefId'],
    'ref': ['Ref. 1 (Header)', 'Ref 1 (Header)', 'Ref. 1', 'Ref1', 'Ref 1', 'Reference', 'DocNum', 'RefId'],
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
    'ref': ['Ref. 2 (Header)', 'Ref 2 (Header)', 'Ref. 2', 'Ref 2', 'Ref.2', 'Ref2', 'Origin No.', 'Ref. 1 (Header)', 'Ref. 1', 'Ref1', 'Reference', 'DocNum', 'RefId'],
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

# Format 3 (AFC / Sales with Freight & GRN) Column Candidates
FORMAT3_BU_COLS = {
    'ref': ['Ref. 2', 'Ref 2', 'Ref.2', 'Ref2', 'Origin No.', 'InvoiceId', 'Invoice ID', 'Reference'],
    'grn': ['Ref. 1', 'Ref 1', 'Ref.1', 'Ref1', 'GRNID', 'GRN ID', 'GRN_ID'],
    'ref': ['Ref. 2 (Header)', 'Ref 2 (Header)', 'Ref. 2', 'Ref 2', 'Ref.2', 'Ref2', 'Origin No.', 'InvoiceId', 'Invoice ID', 'Reference'],
    'grn': ['Ref. 1 (Header)', 'Ref 1 (Header)', 'Ref. 1', 'Ref 1', 'Ref.1', 'Ref1', 'GRNID', 'GRN ID', 'GRN_ID'],
    'date': ['Posting Date', 'PostingDate', 'DocDate', 'Date'],
    'amt': ['Deb./Cred. (LC)', 'Deb/Cred (LC)', 'Debit/Credit (LC)', 'C/D (LC)', 'C/D(LC)', 'CD LC', 'Debit (LC)', 'Amount (LC)', 'LC Amount', 'TAXABLEAMOUNT'],
    'acc': ['Offset Account', 'OffsetAccount', 'Offset Acct', 'Account', 'CardCode'],
    'unit': ['Business Unit', 'BU', 'Branch', 'Unit', 'COGSCostingCode']
}

FORMAT3_DB_COLS = {
    'ref': ['InvoiceId', 'Invoice ID', 'Invoice_Id', 'InvoiceID', 'Invoice_Number', 'Invoice Number', 'RefId'],
    'grn': ['GRNID', 'GRN ID', 'GRN_ID', 'GRNId', 'GRN_No', 'GRN Number', 'GRN'],
    'date': ['DocDate', 'Doc Date', 'Doc_Date', 'Invoice_Date', 'InvoiceDate', 'Date', 'Posting Date'],
    'sales': ['Sales', 'Gross_Sales', 'Gross Sales', 'Sales_Amount', 'SubTotal', 'Total Sales', 'Amount', 'TotalValue_After_Disc', 'TAXABLEAMOUNT'],
    'discount': ['Discounts', 'Discount', 'Total_Discount', 'Total Discount', 'Item_Discount'],
    'upi_discount': ['UPI_Discount', 'UPIDiscount', 'UPI Discount', 'UPI_Disc'],
    'wallet_discount': ['Wallet_Discount', 'WalletDiscount', 'Wallet Discount', 'Wallet_Disc'],
    'packing': ['packingcharges', 'packing_charges', 'packing charges', 'packing_charge', 'packingcharge', 'PackingCharges', 'Packing Charges'],
    'freight': ['Freight', 'Freight_Amount', 'FreightAmount', 'Freight Charges', 'Freight_Charges', 'FreightCharge'],
    'card': ['CardCode', 'Card Code', 'Card_Code', 'CustomerCode', 'Customer_Id', 'Customer Id', 'Offset Account'],
    'unit': ['SO_Project', 'COGSCostingCode', 'Business Unit', 'BU', 'Branch']
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

