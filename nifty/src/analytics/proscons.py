"""Pros / cons: source rows (prosandcons.xlsx, ~8 companies) + KPI-rule generated items for all 92."""
import numpy as np
import pandas as pd


def generate(row: pd.Series, panel_c: pd.DataFrame) -> tuple[list[str], list[str]]:
    pros, cons = [], []
    g = lambda k: row.get(k)  # noqa: E731
    ok = lambda v: v is not None and not pd.isna(v)  # noqa: E731
    roe_hist = panel_c.sort_values("year")["roe"].tail(3)
    if len(roe_hist.dropna()) == 3 and (roe_hist > 20).all():
        pros.append("ROE above 20% for each of the last 3 years")
    elif ok(g("roe")) and g("roe") < 8:
        cons.append(f"Low return on equity ({g('roe'):.1f}%)")
    if ok(g("de")) and g("broad_sector") != "Financials":
        if g("de") < 0.1:
            pros.append("Almost debt free (D/E below 0.1)")
        elif g("de") > 2:
            cons.append(f"High leverage: D/E of {g('de'):.1f}")
    if ok(g("icr")) and not np.isinf(g("icr")) and g("icr") < 1.5 and g("broad_sector") != "Financials":
        cons.append(f"Weak interest coverage ({g('icr'):.1f}x)")
    fcf3 = panel_c.sort_values("year")["fcf"].tail(3)
    if len(fcf3.dropna()) == 3 and (fcf3 < 0).all() and g("broad_sector") != "Financials":
        cons.append("Negative free cash flow for 3 consecutive years")
    elif ok(g("fcf")) and g("fcf") > 0 and ok(g("cfo_pat")) and g("cfo_pat") > 1 and g("broad_sector") != "Financials":
        pros.append("Positive free cash flow with CFO above reported profit")
    if ok(g("pat_cagr_5y")) and g("pat_cagr_5y") > 15:
        pros.append(f"Profit has compounded at {g('pat_cagr_5y'):.1f}% a year over 5 years")
    if ok(g("rev_cagr_5y")) and g("rev_cagr_5y") < 5:
        cons.append(f"Slow revenue growth ({g('rev_cagr_5y'):.1f}% CAGR over 5 years)")
    elif ok(g("rev_cagr_5y")) and g("rev_cagr_5y") > 15:
        pros.append(f"Strong revenue growth ({g('rev_cagr_5y'):.1f}% CAGR over 5 years)")
    if ok(g("dividend_payout")) and 30 <= g("dividend_payout") <= 60:
        pros.append(f"Balanced dividend payout of {g('dividend_payout'):.0f}%")
    if ok(g("pe")) and g("pe") > 60:
        cons.append(f"Expensive on earnings (P/E {g('pe'):.0f})")
    if ok(g("npm")) and g("npm") < 0:
        cons.append("Loss-making in the latest year")
    return pros, cons
