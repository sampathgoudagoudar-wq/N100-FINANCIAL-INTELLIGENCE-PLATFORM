import sqlite3
import pandas as pd
import pytest
from src.analytics import edge_cases, engine

pytestmark = pytest.mark.skipif(not engine.DB.exists(), reason="run make load && make ratios first")


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(engine.DB)
    yield c
    c.close()


def test_row_count_at_least_1100(con):
    assert con.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0] >= 1100


def test_all_92_companies_present(con):
    assert con.execute("SELECT COUNT(DISTINCT company_id) FROM financial_ratios").fetchone()[0] == 92


def test_no_null_only_columns(con):
    df = pd.read_sql("SELECT * FROM financial_ratios", con)
    assert [c for c in df.columns if df[c].isna().all()] == []


def test_required_kpi_columns_exist(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(financial_ratios)")}
    need = {"net_profit_margin_pct", "operating_profit_margin_pct", "return_on_equity_pct", "debt_to_equity",
            "interest_coverage", "asset_turnover", "free_cash_flow_cr", "capex_cr", "earnings_per_share",
            "book_value_per_share", "dividend_payout_ratio_pct", "total_debt_cr", "cash_from_operations_cr",
            "revenue_cagr_5yr", "pat_cagr_5yr", "eps_cagr_5yr", "composite_quality_score", "revenue_cagr_5yr_flag"}
    assert need <= cols


def test_foreign_keys_clean(con):
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_debt_free_icr_is_null_with_label(con):
    n = con.execute("SELECT COUNT(*) FROM financial_ratios WHERE icr_label='Debt Free' AND interest_coverage IS NOT NULL").fetchone()[0]
    assert n == 0 and con.execute("SELECT COUNT(*) FROM financial_ratios WHERE icr_label='Debt Free'").fetchone()[0] > 0


def test_high_leverage_never_set_for_financials(con):
    n = con.execute("""SELECT COUNT(*) FROM financial_ratios f JOIN sectors s USING(company_id)
                       WHERE s.broad_sector='Financials' AND f.high_leverage_flag=1""").fetchone()[0]
    assert n == 0


def test_cagr_null_always_has_reason_flag(con):
    n = con.execute("SELECT COUNT(*) FROM financial_ratios WHERE revenue_cagr_5yr IS NULL AND revenue_cagr_5yr_flag='OK'").fetchone()[0]
    assert n == 0


def test_composite_score_within_0_100(con):
    lo, hi = con.execute("SELECT MIN(composite_quality_score), MAX(composite_quality_score) FROM financial_ratios").fetchone()
    assert 0 <= lo and hi <= 100


def test_capital_allocation_csv_covers_every_cashflow_row(con):
    df = pd.read_csv(engine.OUT / "capital_allocation.csv")
    assert list(df.columns) == ["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"]
    assert len(df) == con.execute("SELECT COUNT(*) FROM cashflow").fetchone()[0]


def test_edge_log_every_entry_categorised_and_explained(con):
    lines = [l for l in (engine.OUT / "ratio_edge_cases.log").read_text().splitlines() if l and not l.startswith("#")]
    assert lines
    for l in lines:
        cat, check, company, detail, why = [x.strip() for x in l.split(" | ")]
        assert cat in {edge_cases.DSI, edge_cases.VER, edge_cases.FORM} and why


def test_spot_check_passes():
    from src.analytics import spotcheck
    assert spotcheck.run() is True


def test_screener_preview_count_in_range():
    from src.analytics import screener_preview
    hit, _ = screener_preview.run()
    assert 15 <= len(hit) <= 50
