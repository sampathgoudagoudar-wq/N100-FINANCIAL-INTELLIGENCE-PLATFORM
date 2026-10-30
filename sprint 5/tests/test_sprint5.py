"""Unit tests for Sprint 5 logic."""
import numpy as np
import pandas as pd

from src.analytics.cashflow_kpis import capex_label, cfo_label
from src.analytics.ratios import cagr
from src.etl.clean import normalize_year
from src.nlp.parser import parse_text
from src.nlp.pros_cons_generator import strict_trend, trailing_run
from src.reports.portfolio_report import trend


def test_parse_spec_pattern():
    assert parse_text("10 Years:     21%") == (10, 21.0)
    assert parse_text("5 Years          14%") == (5, 14.0)


def test_parse_negative_and_failures():
    assert parse_text("1 Year: -2%") == (1, -2.0)
    assert parse_text("TTM:            43%") is None
    assert parse_text("Last Year: 12%") is None


def test_normalize_year():
    assert normalize_year("Mar 2023") == "2023-03"
    assert normalize_year("Mar-23") == "2023-03"
    assert normalize_year("Dec 2012") == "2012-12"
    assert normalize_year("garbage") == "PARSE_ERROR"


def test_cagr_cases():
    y = pd.Series([2019, 2020, 2021, 2022, 2023, 2024])
    v, f = cagr(pd.Series([100, 110, 121, 133.1, 146.41, 161.051]), y, 5)
    assert f == "OK" and abs(v - 10.0) < 0.01
    assert cagr(pd.Series([-100, 1, 2, 3, 4, 200]), y, 5) == (None, "TURNAROUND")
    assert cagr(pd.Series([100, 1, 2, 3, 4, -5]), y, 5) == (None, "DECLINE_TO_LOSS")
    assert cagr(pd.Series([1, 2]), pd.Series([2023, 2024]), 5) == (None, "INSUFFICIENT")


def test_labels():
    assert cfo_label(1.2) == "High Quality" and cfo_label(0.7) == "Moderate" and cfo_label(0.2) == "Accrual Risk"
    assert capex_label(2) == "Asset Light" and capex_label(5) == "Moderate" and capex_label(9) == "Capital Intensive"


def test_runs_and_trends():
    assert trailing_run([1, 25, 30, 22], lambda v: v > 20) == 3
    assert strict_trend([1, 2, 3, 4], 3, up=True) and not strict_trend([1, 2, 2, 4], 3, up=True)
    assert trend(10.1, 10.0, True) == "flat" and trend(12, 10, True) == "up" and trend(12, 10, False) == "down"
    assert trend(np.nan, 1, True) == "na"
