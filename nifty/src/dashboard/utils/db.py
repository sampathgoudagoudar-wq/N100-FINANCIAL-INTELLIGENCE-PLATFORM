"""Cached SQLite loaders for the dashboard. Every query function uses @st.cache_data(ttl=600)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "nifty100.db"
TTL = 600


def _q(sql: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(sql, con, params=params)
    return df


def _norm(ticker: str) -> str:
    return str(ticker).strip().upper()


@st.cache_data(ttl=TTL)
def get_companies() -> pd.DataFrame:
    """company_id, company_name, broad_sector, sub_sector, market_cap_category, about_company."""
    return _q("""SELECT c.id AS company_id, c.company_name, c.about_company, c.website,
                        s.broad_sector, s.sub_sector, s.market_cap_category
                 FROM companies c LEFT JOIN sectors s ON s.company_id = c.id ORDER BY c.company_name""")


@st.cache_data(ttl=TTL)
def get_ratios(ticker: str, year: int | None = None) -> pd.DataFrame:
    """Computed KPI panel for one company (all years, or one fiscal year)."""
    sql, p = "SELECT * FROM financial_ratios WHERE company_id = ?", [_norm(ticker)]
    if year is not None:
        sql, p = sql + " AND year = ?", p + [int(year)]
    return _q(sql + " ORDER BY year", tuple(p))


@st.cache_data(ttl=TTL)
def get_pl(ticker: str) -> pd.DataFrame:
    return _q("SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year", (_norm(ticker),))


@st.cache_data(ttl=TTL)
def get_bs(ticker: str) -> pd.DataFrame:
    return _q("SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year", (_norm(ticker),))


@st.cache_data(ttl=TTL)
def get_cf(ticker: str) -> pd.DataFrame:
    return _q("SELECT * FROM cashflow WHERE company_id = ? ORDER BY year", (_norm(ticker),))


@st.cache_data(ttl=TTL)
def get_sectors() -> pd.DataFrame:
    return _q("SELECT * FROM sectors ORDER BY broad_sector, sub_sector, company_id")


@st.cache_data(ttl=TTL)
def get_peer_groups() -> list[str]:
    return _q("SELECT DISTINCT peer_group_name FROM peer_groups ORDER BY 1")["peer_group_name"].tolist()


@st.cache_data(ttl=TTL)
def get_peers(group_name: str) -> pd.DataFrame:
    """Members of a peer group with latest KPIs (snapshot year 2024) and the benchmark flag."""
    return _q("""SELECT p.peer_group_name, p.is_benchmark, k.*
                 FROM peer_groups p JOIN kpi_snapshot k ON k.company_id = p.company_id
                 WHERE p.peer_group_name = ? AND k.snapshot_year = (SELECT MAX(snapshot_year) FROM kpi_snapshot)
                 ORDER BY p.is_benchmark DESC, k.composite_quality_score DESC""", (group_name,))


@st.cache_data(ttl=TTL)
def get_peer_percentiles(group_name: str) -> pd.DataFrame:
    return _q("SELECT * FROM peer_percentiles WHERE peer_group_name = ?", (group_name,))


@st.cache_data(ttl=TTL)
def get_valuation(ticker: str | None = None) -> pd.DataFrame:
    if ticker is None:
        return _q("SELECT * FROM valuation")
    return _q("SELECT * FROM valuation WHERE company_id = ?", (_norm(ticker),))


@st.cache_data(ttl=TTL)
def get_snapshot(year: int | None = None) -> pd.DataFrame:
    """One row per company with KPIs + composite scores as of `year` (default: latest)."""
    if year is None:
        year = int(_q("SELECT MAX(snapshot_year) y FROM kpi_snapshot")["y"].iloc[0])
    df = _q("SELECT * FROM kpi_snapshot WHERE snapshot_year = ?", (int(year),))
    df.loc[:, "icr"] = df["icr"].where(df["icr"] < 1e9, np.inf)       # 1e9 = stored Debt Free
    return df


@st.cache_data(ttl=TTL)
def get_peer_axes() -> pd.DataFrame:
    """0-100 radar-axis scores for every company (latest snapshot)."""
    from src.analytics.radar import axis_scores
    return axis_scores(get_snapshot().sort_values("company_id").reset_index(drop=True))


@st.cache_data(ttl=TTL)
def get_capital() -> pd.DataFrame:
    return _q("""SELECT c.id AS company_id, c.company_name, s.broad_sector, a.year, a.cfo, a.cfi, a.cff,
                        COALESCE(a.pattern, 'Unclassified (no cash-flow data)') AS pattern,
                        v.market_cap_crore
                 FROM companies c LEFT JOIN sectors s ON s.company_id = c.id
                 LEFT JOIN capital_allocation a ON a.company_id = c.id
                 LEFT JOIN valuation v ON v.company_id = c.id""")


@st.cache_data(ttl=TTL)
def get_docs(ticker: str) -> pd.DataFrame:
    return _q("SELECT year, Annual_Report FROM documents WHERE company_id = ? ORDER BY year DESC", (_norm(ticker),))


@st.cache_data(ttl=TTL)
def get_proscons(ticker: str) -> dict[str, list[str]]:
    """Source pros/cons where present; otherwise (and in addition) KPI-rule generated items."""
    from src.analytics.proscons import generate
    t = _norm(ticker)
    src = _q("SELECT pros, cons FROM prosandcons WHERE company_id = ?", (t,))
    pros = [x for x in src["pros"].dropna().tolist()]
    cons = [x for x in src["cons"].dropna().tolist()]
    snap = get_snapshot()
    row = snap[snap["company_id"] == t]
    if len(row):
        gp, gc = generate(row.iloc[0], get_ratios(t))
        pros += [x for x in gp if x not in pros]
        cons += [x for x in gc if x not in cons]
    return {"pros": pros, "cons": cons}
