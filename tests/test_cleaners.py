"""Unit tests for cleaners module."""
import pandas as pd
from src.core.cleaners import clean_id, clean_card, clean_number, parse_date_series

def test_clean_id():
    assert clean_id("AR-OMNI-1458247") == "1458247"
    assert clean_id("INV-2026-009988") == "009988"
    assert clean_id("1458247.0") == "1458247"
    assert clean_id(1458247) == "1458247"
    assert clean_id(None) == ""
    assert clean_id("") == ""

def test_clean_card():
    assert clean_card("CU2746253") == "2746253"
    assert clean_card("OM2746253") == "2746253"
    assert clean_card("DOM998811") == "998811"
    assert clean_card("BP12345") == "12345"
    assert clean_card("C4567") == "4567"
    assert clean_card("2746253.0") == "2746253"
    assert clean_card("2746253") == "2746253"
    assert clean_card(None) == ""

def test_clean_number():
    assert clean_number("1,234.56") == 1234.56
    assert clean_number("-500.00") == 500.00
    assert clean_number(250.75) == 250.75
    assert clean_number(None) == 0.0
    assert clean_number("invalid") == 0.0

def test_parse_date_series():
    s = pd.Series(["06/08/26", "2026-08-06", "invalid_date", None])
    res = parse_date_series(s, dayfirst=True)
    assert res[0] == "2026-08-06"
    assert res[1] == "2026-08-06"
    assert res[2] == "Missing Date"
    assert res[3] == "Missing Date"

