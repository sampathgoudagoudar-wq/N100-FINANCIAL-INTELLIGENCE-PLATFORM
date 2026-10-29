"""Independent recomputation of ROE and 5-year revenue CAGR from the RAW Excel files
(no engine code, no database) for 3 companies, compared with financial_ratios (Day 12)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .engine import DB, OUT, ROOT

COMPANIES = ["TCS", "RELIANCE", "ITC"]
MONTH = {"Mar": "03", "Dec": "12", "Jun": "06", "Sep": "09"}


def _raw(name):
    return pd.read_excel(ROOT / "data" / "raw" / f"{name}.xlsx", header=1)


def _fy(label):  # 'Mar 2024' / 'Mar-24' -> '2024-03'
    s = str(label).replace("-", " ").split()
    y = s[1] if len(s[1]) == 4 else "20" + s[1]
    return f"{y}-{MONTH[s[0][:3]]}"


def run(companies=COMPANIES, tol=0.1):
    pl, bs = _raw("profitandloss"), _raw("balancesheet")
    con = sqlite3.connect(DB)
    lines = ["# Spot-check: independent recomputation vs financial_ratios", "",
             "| company | year | metric | manual | database | abs diff | pass |", "|---|---|---|---|---|---|---|"]
    ok = True  # becomes numpy bool below; cast on return
    for c in companies:
        p = pl[(pl.company_id == c) & (pl.year != "TTM")].copy()
        p["fy"] = p.year.map(_fy)
        p = p.drop_duplicates("fy", keep="last").set_index("fy")
        y = "2024-03"
        b = bs[(bs.company_id == c)].copy()
        b["fy"] = b.year.map(lambda v: _fy(v) if not str(v).isdigit() else f"{v}-03")
        b = b.drop_duplicates("fy", keep="last").set_index("fy")
        roe = p.loc[y, "net_profit"] / (b.loc[y, "equity_capital"] + b.loc[y, "reserves"]) * 100
        cagr = ((p.loc[y, "sales"] / p.loc["2019-03", "sales"]) ** (1 / 5) - 1) * 100
        db = con.execute("SELECT return_on_equity_pct, revenue_cagr_5yr FROM financial_ratios WHERE company_id=? AND year=?", (c, y)).fetchone()
        for name, m, d in (("ROE %", roe, db[0]), ("Revenue CAGR 5yr %", cagr, db[1])):
            good = abs(m - d) < tol
            ok &= good
            lines.append(f"| {c} | {y} | {name} | {m:.4f} | {d:.4f} | {abs(m - d):.6f} | {'yes' if good else 'NO'} |")
    lines += ["", f"**Result: {'PASS' if ok else 'FAIL'}** (tolerance {tol} percentage points)"]
    (OUT / "spot_check.md").write_text("\n".join(lines) + "\n")
    return bool(ok)


if __name__ == "__main__":
    print("PASS" if run() else "FAIL")
