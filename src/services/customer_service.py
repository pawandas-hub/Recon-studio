"""Customer Master Mapping Service."""
import os
from typing import Dict, List, Optional
import pandas as pd
from ..core.cleaners import clean_card
from ..core.detector import find_best_col, is_customer_mapping_table
from ..core.constants import CUSTOMER_MAP_COLS
from ..readers.file_reader import read_file_tables

class CustomerMappingService:
    """Manages loading and resolving Customer ID <-> SAP Code mappings."""

    def __init__(self, mapping_dict: Optional[Dict[str, str]] = None):
        self._map: Dict[str, str] = mapping_dict or {}

    @property
    def mapping(self) -> Dict[str, str]:
        return self._map

    def get_mapped_sap_code(self, customer_id: str) -> str:
        """Looks up the mapped SAP code for a given customer ID, fallback to original ID if not found."""
        if not customer_id or customer_id == 'Missing in Sales/DB':
            return 'Missing in Sales/DB'
        clean_cid = clean_card(customer_id)
        return self._map.get(clean_cid, clean_cid)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "CustomerMappingService":
        """Builds mapping service from a DataFrame (vectorised — no iterrows)."""
        cust_col = find_best_col(df, CUSTOMER_MAP_COLS['cust_id'])
        sap_col = find_best_col(df, CUSTOMER_MAP_COLS['sap_code'])
        if not cust_col or not sap_col:
            return cls({})
        tmp = df[[cust_col, sap_col]].dropna()
        tmp = tmp[tmp[cust_col].astype(str).str.strip() != ""]
        tmp = tmp[tmp[sap_col].astype(str).str.strip() != ""]
        tmp["_cid"] = tmp[cust_col].apply(clean_card)
        tmp["_sap"] = tmp[sap_col].apply(clean_card)
        tmp = tmp[tmp["_cid"] != ""][tmp["_sap"] != ""]
        map_dict = dict(zip(tmp["_cid"], tmp["_sap"]))
        return cls(map_dict)

    @classmethod
    def load_from_sources(cls, files: Optional[List[str]] = None) -> "CustomerMappingService":
        """
        Discovers and loads customer mapping from passed files or known workspace paths.
        """
        mapping_df = None

        # 1. Search in passed files
        if files:
            for f in files:
                try:
                    fname = os.path.basename(f).lower()
                    if 'customer' in fname and ('id' in fname or 'code' in fname or 'map' in fname):
                        df_test, _ = read_file_tables(f)
                        if is_customer_mapping_table(df_test):
                            mapping_df = df_test
                            break
                except Exception:
                    continue

        # 2. Search locally in workspace / test directory
        if mapping_df is None:
            candidate_paths = [
                'Retailer customer Id.xlsx',
                'Retailer customer Id.xls',
                'test_data/Retailer customer Id.xlsx',
                'test_data/Retailer customer Id.xls',
                'test_data/retailer/Retailer customer Id.xlsx',
                'test_data/retailer/Retailer customer Id.xls',
                os.path.join(os.path.dirname(__file__), '..', '..', 'Retailer customer Id.xlsx'),
                os.path.join(os.path.dirname(__file__), '..', '..', 'test_data', 'Retailer customer Id.xlsx'),
                os.path.join(os.path.dirname(__file__), '..', '..', 'test_data', 'retailer', 'Retailer customer Id.xlsx')
            ]
            for p in candidate_paths:
                if p and os.path.exists(p):
                    try:
                        df_test, _ = read_file_tables(p)
                        if is_customer_mapping_table(df_test):
                            mapping_df = df_test
                            break
                    except Exception:
                        continue

        if mapping_df is not None:
            return cls.from_dataframe(mapping_df)
        return cls({})

def load_customer_mapping(files: Optional[List[str]] = None) -> Dict[str, str]:
    """Helper functional wrapper for backward compatibility."""
    service = CustomerMappingService.load_from_sources(files)
    return service.mapping

