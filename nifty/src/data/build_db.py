"""Build data/nifty100.db — the single SQLite store read by the dashboard."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics.capital import capital_allocation
from src.analytics.metrics import add_growth, build_panel, latest_snapshot
from src.analytics.peer import CORE_METRICS, compute_percentiles, write_peer_percentiles
from src.analytics.valuation import compute_valuation
from src.data.loader import DATA_DIR, load_clean, read_raw
from src.screener.engine import add_composite_score, load_config

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "nifty100.db"
YEARS = range(2019, 2025)


def build(db_path: Path = DB_PATH) -> dict[str, int]:
    t, _ = load_clean()
    cfg = load_config()
    panel = add_growth(build_panel(t))
    snaps = []
    for y in YEARS:
        s = add_composite_score(latest_snapshot(t, panel, y), cfg)
        s["snapshot_year"] = y
        snaps.append(s)
    kpi = pd.concat(snaps, ignore_index=True)
    latest = snaps[-1]

    # History for companies whose balance sheet is unusable (unit anomalies / SBIN): blank the
    # P&L-vs-BS ratios, keep the pre-computed source ROE/ROCE for the latest year only.
    bad = latest[latest["roe_source"] != "computed"].set_index("company_id")
    mask = panel["company_id"].isin(bad.index)
    panel.loc[mask, ["roe", "roce", "asset_turnover"]] = np.nan
    for cid, r in bad.iterrows():
        idx = panel.index[(panel["company_id"] == cid) & (panel["year"] == r["fy"])]
        panel.loc[idx, ["roe", "roce"]] = [r["roe"], r["roce"]]

    docs = read_raw("documents", DATA_DIR)
    docs["company_id"] = docs["company_id"].astype(str).str.strip().str.upper()
    docs = docs[docs["company_id"].isin(set(t["companies"]["id"]))].rename(columns={"Year": "year"})
    pc = read_raw("prosandcons", DATA_DIR)
    pc["company_id"] = pc["company_id"].astype(str).str.strip().str.upper()

    tables = {
        "companies": t["companies"].drop(columns=["company_logo"], errors="ignore"),
        "profitandloss": t["profitandloss"], "balancesheet": t["balancesheet"], "cashflow": t["cashflow"],
        "sectors": t["sectors"], "market_cap": t["market_cap"], "peer_groups": t["peer_groups"],
        "documents": docs, "prosandcons": pc,
        "financial_ratios": panel,               # computed KPI panel (company x fiscal year)
        "kpi_snapshot": kpi,                     # per-year snapshot incl. composite scores
        "capital_allocation": capital_allocation(t["cashflow"]),
        "valuation": compute_valuation(t, latest),
    }
    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with sqlite3.connect(db_path) as con:
        for name, df in tables.items():
            d = df.copy()
            for c in d.columns:                       # SQLite cannot store inf
                if d[c].dtype.kind == "f":
                    d[c] = d[c].where(~d[c].isin([float("inf"), float("-inf")]), 1e9)
            d.to_sql(name, con, if_exists="replace", index=False)
            counts[name] = len(d)
        con.execute("CREATE INDEX IF NOT EXISTS ix_fr ON financial_ratios(company_id, year)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_pl ON profitandloss(company_id, year)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_kpi ON kpi_snapshot(snapshot_year, company_id)")
    counts["peer_percentiles"] = write_peer_percentiles(
        compute_percentiles(latest, t["peer_groups"], CORE_METRICS), db_path)
    return counts


if __name__ == "__main__":
    print(build())
