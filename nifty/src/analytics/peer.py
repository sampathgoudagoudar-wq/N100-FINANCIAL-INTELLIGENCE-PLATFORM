"""Peer percentile engine.

PERCENT_RANK within each peer group (SQL semantics):  (rank_min - 1) / (n_valid - 1), computed over
the non-null values of that metric.  Metrics where lower is better (D/E, P/E, P/B) are inverted
(1 - PERCENT_RANK) so a higher percentile is always "better".
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

NO_PEER_MESSAGE = "No peer group assigned"
DEBT_FREE_SENTINEL = 999.0          # project doc: interest coverage 999 is displayed as 'Debt Free'

# key, label, higher_is_better
CORE_METRICS = [
    ("roe", "ROE %", True), ("roce", "ROCE %", True), ("npm", "Net profit margin %", True),
    ("de", "Debt / Equity", False), ("fcf", "Free cash flow (Cr)", True),
    ("pat_cagr_5y", "PAT CAGR 5yr %", True), ("rev_cagr_5y", "Revenue CAGR 5yr %", True),
    ("eps_cagr_5y", "EPS CAGR 5yr %", True), ("icr", "Interest coverage (x)", True),
    ("asset_turnover", "Asset turnover (x)", True),
]
EXTRA_METRICS = [
    ("opm", "Operating margin %", True), ("cfo_pat", "CFO / PAT", True),
    ("rev_cagr_3y", "Revenue CAGR 3yr %", True), ("fcf_cagr_5y", "FCF CAGR 5yr %", True),
    ("pe", "P/E", False), ("pb", "P/B", False), ("div_yield", "Dividend yield %", True),
    ("sales", "Sales (Cr)", True), ("net_profit", "Net profit (Cr)", True),
    ("composite_quality_score", "Composite quality score", True),
]
ALL_METRICS = CORE_METRICS + EXTRA_METRICS


def percent_rank(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """PERCENT_RANK over non-null values; NaN stays NaN; <2 valid values -> NaN."""
    out = pd.Series(np.nan, index=values.index)
    valid = values.dropna()
    n = len(valid)
    if n < 2:
        return out
    ranks = rankdata(valid.to_numpy(dtype=float), method="min")   # ties share the lowest rank
    pr = (ranks - 1) / (n - 1)
    out.loc[valid.index] = pr if higher_is_better else 1 - pr
    return out


# NB: for inverted metrics a *tie* gets (1 - PERCENT_RANK), which keeps tied companies equal.


def compute_percentiles(snapshot: pd.DataFrame, peer_groups: pd.DataFrame,
                        metrics: list[tuple[str, str, bool]] = CORE_METRICS) -> pd.DataFrame:
    """Long table: company_id, peer_group_name, metric, value, percentile_rank, year."""
    snap = snapshot.set_index("company_id")
    rows = []
    for group, members in peer_groups.groupby("peer_group_name"):
        ids = [c for c in members["company_id"] if c in snap.index]
        sub = snap.loc[ids]
        for key, _, hib in metrics:
            vals = pd.to_numeric(sub[key], errors="coerce")
            ranked = vals
            if np.isinf(vals).any():
                # debt-free interest coverage (+inf) must outrank every finite value
                finite = vals[np.isfinite(vals)]
                ranked = vals.replace(np.inf, (finite.max() if len(finite) else 0) * 10 + 1)
            pr = percent_rank(ranked, hib)
            for cid in ids:
                v = vals.loc[cid]
                rows.append({
                    "company_id": cid, "peer_group_name": group, "metric": key,
                    "value": DEBT_FREE_SENTINEL if (key == "icr" and np.isinf(v)) else (None if pd.isna(v) else float(v)),
                    "percentile_rank": None if pd.isna(pr.loc[cid]) else round(float(pr.loc[cid]), 4),
                    "year": int(sub.loc[cid, "fy"]),
                })
    return pd.DataFrame(rows)


def write_peer_percentiles(df: pd.DataFrame, db_path: str | Path) -> int:
    """(Re)create the peer_percentiles table in SQLite; returns the row count."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.execute("DROP TABLE IF EXISTS peer_percentiles")
        con.execute("""CREATE TABLE peer_percentiles (
            company_id TEXT NOT NULL, peer_group_name TEXT NOT NULL, metric TEXT NOT NULL,
            value REAL, percentile_rank REAL, year INTEGER NOT NULL,
            PRIMARY KEY (company_id, peer_group_name, metric, year))""")
        df.to_sql("peer_percentiles", con, if_exists="append", index=False)
        con.execute("CREATE INDEX idx_pp_group_metric ON peer_percentiles(peer_group_name, metric)")
        return con.execute("SELECT COUNT(*) FROM peer_percentiles").fetchone()[0]


def company_percentiles(company_id: str, db_path: str | Path) -> pd.DataFrame | str:
    """Percentiles for one company, or the string 'No peer group assigned' (never raises)."""
    company_id = str(company_id).strip().upper()
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(
            "SELECT * FROM peer_percentiles WHERE company_id = ?", con, params=(company_id,))
    return df if len(df) else NO_PEER_MESSAGE
