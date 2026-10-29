"""Builds output/ratio_edge_cases.log (Sprint 2, Day 13).

Each anomaly is categorised, with evidence, as one of:
  DATA SOURCE ISSUE     - the supplied value is wrong/missing/in another unit
  VERSION DIFFERENCE    - source is a different snapshot/period than the engine uses
  FORMULA DISCREPANCY   - a different, identifiable definition explains the gap
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd

from .engine import DB, OUT

DSI, VER, FORM = "DATA SOURCE ISSUE", "VERSION DIFFERENCE", "FORMULA DISCREPANCY"
THRESH = 5.0   # percentage points


def _entry(cat, check, company, detail, why):
    return {"category": cat, "check": check, "company": company, "detail": detail, "explanation": why}


def build(con: sqlite3.Connection) -> list[dict]:
    q = lambda s: pd.read_sql(s, con)
    base = q("""SELECT f.*, s.broad_sector sector, c.roce_percentage s_roce, c.roe_percentage s_roe
                FROM financial_ratios f JOIN companies c ON c.id=f.company_id JOIN sectors s USING(company_id)""")
    pl = q("SELECT * FROM profitandloss").set_index(["company_id", "year"])
    bs = q("SELECT * FROM balancesheet").set_index(["company_id", "year"])
    out: list[dict] = []

    # ---- 1/2: ROCE and ROE vs companies.xlsx (latest fiscal year per company)
    latest = base[base.return_on_equity_pct.notna() | base.roce_pct.notna()]
    latest = latest[latest.year.isin(pl.reset_index().year)].sort_values("year").groupby("company_id").tail(1)
    for _, r in latest.iterrows():
        cid, y = r.company_id, r.year
        p, b = pl.loc[(cid, y)], bs.loc[(cid, y)] if (cid, y) in bs.index else None
        fin, suspect = r.sector == "Financials", r.data_quality_flag == "BS_SCALE_SUSPECT"
        # ROCE
        if pd.notna(r.roce_pct):
            if pd.isna(r.s_roce):
                out.append(_entry(DSI, "ROCE vs source", cid, f"{y}: computed {r.roce_pct:.1f}%, source roce_percentage missing",
                                  "companies.xlsx has no ROCE for this company."))
            elif abs(r.roce_pct - r.s_roce) > THRESH:
                alt = (p.profit_before_tax + p.interest) / (b.equity_capital + b.reserves + b.borrowings) * 100 if b is not None else None
                d = f"{y}: computed {r.roce_pct:.1f}% vs source {r.s_roce:.1f}% (diff {r.roce_pct - r.s_roce:+.1f}pp)"
                if suspect:
                    out.append(_entry(DSI, "ROCE vs source", cid, d, "Balance-sheet figures are implausibly small versus sales (BS_SCALE_SUSPECT); computed value unreliable."))
                elif alt is not None and abs(alt - r.s_roce) <= THRESH:
                    out.append(_entry(FORM, "ROCE vs source", cid, d + f"; PBT+interest basis gives {alt:.1f}%",
                                      "Source ROCE matches EBIT = PBT + interest (includes other income); spec EBIT = operating_profit - depreciation excludes it."))
                elif fin:
                    out.append(_entry(FORM, "ROCE vs source", cid, d,
                                      "Lender: deposits/borrowings make capital employed non-comparable; neither definition matches the source. Sector-relative ROCE is used instead."))
                else:
                    out.append(_entry(VER, "ROCE vs source", cid, d,
                                      "Gap persists after aligning the EBIT definition; companies.xlsx is a current snapshot (not tied to the FY2024 statements used here)."))
        # ROE
        if pd.notna(r.return_on_equity_pct) and pd.notna(r.s_roe) and abs(r.return_on_equity_pct - r.s_roe) > THRESH:
            d = f"{y}: computed {r.return_on_equity_pct:.1f}% vs source {r.s_roe:.2f}% (diff {r.return_on_equity_pct - r.s_roe:+.1f}pp)"
            prev = bs.loc[(cid, f"{int(y[:4]) - 1}{y[4:]}")] if (cid, f"{int(y[:4]) - 1}{y[4:]}") in bs.index else None
            avg_roe = (p.net_profit / ((b.equity_capital + b.reserves + prev.equity_capital + prev.reserves) / 2) * 100
                       if b is not None and prev is not None else None)
            if suspect:
                out.append(_entry(DSI, "ROE vs source", cid, d, "Balance-sheet scale implausible (BS_SCALE_SUSPECT); computed ROE unreliable."))
            elif abs(r.s_roe * 100 - r.return_on_equity_pct) <= THRESH:
                out.append(_entry(DSI, "ROE vs source", cid, d, "Source value is the ratio stored as a fraction (x100 matches computed); use engine value, source for display only."))
            elif avg_roe is not None and abs(avg_roe - r.s_roe) <= THRESH:
                out.append(_entry(FORM, "ROE vs source", cid, d + f"; average-equity ROE {avg_roe:.1f}%",
                                  "Source ROE uses average equity; engine uses closing equity + reserves per spec."))
            else:
                out.append(_entry(VER, "ROE vs source", cid, d, "Not explained by units or average equity; source is a current snapshot, engine uses FY2024 statements."))

    # ---- 3: OPM cross-check (per company)
    mm = base[base.opm_mismatch_flag == 1].copy()
    mm["gap"] = (mm.opm_source_pct - mm.operating_profit_margin_pct).abs()
    for cid, g in mm.groupby("company_id"):
        d = f"{len(g)} year(s) with |source - computed| > 1pp; max gap {g.gap.max():.1f}pp (source up to {g.opm_source_pct.abs().max():.0f})"
        if g.opm_source_pct.abs().max() > 100:
            out.append(_entry(DSI, "OPM cross-check", cid, d, "Source opm_percentage holds non-percentage values (> 100); engine uses computed OPM."))
        elif g.sector.iloc[0] == "Financials":
            out.append(_entry(FORM, "OPM cross-check", cid, d, "Lender: operating profit is defined differently from industrials; engine uses computed OPM."))
        else:
            out.append(_entry(DSI, "OPM cross-check", cid, d, "Source OPM inconsistent with its own operating_profit / sales; engine uses computed OPM."))

    # ---- 4: structural data problems
    for cid, g in base[base.data_quality_flag == "BS_SCALE_SUSPECT"].groupby("company_id"):
        out.append(_entry(DSI, "Balance-sheet scale", cid, f"{len(g)} year(s) with sales / total_assets > 6x (max {g.asset_turnover.max():.0f}x)",
                          "Total assets and equity are orders of magnitude below sales; ROE/ROCE/ROA/asset turnover unreliable for these rows."))
    allco = q("SELECT id FROM companies").id
    for cid in allco[~allco.isin(base[base.return_on_equity_pct.notna()].company_id)]:
        out.append(_entry(DSI, "Missing inputs", cid, "No ROE computable in any year", "Balance sheet missing in source (cannot compute equity-based ratios)."))
    nbs = base[(base.data_quality_flag == "NO_PL")]
    out.append(_entry(VER, "Period mismatch", f"{nbs.company_id.nunique()} companies",
                      f"{len(nbs)} balance-sheet-only rows labelled 2024-09", "Sep-2024 balance sheets have no P&L/cash-flow for that date; only balance-sheet ratios are populated."))
    return out


def write(entries: list[dict], path: Path) -> None:
    cnt = Counter(e["category"] for e in entries)
    lines = ["# ratio_edge_cases.log - Sprint 2", f"# entries: {len(entries)} | " + " | ".join(f"{k}: {v}" for k, v in sorted(cnt.items())),
             "# format: CATEGORY | CHECK | COMPANY | DETAIL | EXPLANATION", ""]
    for e in sorted(entries, key=lambda e: (e["check"], e["company"])):
        lines.append(f"{e['category']} | {e['check']} | {e['company']} | {e['detail']} | {e['explanation']}")
    path.write_text("\n".join(lines) + "\n")


def run(db: Path = DB, out_dir: Path = OUT) -> list[dict]:
    con = sqlite3.connect(db)
    e = build(con)
    con.close()
    write(e, out_dir / "ratio_edge_cases.log")
    return e


if __name__ == "__main__":
    es = run()
    print(len(es), dict(Counter(e["category"] for e in es)))
