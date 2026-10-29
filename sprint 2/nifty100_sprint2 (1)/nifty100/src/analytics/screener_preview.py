"""Day 14 screener preview: ROE > 15% and D/E < 1 on each company's latest fiscal year."""
from __future__ import annotations

import sqlite3

import pandas as pd

from .engine import DB, OUT


def run():
    con = sqlite3.connect(DB)
    d = pd.read_sql("""SELECT f.company_id, c.company_name, s.broad_sector, f.year, f.return_on_equity_pct roe,
                              f.debt_to_equity de, f.data_quality_flag
                       FROM financial_ratios f JOIN companies c ON c.id=f.company_id JOIN sectors s USING(company_id)
                       WHERE f.return_on_equity_pct IS NOT NULL AND f.net_profit_margin_pct IS NOT NULL""", con)
    latest = d.sort_values("year").groupby("company_id").tail(1)
    excluded = latest[latest.data_quality_flag == "BS_SCALE_SUSPECT"]
    hit = latest[(latest.data_quality_flag.isna()) & (latest.roe > 15) & (latest.de < 1)].sort_values("roe", ascending=False)
    hit.to_csv(OUT / "screener_preview.csv", index=False)
    return hit, excluded


if __name__ == "__main__":
    h, e = run()
    print(len(h), "matches; excluded as suspect data:", list(e.company_id))
    print(h[["company_id", "broad_sector", "roe", "de"]].to_string(index=False))
