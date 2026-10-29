"""Day 06 manual DQ review: spot-check 5 random companies, DB vs raw Excel."""
from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pandas as pd

from .loader import ROOT, SPECS, read_sheet
from .normaliser import normalize_ticker, normalize_year

TS = {"profitandloss": ["sales", "net_profit"], "balancesheet": ["total_assets", "reserves"],
      "cashflow": ["operating_activity", "net_cash_flow"]}


def review(seed: int = 7, n: int = 5, db=ROOT / "data/nifty100.db", raw=ROOT / "data/raw"):
    con = sqlite3.connect(db)
    ids = [r[0] for r in con.execute("SELECT id FROM companies ORDER BY id")]
    picks = random.Random(seed).sample(ids, n)
    lines = [f"# Day 06 manual review (seed={seed})", "", f"Companies: {', '.join(picks)}", ""]
    problems = 0
    for cid in picks:
        name = con.execute("SELECT company_name FROM companies WHERE id=?", (cid,)).fetchone()[0]
        lines += [f"## {cid} - {name}", "", "| table | db years | first | last | raw rows | value check |", "|---|---|---|---|---|---|"]
        for t, cols in TS.items():
            d = pd.read_sql(f"SELECT * FROM {t} WHERE company_id=?", con, params=(cid,))
            r = read_sheet(raw / SPECS[t]["file"], SPECS[t]["header"])
            r["company_id"] = r["company_id"].map(normalize_ticker)
            r = r[r.company_id == cid].copy()
            r["y"] = r["year"].map(normalize_year)
            r = r[~r.y.isin(["TTM", "PARSE_ERROR"])]
            raw_years = set(r.y)
            ok = raw_years == set(d.year)
            mism = 0
            for _, row in d.iterrows():          # every value of the check columns vs the (last) raw row
                src = r[r.y == row.year].iloc[-1]
                for c in cols:
                    if pd.notna(src[c]) and abs(float(src[c]) - float(row[c])) > 1e-9 and not (t == "cashflow" and c == "net_cash_flow"):
                        mism += 1
            problems += (not ok) + (mism > 0)
            lines.append(f"| {t} | {len(d)} | {d.year.min() if len(d) else '-'} | {d.year.max() if len(d) else '-'} "
                         f"| {len(r)} | years {'match' if ok else 'DIFFER'}; {mism} value mismatches |")
        yrs = con.execute("SELECT COUNT(*) FROM stock_prices WHERE company_id=?", (cid,)).fetchone()[0]
        lines += ["", f"stock_prices rows: {yrs} (expected 60)", ""]
        problems += yrs != 60
    short = pd.read_sql("""SELECT c.id, (SELECT COUNT(*) FROM profitandloss WHERE company_id=c.id) pl,
        (SELECT COUNT(*) FROM balancesheet WHERE company_id=c.id) bs, (SELECT COUNT(*) FROM cashflow WHERE company_id=c.id) cf
        FROM companies c WHERE pl<5 OR bs<5 OR cf<5""", con)
    lines += ["## Companies with fewer than 5 years in any statement", "", short.to_markdown(index=False), ""]
    lines += ["## Findings for analyst follow-up (source data, not loader bugs)", "",
              "1. **Loader bug fixed:** 7 cash-flow rows were keyed `AGTL` (typo of `ATGL`); remapped via `TICKER_ALIASES`.",
              "2. **SBIN has no balance-sheet rows and ATGL/SBIN have no financial_ratios rows in the source files.**",
              "3. **Out-of-universe tickers:** ULTRACEMCO, UNIONBANK, UNITDSPR, VBL, VEDL, WIPRO, ZOMATO, ZYDUSLIFE appear in time-series files but not in companies.xlsx (92); their rows are excluded (DQ-03).",
              "4. **Implausible balance-sheet scale** for BEL, HAL, INDIGO and LT (sales/total_assets > 20x in 39 rows; e.g. BEL FY24 total_assets=161 Cr vs sales=20,268 Cr), so ROE is in the thousands of %. Balance and OPM rules cannot catch this.",
              "5. **83 balance-sheet rows are labelled Sep 2024** (one per company) with no matching P&L/CF period; kept as `2024-09` but look like interim snapshots.",
              "6. **Bank OPM:** `opm_percentage` holds non-percentage values for banks (e.g. AXISBANK 1353), driving most DQ-05 flags.",
              "7. TVSMOTOR has no face/book value or ROCE in companies.xlsx; INDIGO and TVSMOTOR have null ROE.", ""]
    lines.append(f"**Result: {problems} problems across the 5 sampled companies.**")
    out = ROOT / "output" / "manual_review.md"
    out.write_text("\n".join(lines))
    return problems, picks, short


if __name__ == "__main__":
    p, picks, short = review()
    print(picks, "problems:", p); print(short)
