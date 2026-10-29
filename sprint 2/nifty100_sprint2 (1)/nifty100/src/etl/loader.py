"""Excel -> normalise -> validate -> SQLite loader (Sprint 1, Days 02/04/05).

Run:  python -m src.etl.loader            (full load)
      python -m src.etl.loader --validate-only
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import validator as V
from .normaliser import parse_growth_text

log = logging.getLogger("nifty100.etl")
ROOT = Path(__file__).resolve().parents[2]

# name -> (file, header row, rename map)
CORE_HEADER = 1   # row 0 is a merged title/metadata banner
SPECS = {
    "companies":        dict(file="companies.xlsx",        header=CORE_HEADER),
    "profitandloss":    dict(file="profitandloss.xlsx",    header=CORE_HEADER, rename={"id": "source_id"}),
    "balancesheet":     dict(file="balancesheet.xlsx",     header=CORE_HEADER, rename={"id": "source_id"}),
    "cashflow":         dict(file="cashflow.xlsx",         header=CORE_HEADER, rename={"id": "source_id"}),
    "analysis":         dict(file="analysis.xlsx",         header=CORE_HEADER),
    "documents":        dict(file="documents.xlsx",        header=CORE_HEADER,
                             rename={"id": "source_id", "Year": "year", "Annual_Report": "annual_report"}),
    "prosandcons":      dict(file="prosandcons.xlsx",      header=CORE_HEADER),
    "sectors":          dict(file="sectors.xlsx",          header=0, rename={"id": "source_id"}),
    "stock_prices":     dict(file="stock_prices.xlsx",     header=0, rename={"id": "source_id"}),
    "market_cap":       dict(file="market_cap.xlsx",       header=0, rename={"id": "source_id"}),
    "financial_ratios_source": dict(file="financial_ratios.xlsx", header=0, rename={"id": "source_id"}),
    "peer_groups":      dict(file="peer_groups.xlsx",      header=0, rename={"id": "source_id"}),
}
# FK-safe load order: parent first
LOAD_ORDER = ["companies", "sectors", "profitandloss", "balancesheet", "cashflow", "analysis",
              "documents", "prosandcons", "stock_prices", "market_cap", "financial_ratios_source", "peer_groups"]
FISCAL_YEAR_TABLES = {"profitandloss", "balancesheet", "cashflow", "financial_ratios_source"}
KEYS = {
    "profitandloss": ["company_id", "year"], "balancesheet": ["company_id", "year"],
    "cashflow": ["company_id", "year"], "financial_ratios_source": ["company_id", "year"],
    "documents": ["company_id", "year"], "market_cap": ["company_id", "year"],
    "stock_prices": ["company_id", "date"], "sectors": ["company_id"],
    "peer_groups": ["peer_group_name", "company_id"],
}


def read_sheet(path: Path, header: int) -> pd.DataFrame:
    """Read an Excel file; fall back to the other header row if the expected column is missing."""
    for h in (header, 1 - header if header in (0, 1) else header):
        df = pd.read_excel(path, header=h)
        if {"id", "company_id"} & set(df.columns):
            return df.dropna(how="all").reset_index(drop=True)
    raise ValueError(f"{path.name}: could not locate header row")


def _clean_text(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object:
            df[c] = df[c].map(lambda v: re.sub(r"\s+", " ", v).strip() or None if isinstance(v, str) else v)
    return df


def _audit_row(table, spec, rows_in, st, rows_out, runtime):
    return {
        "table": table, "source_file": spec["file"], "rows_in": rows_in,
        "rejected_ticker": st["ticker"], "rejected_year": st["year"],
        "excluded_ttm": st["ttm"], "excluded_out_of_universe": st["orphan"],
        "duplicates_removed": st["dups"], "rows_out": rows_out,
        "rejected_total": rows_in - rows_out,
        "critical_rejections": st["ticker"] + st["year"],
        "warnings_flagged": st["warn"],
        "loaded_at": datetime.now().isoformat(timespec="seconds"), "runtime_s": round(runtime, 3),
    }


def run(raw_dir: Path, db_path: Path, out_dir: Path, check_urls: bool = False,
        validate_only: bool = False) -> dict:
    t_start = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[dict] = []
    frames: dict[str, pd.DataFrame] = {}
    audit: list[dict] = []
    info: dict = {}

    # ---------------------------------------------------------------- companies
    t0 = time.time()
    spec = SPECS["companies"]
    raw = read_sheet(raw_dir / spec["file"], spec["header"])
    st = dict(ticker=0, year=0, ttm=0, orphan=0, dups=0, warn=0)
    comp = raw.rename(columns={"id": "company_id"})
    comp, f, st["ticker"] = V.dq08_tickers(comp, "companies"); failures += f
    ok, f = V.dq01_company_pk(comp); failures += f
    if not ok:
        raise RuntimeError("DQ-01 failed: duplicate tickers in companies; load halted")
    comp = _clean_text(comp).rename(columns={"company_id": "id"})
    valid_ids = set(comp["id"])
    frames["companies"] = comp
    rows_in = {"companies": len(raw)}
    stats = {"companies": st}
    runtimes = {"companies": time.time() - t0}

    # ------------------------------------------------------- the other 11 tables
    for table in LOAD_ORDER[1:]:
        t0 = time.time()
        spec = SPECS[table]
        raw = read_sheet(raw_dir / spec["file"], spec["header"])
        rows_in[table] = len(raw)
        st = dict(ticker=0, year=0, ttm=0, orphan=0, dups=0, warn=0)
        df = _clean_text(raw.rename(columns=spec.get("rename", {})))
        df, f, st["ticker"] = V.dq08_tickers(df, table); failures += f
        df, f, st["orphan"] = V.dq03_fk(df, table, valid_ids); failures += f
        if table in FISCAL_YEAR_TABLES:
            df, f, st["year"], st["ttm"] = V.dq07_years(df, table); failures += f
            assert V.check_year_format(df["year"]), f"{table}: DQ-07 post-condition failed"
        if table == "stock_prices":
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        if table == "market_cap" or table == "documents":
            df["year"] = df["year"].astype(int)
        if table in KEYS:
            df, f, st["dups"] = V.dq02_dedupe(df, table, KEYS[table]); failures += f
        if table == "analysis":
            df = _parse_analysis(df)
        if table == "peer_groups":
            df["is_benchmark"] = df["is_benchmark"].astype(bool).astype(int)
        frames[table] = df
        stats[table] = st
        runtimes[table] = time.time() - t0

    # --------------------------------------------------------- post-clean rules
    pl, bs, cf = frames["profitandloss"], frames["balancesheet"], frames["cashflow"]
    banks = set(frames["sectors"].loc[frames["sectors"]["sub_sector"].fillna("").str.contains("Bank"), "company_id"])
    f4, strict = V.dq04_bs_balance(bs)
    bs, f10 = V.dq10_fixed_assets(bs)
    cf, f9 = V.dq09_net_cash(cf)
    post = f4 + f10 + f9 + V.dq05_opm(pl) + V.dq06_positive_sales(pl, banks) + V.dq11_tax(pl) \
        + V.dq12_dividend(pl) + V.dq14_eps(pl) + V.dq13_urls(frames["documents"], check_urls) \
        + V.dq16_coverage(comp, {"profitandloss": pl, "balancesheet": bs, "cashflow": cf})
    failures += post
    frames["balancesheet"], frames["cashflow"] = bs, cf
    failures.append({**V._f("DQ-15", "balancesheet", None,
                            f"{strict} rows pass DQ-04 but total_assets != total_liabilities exactly",
                            "Informational counter", "INFO", company_id="*", year="*")})
    for r in post:
        if r["status"] == "FLAGGED" and r["table"] in stats:
            stats[r["table"]]["warn"] += 1

    fails_df = V.failures_frame(failures)
    fails_df.to_csv(out_dir / "validation_failures.csv", index=False)
    fails_df[fails_df["rule_id"] == "DQ-07"].to_csv(out_dir / "parse_failures.csv", index=False)
    info["failures"] = fails_df

    if validate_only:
        info["validate_only"] = True
        return info

    # ------------------------------------------------------------------ SQLite
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((ROOT / "db" / "schema.sql").read_text())
    for table in LOAD_ORDER:
        t0 = time.time()
        frames[table].to_sql(table, con, if_exists="append", index=False)
        con.commit()
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        audit.append(_audit_row(table, SPECS[table], rows_in[table], stats[table], n,
                                runtimes[table] + time.time() - t0))
    fk_violations = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()

    audit_df = pd.DataFrame(audit)
    audit_df.to_csv(out_dir / "load_audit.csv", index=False)
    info.update(audit=audit_df, fk_violations=len(fk_violations), runtime_s=round(time.time() - t_start, 2),
                dq15_strict_imbalance=strict)
    return info


def _parse_analysis(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = {"compounded_sales_growth": "compounded_sales_growth_pct",
            "compounded_profit_growth": "compounded_profit_growth_pct",
            "stock_price_cagr": "stock_price_cagr_pct", "roe": "roe_pct"}
    df["period"] = None
    for src, dst in cols.items():
        parsed = df[src].map(parse_growth_text)
        df[dst] = parsed.map(lambda t: t[1])
        if src == "compounded_sales_growth":
            df["period"] = parsed.map(lambda t: t[0])
    return df


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def main(argv=None) -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:  # pragma: no cover
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=_env("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
    info = run(ROOT / _env("RAW_DIR", "data/raw"), ROOT / _env("DB_PATH", "data/nifty100.db"),
               ROOT / _env("OUTPUT_DIR", "output"),
               check_urls=_env("CHECK_URLS", "false").lower() == "true", validate_only=a.validate_only)
    if "audit" in info:
        print(info["audit"][["table", "rows_in", "rows_out", "rejected_total", "critical_rejections"]].to_string(index=False))
        print(f"foreign_key_check violations: {info['fk_violations']}  runtime: {info['runtime_s']}s")
    else:
        print(info["failures"].groupby(["rule_id", "severity", "status"]).size())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
