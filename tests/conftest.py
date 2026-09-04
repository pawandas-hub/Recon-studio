"""Pytest configuration and shared fixtures."""
import os
import sys
import pytest

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

@pytest.fixture
def project_root():
    return PROJECT_ROOT

@pytest.fixture
def test_data_dir():
    return os.path.join(PROJECT_ROOT, "test_data")

@pytest.fixture
def sap_ledger_file(test_data_dir):
    return os.path.join(test_data_dir, "retailer", "4020101001.xls")

@pytest.fixture
def retailer_file(test_data_dir):
    return os.path.join(test_data_dir, "retailer", "RetailerFnV.xlsx")

@pytest.fixture
def customer_map_file(test_data_dir):
    return os.path.join(test_data_dir, "retailer", "Retailer customer Id.xlsx")

