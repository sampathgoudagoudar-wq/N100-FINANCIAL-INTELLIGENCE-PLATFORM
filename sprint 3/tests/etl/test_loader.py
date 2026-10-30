import sqlite3
import pandas as pd
import pytest
from src.etl import loader

RAW = loader.ROOT / "data" / "raw"
pytestmark = pytest.mark.skipif(not RAW.exists(), reason="raw data not present")


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    d = tmp_path_factory.mktemp("load")
    info = loader.run(RAW, d / "t.db", d / "out")
    con = sqlite3.connect(d / "t.db")
    con.execute("PRAGMA foreign_keys = ON")
    yield info, con, d
    con.close()


def test_companies_count(result):
    assert result[1].execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 92


def test_fk_check_clean(result):
    assert result[0]["fk_violations"] == 0 and result[1].execute("PRAGMA foreign_key_check").fetchall() == []


def test_twelve_tables_loaded(result):
    names = {r[0] for r in result[1].execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == set(loader.LOAD_ORDER)


def test_no_critical_rejections(result):
    assert result[0]["audit"]["critical_rejections"].sum() == 0


def test_years_normalised(result):
    for t in ("profitandloss", "balancesheet", "cashflow", "financial_ratios"):
        bad = result[1].execute(f"SELECT COUNT(*) FROM {t} WHERE year NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'").fetchone()[0]
        assert bad == 0


def test_no_duplicate_company_year(result):
    n = result[1].execute("SELECT COUNT(*) FROM (SELECT 1 FROM cashflow GROUP BY company_id, year HAVING COUNT(*)>1)").fetchone()[0]
    assert n == 0


def test_stock_prices_rowcount(result):
    assert result[1].execute("SELECT COUNT(*) FROM stock_prices").fetchone()[0] == 5520


def test_audit_reconciles(result):
    a = result[0]["audit"]
    removed = a.excluded_ttm + a.excluded_out_of_universe + a.duplicates_removed + a.rejected_ticker + a.rejected_year
    assert (a.rows_in - removed == a.rows_out).all()


def test_audit_and_failure_files_written(result):
    out = result[2] / "out"
    assert (out / "load_audit.csv").exists() and (out / "validation_failures.csv").exists()


def test_atgl_typo_recovered(result):
    assert result[1].execute("SELECT COUNT(*) FROM cashflow WHERE company_id='ATGL'").fetchone()[0] == 7


def test_analysis_parsed(result):
    r = result[1].execute("SELECT period, roe_pct FROM analysis WHERE company_id='TCS' AND period='TTM'").fetchone()
    assert r == ("TTM", 52.0)


def test_company_name_newlines_stripped(result):
    assert result[1].execute("SELECT COUNT(*) FROM companies WHERE company_name LIKE '%'||char(10)||'%'").fetchone()[0] == 0


def test_fk_enforced_on_insert(result):
    with pytest.raises(sqlite3.IntegrityError):
        result[1].execute("INSERT INTO sectors(company_id, broad_sector) VALUES ('NOPE','X')")


def test_read_sheet_header_fallback():
    df = loader.read_sheet(RAW / "sectors.xlsx", 1)   # wrong header on purpose
    assert "company_id" in df.columns
