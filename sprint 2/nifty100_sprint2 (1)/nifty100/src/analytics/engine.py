"""Ratio engine: builds financial_ratios for every company-year (Sprint 2, Days 12-13).

Run:  python -m src.analytics.engine
Reads profitandloss / balancesheet / cashflow / companies / sectors from nifty100.db,
rewrites financial_ratios and writes output/capital_allocation.csv.
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from . import cagr as C
from . import cashflow_kpis as K
from . import ratios as R

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "nifty100.db"
OUT = ROOT / "output"
WINDOWS = (3, 5, 10)
BS_SCALE_SUSPECT_TURNOVER = 6.0    # sales / total_assets above this is implausible for this universe (LT FY24 = 8x, ROE 78%)
CFO_WINDOW = 5


def _clip(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def composite_quality_score(roe, margin, de, cfo_quality, is_financial) -> Optional[float]:
    """Provisional 0-100 blend of equally weighted components.

    ROE (0 -> 0, 25% -> 100); margin (OPM 0-30% for non-Financials, net margin 0-25% for
    Financials); leverage (D/E 0 -> 100, 3 -> 0; non-Financials only); cash quality
    (CFO/PAT 0 -> 0, 1.0 -> 100; non-Financials only). Needs >= 3 components (>= 2 for
    Financials). Weights are a Sprint 2 placeholder; the Sprint 3 health score supersedes it.
    """
    parts = []
    if roe is not None:
        parts.append(_clip(roe / 25 * 100))
    if margin is not None:
        parts.append(_clip(margin / (25 if is_financial else 30) * 100))
    if not is_financial:
        if de is not None:
            parts.append(_clip((3 - de) / 3 * 100))
        if cfo_quality is not None:
            parts.append(_clip(cfo_quality * 100))
    need = 2 if is_financial else 3
    return sum(parts) / len(parts) if len(parts) >= need else None


def load_inputs(con) -> dict:
    q = lambda s: pd.read_sql(s, con)
    return dict(
        pl=q("SELECT * FROM profitandloss"), bs=q("SELECT * FROM balancesheet"), cf=q("SELECT * FROM cashflow"),
        co=q("SELECT id, face_value FROM companies").set_index("id"),
        sec=q("SELECT company_id, broad_sector FROM sectors").set_index("company_id")["broad_sector"],
    )


def compute(inp: dict) -> pd.DataFrame:
    pl = inp["pl"].set_index(["company_id", "year"]).to_dict("index")
    bs = inp["bs"].set_index(["company_id", "year"]).to_dict("index")
    cf = inp["cf"].set_index(["company_id", "year"]).to_dict("index")
    keys = sorted(set(pl) | set(bs) | set(cf))
    series: Dict[str, Dict[str, Dict[str, float]]] = {}
    for (cid, y), row in pl.items():
        for name, col in (("revenue", "sales"), ("pat", "net_profit"), ("eps", "eps")):
            if row.get(col) is not None and not pd.isna(row[col]):
                series.setdefault(name, {}).setdefault(cid, {})[y] = row[col]

    rows = []
    for cid, y in keys:
        p, b, f = pl.get((cid, y), {}), bs.get((cid, y), {}), cf.get((cid, y), {})
        fin = inp["sec"].get(cid) == "Financials"
        fv = inp["co"]["face_value"].get(cid)
        r = {"company_id": cid, "year": y}
        r["net_profit_margin_pct"] = R.net_profit_margin(p.get("net_profit"), p.get("sales"))
        r["operating_profit_margin_pct"] = R.operating_profit_margin(p.get("operating_profit"), p.get("sales"))
        r["opm_source_pct"] = R.num(p.get("opm_percentage"))
        r["opm_mismatch_flag"] = int(R.opm_mismatch(p.get("opm_percentage"), r["operating_profit_margin_pct"]))
        r["return_on_equity_pct"] = R.return_on_equity(p.get("net_profit"), b.get("equity_capital"), b.get("reserves"))
        r["roce_pct"] = R.return_on_capital_employed(p.get("operating_profit"), p.get("depreciation"),
                                                     b.get("equity_capital"), b.get("reserves"), b.get("borrowings"))
        r["return_on_assets_pct"] = R.return_on_assets(p.get("net_profit"), b.get("total_assets"))
        de = R.debt_to_equity(b.get("borrowings"), b.get("equity_capital"), b.get("reserves"))
        r["debt_to_equity"] = de
        r["high_leverage_flag"] = int(R.high_leverage_flag(de, fin))
        icr = R.interest_coverage(p.get("operating_profit"), p.get("other_income"), p.get("interest"))
        r["interest_coverage"] = icr
        r["icr_label"] = R.icr_label(p.get("interest"))
        r["icr_warning_flag"] = int(R.icr_warning_flag(icr))
        r["net_debt_cr"] = R.net_debt(b.get("borrowings"), b.get("investments"))
        r["asset_turnover"] = R.asset_turnover(p.get("sales"), b.get("total_assets"))
        r["total_debt_cr"] = R.num(b.get("borrowings"))
        fcf = K.free_cash_flow(f.get("operating_activity"), f.get("investing_activity"))
        r["free_cash_flow_cr"] = fcf
        r["capex_cr"] = K.capex_proxy(f.get("investing_activity"))
        r["cash_from_operations_cr"] = R.num(f.get("operating_activity"))
        pairs = []
        for k in range(CFO_WINDOW):
            yy = C.shift_year(y, k)
            pairs.append((cf.get((cid, yy), {}).get("operating_activity"), pl.get((cid, yy), {}).get("net_profit")))
        r["cfo_quality_score"], r["cfo_quality_label"] = K.cfo_quality_score(pairs)
        r["capex_intensity_pct"] = K.capex_intensity(f.get("investing_activity"), p.get("sales"))
        r["capex_intensity_label"] = K.capex_intensity_label(r["capex_intensity_pct"])
        r["fcf_conversion_pct"] = K.fcf_conversion(fcf, p.get("operating_profit"))
        r["capital_allocation_pattern"] = (
            K.capital_allocation_pattern(f.get("operating_activity"), f.get("investing_activity"),
                                         f.get("financing_activity"),
                                         K.cfo_pat_ratio(f.get("operating_activity"), p.get("net_profit")))
            if f else None)
        r["earnings_per_share"] = R.num(p.get("eps"))
        r["book_value_per_share"] = R.book_value_per_share(b.get("equity_capital"), b.get("reserves"), fv)
        r["dividend_payout_ratio_pct"] = R.num(p.get("dividend_payout"))
        for name in ("revenue", "pat", "eps"):
            s = series.get(name, {}).get(cid, {})
            for n in WINDOWS:
                r[f"{name}_cagr_{n}yr"], r[f"{name}_cagr_{n}yr_flag"] = C.window_cagr(s, y, n)
        r["composite_quality_score"] = composite_quality_score(
            r["return_on_equity_pct"], r["net_profit_margin_pct"] if fin else r["operating_profit_margin_pct"],
            de, r["cfo_quality_score"], fin)
        at = r["asset_turnover"]
        r["data_quality_flag"] = ("BS_SCALE_SUSPECT" if at is not None and at > BS_SCALE_SUSPECT_TURNOVER
                                  else "NO_PL" if not p else "NO_BS" if not b else None)
        r["_fin"] = fin
        rows.append(r)

    df = pd.DataFrame(rows)
    # Financials: ROCE relative to the sector median for the same year (absolute thresholds not meaningful)
    med = df[df["_fin"]].groupby("year")["roce_pct"].median()
    df["roce_vs_sector_median_pp"] = [
        (v - med.get(y)) if fin and v is not None and not pd.isna(v) and y in med.index and not pd.isna(med.get(y)) else None
        for v, y, fin in zip(df["roce_pct"], df["year"], df["_fin"])]
    return df.drop(columns="_fin")


def write(df: pd.DataFrame, con: sqlite3.Connection) -> None:
    con.executescript((ROOT / "db" / "schema_ratios.sql").read_text())
    cols = [r[1] for r in con.execute("PRAGMA table_info(financial_ratios)")]
    out = df[cols].astype(object).where(df[cols].notna(), None)
    con.executemany(f"INSERT INTO financial_ratios ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    out.values.tolist())
    con.commit()


def capital_allocation_frame(df: pd.DataFrame, cf: pd.DataFrame, pl: pd.DataFrame) -> pd.DataFrame:
    m = cf.merge(pl[["company_id", "year", "net_profit"]], on=["company_id", "year"], how="left")
    out = pd.DataFrame({
        "company_id": m["company_id"], "year": m["year"],
        "cfo_sign": m["operating_activity"].map(K.sign), "cfi_sign": m["investing_activity"].map(K.sign),
        "cff_sign": m["financing_activity"].map(K.sign),
        "pattern_label": [K.capital_allocation_pattern(o, i, fl, K.cfo_pat_ratio(o, n))
                          for o, i, fl, n in zip(m["operating_activity"], m["investing_activity"],
                                                 m["financing_activity"], m["net_profit"])]})
    return out.sort_values(["company_id", "year"]).reset_index(drop=True)


def run(db: Path = DB, out_dir: Path = OUT) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    inp = load_inputs(con)
    df = compute(inp)
    write(df, con)
    capital_allocation_frame(df, inp["cf"], inp["pl"]).to_csv(out_dir / "capital_allocation.csv", index=False)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
    return df


if __name__ == "__main__":
    d = run()
    print(f"financial_ratios rows: {len(d)}; companies: {d.company_id.nunique()}")
