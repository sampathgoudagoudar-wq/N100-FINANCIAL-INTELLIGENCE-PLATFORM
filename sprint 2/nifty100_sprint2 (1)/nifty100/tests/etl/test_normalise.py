import math
import pytest
from src.etl.normaliser import (MISSING, PARSE_ERROR, TTM, is_valid_ticker, normalize_ticker,
                                normalize_year, parse_growth_text)

YEAR_CASES = [
    ("Mar-23", "2023-03"), ("Mar 23", "2023-03"), ("March-2023", "2023-03"), ("Mar 2023", "2023-03"),
    (2023, "2023-03"), ("2023", "2023-03"), (2023.0, "2023-03"), ("FY23", "2023-03"), ("FY2023", "2023-03"),
    ("Dec-22", "2022-12"), ("Dec 2012", "2012-12"), ("Jun-23", "2023-06"), ("Sep 2024", "2024-09"),
    ("2023-03", "2023-03"), ("  Mar 2024  ", "2024-03"), ("Mar 2016 9m", "2016-03"), ("Mar 2023 15", "2023-03"),
    ("MAR-13", "2013-03"), ("TTM", TTM), ("ttm", TTM),
    ("garbage", PARSE_ERROR), ("", PARSE_ERROR), (None, PARSE_ERROR), (2024.5, PARSE_ERROR),
    (float("nan"), PARSE_ERROR), ("2023-13", PARSE_ERROR), ("Foo-23", PARSE_ERROR), ("Mar", PARSE_ERROR),
]


@pytest.mark.parametrize("raw,expected", YEAR_CASES)
def test_normalize_year(raw, expected):
    assert normalize_year(raw) == expected


TICKER_CASES = [
    ("TCS", "TCS"), ("tcs", "TCS"), ("  TCS  ", "TCS"), ("\tTcs\n", "TCS"), ("BAJAJ-AUTO", "BAJAJ-AUTO"),
    ("bajaj-auto", "BAJAJ-AUTO"), ("M&M", "M&M"), ("m&m", "M&M"), ("\xa0INFY", "INFY"), ("hdfcbank ", "HDFCBANK"),
    ("", MISSING), ("   ", MISSING), (None, MISSING), (float("nan"), MISSING), ("ULTRACEMCO", "ULTRACEMCO"),
    ("L&T", "L&T"), ("  m&m", "M&M"), ("Tatamotors", "TATAMOTORS"), ("sbin", "SBIN"), ("ITC", "ITC"),
]


@pytest.mark.parametrize("raw,expected", TICKER_CASES)
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("t,ok", [("TCS", True), ("ITC", True), ("A", False), ("ABCDEFGHIJKLM", False),
                                  ("ABCDEFGHIJKL", True), (MISSING, False)])
def test_ticker_length(t, ok):
    assert is_valid_ticker(t) is ok


@pytest.mark.parametrize("raw,expected", [
    ("10 Years: 21%", ("10Y", 21.0)), ("10 Years:     15%", ("10Y", 15.0)), ("5 Years          14%", ("5Y", 14.0)),
    ("TTM:            43%", ("TTM", 43.0)), ("1 Year:        -2%", ("1Y", -2.0)),
    ("Last Year:      12%", ("LY", 12.0)), ("", (None, None)), (None, (None, None)), ("n/a", (None, None)),
])
def test_parse_growth_text(raw, expected):
    assert parse_growth_text(raw) == expected
