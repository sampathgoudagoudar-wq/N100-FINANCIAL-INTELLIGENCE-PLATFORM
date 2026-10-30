"""Financial ratio engine: KPI panel, CAGR with edge-case flags, capital-allocation classes."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.etl.clean import OUT, load_clean

logger = logging.getLogger(__name__)

PATTERNS = {  # (CFO sign, CFI sign, CFF sign) -> label
    ("+", "-", "-"): "Reinvestor",
    ("+", "-", "+"): "Aggressive Expander",
    ("+", "+", "-"): "Shareholder Returns",
    ("+", "+", "+"): "Cash Accumulator",
    ("-", "-", "+"): "Distress Signal",
    ("-", "+", "+"): "Distress - Asset Liquidation",
    ("-", "+", "-"): "Cash Burn - Divestment Funded",
    ("-", "-", "-"): "Cash Drain",
}


def sgn(x: float) -> str | None:
    """Return '+' for >=0, '-' for <0, None for NaN."""
    if pd.isna(x):
        return None
    return "+" if x >= 0 else "-"


def safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise a/b returning NaN where b is 0/NaN."""
    return (a / b.where(b != 0)).astype(float)


def build_panel(tables: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """P&L spine left-joined with balance sheet, cash flow, sector; adds all KPIs."""
    t = tables or load_clean()
    pl = t["profitandloss"].drop(columns=["id", "raw_year", "partial_period"])
    bs = t["balancesheet"].drop(columns=["id", "raw_year", "partial_period"])
    cf = t["cashflow"].drop(columns=["id", "raw_year", "partial_period"])
    p = pl.merge(bs, on=["company_id", "year"], how="left").merge(cf, on=["company_id", "year"], how="left")
    p = p.merge(t["sectors"][["company_id", "broad_sector", "sub_sector"]], on="company_id", how="left")
    p["fy"] = p["year"].str[:4].astype(int)
    p["is_financial"] = p["broad_sector"].eq("Financials")

    eq = p.equity_capital + p.reserves
    p["total_equity"] = eq
    p["npm"] = safe_div(p.net_profit, p.sales) * 100
    p["opm"] = safe_div(p.operating_profit, p.sales) * 100
    p["roe"] = safe_div(p.net_profit, eq.where(eq > 0)) * 100
    p["ebit"] = p.operating_profit - p.depreciation
    p["roce"] = safe_div(p.ebit, (eq + p.borrowings).where((eq + p.borrowings) > 0)) * 100
    p["de"] = safe_div(p.borrowings, eq.where(eq > 0))
    p.loc[(p.borrowings == 0) & (eq > 0), "de"] = 0.0
    p["icr"] = safe_div(p.operating_profit + p.other_income, p.interest.where(p.interest > 0))
    p["debt_free"] = p.borrowings.fillna(-1).eq(0)
    p["asset_turnover"] = safe_div(p.sales, p.total_assets)
    p["fcf"] = p.operating_activity + p.investing_activity
    p["capex"] = p.investing_activity.abs()
    p["cfo_pat"] = safe_div(p.operating_activity, p.net_profit.where(p.net_profit > 0))
    p["capex_intensity"] = safe_div(p.investing_activity.abs(), p.sales) * 100
    p["fcf_conversion"] = safe_div(p.fcf, p.operating_profit.where(p.operating_profit > 0)) * 100
    p["net_debt"] = p.borrowings - p.investments
    p["nd_ebitda"] = safe_div(p.net_debt, p.operating_profit.where(p.operating_profit > 0))
    p["cfo_sign"] = p.operating_activity.map(sgn)
    p["cfi_sign"] = p.investing_activity.map(sgn)
    p["cff_sign"] = p.financing_activity.map(sgn)
    p["pattern_label"] = [
        PATTERNS.get((a, b, c)) if a and b and c else None
        for a, b, c in zip(p.cfo_sign, p.cfi_sign, p.cff_sign)
    ]
    return p.sort_values(["company_id", "fy", "year"]).reset_index(drop=True)


def cagr(series: pd.Series, years: pd.Series, n: int, tol: int = 1) -> tuple[float | None, str]:
    """CAGR over ~n years ending at the last available year; returns (pct, flag)."""
    s = pd.DataFrame({"y": years.values, "v": series.values}).dropna().sort_values("y")
    if len(s) < 3:
        return None, "INSUFFICIENT"
    end = s.iloc[-1]
    target = end.y - n
    cand = s[(s.y - target).abs() <= tol]
    if cand.empty:
        return None, "INSUFFICIENT"
    base = cand.iloc[(cand.y - target).abs().argmin()]
    gap = end.y - base.y
    if gap < 2:
        return None, "INSUFFICIENT"
    b, e = float(base.v), float(end.v)
    if b == 0:
        return None, "ZERO_BASE"
    if b > 0 and e > 0:
        return ((e / b) ** (1 / gap) - 1) * 100, "OK"
    if b > 0 and e <= 0:
        return None, "DECLINE_TO_LOSS"
    if b < 0 and e > 0:
        return None, "TURNAROUND"
    return None, "BOTH_NEGATIVE"


def company_cagrs(p: pd.DataFrame) -> pd.DataFrame:
    """3/5/10-year revenue, PAT, EPS and FCF CAGRs per company."""
    rows = []
    for cid, g in p.groupby("company_id"):
        r = {"company_id": cid}
        for col, tag in (("sales", "rev"), ("net_profit", "pat"), ("eps", "eps"), ("fcf", "fcf")):
            for n in (3, 5, 10):
                v, f = cagr(g[col], g["fy"], n)
                r[f"{tag}_cagr_{n}y"], r[f"{tag}_cagr_{n}y_flag"] = v, f
        rows.append(r)
    return pd.DataFrame(rows)


def run() -> pd.DataFrame:
    """Build panel and write capital_allocation.csv + ratio_edge_cases.log."""
    t = load_clean()
    p = build_panel(t)
    ca = p[["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"]].copy()
    ca.to_csv(OUT / "capital_allocation.csv", index=False)
    t["dq_log"].to_csv(OUT / "validation_failures.csv", index=False)
    cg = company_cagrs(p)
    with open(OUT / "ratio_edge_cases.log", "w") as fh:
        for _, r in cg.iterrows():
            for k in r.index:
                if k.endswith("_flag") and r[k] not in ("OK", "INSUFFICIENT"):
                    fh.write(f"{r.company_id}\t{k}\t{r[k]}\n")
    return p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = run()
    print(p.shape, p.company_id.nunique())
    ca = pd.read_csv(OUT / "capital_allocation.csv")
    print("capital_allocation rows", len(ca), "companies", ca.company_id.nunique(), "unlabelled", ca.pattern_label.isna().sum())
