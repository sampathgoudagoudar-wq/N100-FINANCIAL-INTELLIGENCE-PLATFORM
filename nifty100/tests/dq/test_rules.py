import pandas as pd
from src.etl import validator as V


def pl(**kw):
    base = dict(source_id=1, company_id="TCS", year="2023-03", sales=1000.0, expenses=800.0,
                operating_profit=200.0, opm_percentage=20.0, tax_percentage=25.0, net_profit=100.0,
                eps=5.0, dividend_payout=40.0)
    base.update(kw)
    return pd.DataFrame([base])


def test_dq01_duplicate_company_detected():
    ok, f = V.dq01_company_pk(pd.DataFrame({"id": ["TCS", "TCS", "INFY"]}))
    assert not ok and len(f) == 2 and f[0]["severity"] == "CRITICAL"


def test_dq01_unique_company_ok():
    ok, f = V.dq01_company_pk(pd.DataFrame({"id": ["TCS", "INFY"]}))
    assert ok and f == []


def test_dq02_keeps_last_and_logs():
    df = pd.DataFrame({"source_id": [1, 2], "company_id": ["A", "A"], "year": ["2020-03"] * 2, "x": [1.0, 2.0]})
    out, f, n = V.dq02_dedupe(df, "t", ["company_id", "year"])
    assert n == 1 and out["x"].iloc[0] == 2.0 and f[0]["status"] == "FLAGGED"


def test_dq02_identical_dups_resolved_not_flagged():
    df = pd.DataFrame({"source_id": [1, 2], "company_id": ["A", "A"], "year": ["2020-03"] * 2, "x": [1.0, 1.0]})
    _, f, _ = V.dq02_dedupe(df, "t", ["company_id", "year"])
    assert f[0]["status"] == "RESOLVED"


def test_dq02_zero_filled_duplicate_never_wins():
    df = pd.DataFrame({"source_id": [1, 2], "company_id": ["A", "A"], "year": ["2020-03"] * 2,
                       "cfo": [155.0, 0.0], "cfi": [-144.0, 0.0]})
    out, _, _ = V.dq02_dedupe(df, "t", ["company_id", "year"])
    assert out["cfo"].iloc[0] == 155.0


def test_dq03_orphans_removed():
    df = pd.DataFrame({"company_id": ["TCS", "WIPRO"], "year": ["2023-03"] * 2})
    out, f, n = V.dq03_fk(df, "t", {"TCS"})
    assert list(out.company_id) == ["TCS"] and n == 1 and f[0]["rule_id"] == "DQ-03"


def test_dq04_flags_imbalance():
    bs = pd.DataFrame([dict(source_id=1, company_id="A", year="2020-03", total_assets=1000.0, total_liabilities=1020.0)])
    f, _ = V.dq04_bs_balance(bs)
    assert len(f) == 1 and f[0]["rule_id"] == "DQ-04"


def test_dq04_within_tolerance_counts_strict_info():
    bs = pd.DataFrame([dict(source_id=1, company_id="A", year="2020-03", total_assets=1000.0, total_liabilities=1005.0)])
    f, strict = V.dq04_bs_balance(bs)
    assert f == [] and strict == 1


def test_dq05_flags_opm_mismatch():
    assert len(V.dq05_opm(pl(opm_percentage=30.0))) == 1


def test_dq05_passes_when_consistent():
    assert V.dq05_opm(pl()) == []


def test_dq06_zero_sales_flagged_non_bank():
    assert len(V.dq06_positive_sales(pl(sales=0.0), bank_ids=set())) == 1


def test_dq06_banks_exempt():
    assert V.dq06_positive_sales(pl(sales=0.0), bank_ids={"TCS"}) == []


def test_dq07_rejects_unparseable_and_excludes_ttm():
    df = pd.DataFrame({"company_id": ["A"] * 4, "year": ["Mar-23", "TTM", "garbage", 2024]})
    out, f, bad, ttm = V.dq07_years(df, "t")
    assert list(out.year) == ["2023-03", "2024-03"] and bad == 1 and ttm == 1
    assert V.check_year_format(out.year)


def test_dq08_normalises_and_rejects_short_ticker():
    df = pd.DataFrame({"company_id": [" tcs ", "X", None]})
    out, f, n = V.dq08_tickers(df, "t")
    assert list(out.company_id) == ["TCS"] and n == 2


def test_dq08_known_typo_remapped():
    out, f, _ = V.dq08_tickers(pd.DataFrame({"company_id": ["AGTL"]}), "t")
    assert out.company_id.iloc[0] == "ATGL" and f[0]["status"] == "RESOLVED"


def test_dq09_recomputes_net_cash():
    cf = pd.DataFrame([dict(source_id=1, company_id="A", year="2020-03", operating_activity=100.0,
                            investing_activity=-50.0, financing_activity=-20.0, net_cash_flow=500.0)])
    out, f = V.dq09_net_cash(cf)
    assert out.net_cash_flow.iloc[0] == 30.0 and len(f) == 1


def test_dq09_tolerance_10cr():
    cf = pd.DataFrame([dict(source_id=1, company_id="A", year="2020-03", operating_activity=100.0,
                            investing_activity=-50.0, financing_activity=-20.0, net_cash_flow=38.0)])
    assert V.dq09_net_cash(cf)[1] == []


def test_dq10_negative_fixed_assets_coerced():
    bs = pd.DataFrame([dict(source_id=1, company_id="A", year="2020-03", fixed_assets=-5.0)])
    out, f = V.dq10_fixed_assets(bs)
    assert out.fixed_assets.iloc[0] == 0 and len(f) == 1


def test_dq11_tax_out_of_range():
    assert len(V.dq11_tax(pl(tax_percentage=75.0))) == 1 and len(V.dq11_tax(pl(tax_percentage=-3.0))) == 1
    assert V.dq11_tax(pl()) == []


def test_dq12_dividend_cap():
    assert len(V.dq12_dividend(pl(dividend_payout=250.0))) == 1 and V.dq12_dividend(pl(dividend_payout=200.0)) == []


def test_dq13_skipped_by_default():
    f = V.dq13_urls(pd.DataFrame({"annual_report": ["http://x"]}))
    assert f[0]["severity"] == "INFO"


def test_dq14_eps_sign():
    assert len(V.dq14_eps(pl(eps=-1.0))) == 1 and V.dq14_eps(pl(net_profit=-5.0, eps=-1.0)) == []


def test_dq16_short_history_flagged():
    comp = pd.DataFrame({"id": ["A", "B"]})
    t = pd.DataFrame({"company_id": ["A"] * 6 + ["B"] * 2, "year": [f"20{y}-03" for y in range(10, 16)] + ["2020-03", "2021-03"]})
    f = V.dq16_coverage(comp, {"profitandloss": t})
    assert [x["company_id"] for x in f] == ["B"]


def test_dq16_missing_company_reports_zero():
    f = V.dq16_coverage(pd.DataFrame({"id": ["C"]}), {"cashflow": pd.DataFrame({"company_id": [], "year": []})})
    assert "0 year" in f[0]["detail"]
