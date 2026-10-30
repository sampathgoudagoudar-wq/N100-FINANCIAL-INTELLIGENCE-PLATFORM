"""14 DQ rule unit tests + integration checks on the cleaned dataset."""
import numpy as np
import pandas as pd
import pytest

from src.dq import rules as R


def df(**cols):
    return pd.DataFrame(cols)


# ── unit tests: each rule flags a bad row and passes a good one ───────────────
def test_dq01_company_pk_uniqueness():
    assert len(R.dq01_company_pk_unique(df(id=["A", "B", "A"]))) == 2
    assert R.dq01_company_pk_unique(df(id=["A", "B"])).empty


def test_dq02_annual_pk_uniqueness():
    bad = df(company_id=["A", "A", "B"], year=[2024, 2024, 2024])
    assert len(R.dq02_annual_pk_unique(bad)) == 2
    assert R.dq02_annual_pk_unique(bad.iloc[1:]).empty


def test_dq03_fk_integrity():
    co = df(id=["A", "B"])
    child = df(company_id=["A", "ZZZ"])
    assert R.dq03_fk_integrity(child, co)["company_id"].tolist() == ["ZZZ"]
    assert R.dq03_fk_integrity(child.iloc[:1], co).empty


def test_dq04_balance_sheet_balance():
    bs = df(total_assets=[1000, 1000], total_liabilities=[1005, 1100])   # 0.5 % ok, 10 % bad
    assert R.dq04_balance_sheet_balances(bs).index.tolist() == [1]


def test_dq05_opm_cross_check():
    pl = df(sales=[1000, 1000], operating_profit=[200, 200], opm_percentage=[20.5, 25.0])
    assert R.dq05_opm_cross_check(pl).index.tolist() == [1]


def test_dq06_positive_sales_excludes_banks():
    pl = df(company_id=["X", "BANK"], sales=[0, -5])
    assert R.dq06_positive_sales(pl, {"BANK"})["company_id"].tolist() == ["X"]


def test_dq07_year_format():
    d = df(year_std=["2024-03", "Mar-24", "2024"])
    assert R.dq07_year_format(d).index.tolist() == [1, 2]


def test_dq08_ticker_format():
    d = df(company_id=["TCS", " tcs", "A", "ABCDEFGHIJKLM"])
    assert R.dq08_ticker_format(d).index.tolist() == [1, 2, 3]


def test_dq09_net_cash_check():
    cf = df(operating_activity=[100, 100], investing_activity=[-40, -40], financing_activity=[-30, -30],
            net_cash_flow=[35, 60])                                         # |35-30|=5 ok, 30 bad
    assert R.dq09_net_cash_check(cf).index.tolist() == [1]


def test_dq10_non_negative_fixed_assets():
    assert R.dq10_non_negative_fixed_assets(df(fixed_assets=[5, -1, 0])).index.tolist() == [1]


def test_dq11_tax_rate_range():
    assert R.dq11_tax_rate_range(df(tax_percentage=[0, 25, 60, 61, -1])).index.tolist() == [3, 4]


def test_dq12_dividend_payout_cap():
    assert R.dq12_dividend_payout_cap(df(dividend_payout=[50, 200, 201])).index.tolist() == [2]


def test_dq14_eps_sign_consistency():
    pl = df(net_profit=[100, 100, -5], eps=[5, -1, -2])
    assert R.dq14_eps_sign_consistency(pl).index.tolist() == [1]


def test_dq16_coverage():
    pl = df(company_id=["A"] * 5 + ["B"] * 3, year=list(range(2020, 2025)) + [2022, 2023, 2024])
    out = R.dq16_coverage(pl, pl, pl)
    assert set(out["company_id"]) == {"B"} and len(out) == 3


# ── integration: critical rules hold on the cleaned dataset ───────────────────
@pytest.fixture(scope="module")
def cleaned():
    from src.data.loader import load_clean
    return load_clean()[0]


@pytest.mark.parametrize("rule", ["DQ-01", "DQ-02", "DQ-03", "DQ-07", "DQ-08"])
def test_critical_rules_clean_after_etl(cleaned, rule):
    summary = R.run_all(cleaned).set_index("rule")
    assert summary.loc[rule, "violations"] == 0, f"{rule} still has violations after cleaning"
