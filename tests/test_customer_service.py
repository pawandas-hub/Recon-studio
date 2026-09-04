"""Unit tests for Customer Mapping Service."""
import pandas as pd
from src.services.customer_service import CustomerMappingService

def test_customer_mapping_lookup():
    df_map = pd.DataFrame({
        "Customer_Id": ["2765805", "2746183", "2036863"],
        "SAP Code": ["CU511924", "CU1682875", "CU2036863"]
    })
    service = CustomerMappingService.from_dataframe(df_map)

    assert service.get_mapped_sap_code("2765805") == "511924"
    assert service.get_mapped_sap_code("2746183") == "1682875"
    assert service.get_mapped_sap_code("2036863") == "2036863"
    # Unmapped customer returns original cleaned ID
    assert service.get_mapped_sap_code("9999999") == "9999999"
    assert service.get_mapped_sap_code("Missing in Sales/DB") == "Missing in Sales/DB"

def test_customer_mapping_load_from_file(customer_map_file):
    service = CustomerMappingService.load_from_sources([customer_map_file])
    assert len(service.mapping) > 0
    # In Retailer customer Id.xlsx, 2765805 maps to CU511924 (511924)
    assert service.get_mapped_sap_code("2765805") == "511924"

