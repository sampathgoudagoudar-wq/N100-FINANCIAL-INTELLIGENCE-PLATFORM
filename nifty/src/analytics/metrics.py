"""KPI panel + latest-year snapshot used by the screener and the peer engine.

Formulas follow section 13 (KPI Reference) of the project document. They are
recomputed from the cleaned raw statements because the supplied
financial_ratios.xlsx contains duplicated / unit-corrupted rows
(e.g. OPM up to 47,971 %, ROE up to 17,886 %).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    return (a / b.where(b != 0)).replace([np.inf, -np.inf], np.nan)


def build_panel(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per (company_id, year) with all base KPIs."""
    pl, bs, cf = t["profitandloss"], t["balancesheet"], t["cashflow"]
    keys = ["company_id", "year"]
    p = (pl.merge(bs.drop(columns=["id"]), on=keys, how="left", suffixes=("", "_bs"))
           .merge(cf.drop(columns=["id"]), on=keys, how="left", suffixes=("", "_cf")))

    equity = p["equity_capital"].fillna(0) + p["reserves"].fillna(0)
    equity = equity.where(equity > 0)                      # ROE/D-E None if equity <= 0
    borrow = p["borrowings"].fillna(0)

    ebitda = p["operating_profit"]
    ebit = (ebitda - p["depreciation"].fillna(0))
    # banks/NBFCs have no operating_profit: fall back to PBT + interest
    ebit = ebit.fillna(p["profit_before_tax"] + p["interest"].fillna(0))

    out = p[keys].copy()
    out["sales"] = p["sales"]
    out["net_profit"] = p["net_profit"]
    out["eps"] = p["eps"]
    out["roe"] = _safe_div(p["net_profit"], equity) * 100
    out["roce"] = _safe_div(ebit, equity + borrow) * 100
    out["npm"] = _safe_div(p["net_profit"], p["sales"].where(p["sales"] > 0)) * 100
    opm_calc = _safe_div(ebitda, p["sales"].where(p["sales"] > 0)) * 100
    out["opm"] = opm_calc.fillna(p["opm_percentage"])
    out["de"] = _safe_div(borrow, equity)
    interest = p["interest"]
    icr = _safe_div(p["operating_profit"].fillna(ebit) + p["other_income"].fillna(0), interest)
    icr = icr.mask(interest == 0, np.inf)                  # Debt Free -> infinity
    out["icr"] = icr
    out["asset_turnover"] = _safe_div(p["sales"], p["total_assets"])
    out["fcf"] = p["operating_activity"] + p["investing_activity"]
    out["cfo_pat"] = _safe_div(p["operating_activity"], p["net_profit"].where(p["net_profit"] > 0))
    out["dividend_payout"] = p["dividend_payout"]
    out["borrowings"] = p["borrowings"]
    out["equity"] = equity
    return out


def _cagr(panel: pd.DataFrame, col: str, years: int) -> tuple[pd.Series, pd.Series]:
    """CAGR (%) for each (company, year) over `years`, plus a flag column.

    flag = 'Turnaround' when both end-points exist but base <= 0 or end <= 0 (CAGR undefined),
           'No data'    when the base year is missing (history shorter than `years`), else ''.
    """
    lag = panel[["company_id", "year", col]].copy()
    lag["year"] = lag["year"] + years
    m = panel[["company_id", "year", col]].merge(
        lag, on=["company_id", "year"], how="left", suffixes=("", "_base"))
    end, base = m[col], m[f"{col}_base"]
    ok = (end > 0) & (base > 0)
    val = (end / base) ** (1 / years) - 1
    flag = np.where(ok, "", np.where(end.isna() | base.isna(), "No data", "Turnaround"))
    return (pd.Series(np.where(ok, val * 100, np.nan), index=panel.index),
            pd.Series(flag, index=panel.index))


def add_growth(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["company_id", "year"]).reset_index(drop=True)
    for col, name in (("sales", "rev"), ("net_profit", "pat"), ("eps", "eps"), ("fcf", "fcf")):
        for n in (3, 5):
            panel[f"{name}_cagr_{n}y"], panel[f"{name}_cagr_{n}y_flag"] = _cagr(panel, col, n)
    # prior-year D/E for the "declining" test
    prev = panel[["company_id", "year", "de"]].copy()
    prev["year"] += 1
    panel = panel.merge(prev.rename(columns={"de": "de_prev"}), on=["company_id", "year"], how="left")
    return panel


def _repair_balance_sheet_anomalies(snap: pd.DataFrame, companies: pd.DataFrame) -> pd.DataFrame:
    """Some balance sheets are on a different scale from the P&L (BEL, HAL, INDIGO, LT, PNB:
    computed ROE/ROCE > 100 %, asset turnover > 10x) and SBIN has no balance sheet at all.
    Ratios that mix P&L and balance-sheet values are unusable for these companies, so we
    fall back to the pre-computed ROE/ROCE in companies.xlsx and blank asset turnover.
    Pure balance-sheet ratios (D/E) are scale-free and are kept."""
    src = companies.set_index("id")
    roe_src = snap["company_id"].map(src["roe_percentage"])
    roce_src = snap["company_id"].map(src["roce_percentage"])
    no_bs = snap["roe"].isna() & snap["equity"].isna()
    anomaly = (snap["roe"] > 100) | (snap["roce"] > 100) | (snap["asset_turnover"] > 10)
    fix = anomaly | no_bs
    snap["roe_source"] = np.where(fix, "companies.xlsx", "computed")
    snap["bs_anomaly"] = anomaly
    snap.loc[fix, "roe"] = roe_src[fix]
    snap.loc[fix, "roce"] = roce_src[fix]
    snap.loc[anomaly, "asset_turnover"] = np.nan
    return snap


def latest_snapshot(t: dict[str, pd.DataFrame], panel: pd.DataFrame | None = None,
                    year: int | None = None) -> pd.DataFrame:
    """One row per company: latest annual KPIs (as of `year` if given) + valuation + names/sectors."""
    if panel is None:
        panel = add_growth(build_panel(t))
    base = panel if year is None else panel[panel["year"] <= year]
    snap = base.sort_values("year").groupby("company_id").tail(1).copy()
    snap = snap.rename(columns={"year": "fy"})

    mc = t["market_cap"]
    mc = mc[mc["year"] == (mc["year"].max() if year is None else min(year, mc["year"].max()))][
        ["company_id", "year", "market_cap_crore", "pe_ratio", "pb_ratio", "dividend_yield_pct"]]
    mc = mc.rename(columns={"year": "mkt_year", "market_cap_crore": "market_cap",
                            "pe_ratio": "pe", "pb_ratio": "pb", "dividend_yield_pct": "div_yield"})
    snap = snap.merge(mc, on="company_id", how="left")
    snap["fcf_yield"] = _safe_div(snap["fcf"], snap["market_cap"]) * 100

    co = t["companies"][["id", "company_name"]].rename(columns={"id": "company_id"})
    se = t["sectors"][["company_id", "broad_sector", "sub_sector", "market_cap_category"]]
    snap = co.merge(se, on="company_id", how="left").merge(snap, on="company_id", how="left")
    snap = _repair_balance_sheet_anomalies(snap, t["companies"])
    snap["icr_label"] = np.where(np.isinf(snap["icr"]), "Debt Free", "")
    snap["fcf_positive"] = snap["fcf"] > 0
    snap["de_declining"] = snap["de"] < snap["de_prev"]
    return snap.reset_index(drop=True)
