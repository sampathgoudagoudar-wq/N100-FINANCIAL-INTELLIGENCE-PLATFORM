"""Data-quality rules DQ-01 … DQ-16 (project document, section 14).

Each rule returns a DataFrame of *violating* rows (empty = rule satisfied).
14 rules are unit-testable offline; DQ-13 (HTTP URL check) needs network access and DQ-15 is an
informational counter, so both are intentionally not part of the 14.
"""
from __future__ import annotations

import re

import pandas as pd

SEVERITY = {
    "DQ-01": "CRITICAL", "DQ-02": "CRITICAL", "DQ-03": "CRITICAL", "DQ-04": "WARNING",
    "DQ-05": "WARNING", "DQ-06": "WARNING", "DQ-07": "CRITICAL", "DQ-08": "CRITICAL",
    "DQ-09": "WARNING", "DQ-10": "WARNING", "DQ-11": "WARNING", "DQ-12": "WARNING",
    "DQ-14": "WARNING", "DQ-16": "WARNING",
}
YEAR_RE = re.compile(r"^\d{4}-\d{2}$")


def dq01_company_pk_unique(companies: pd.DataFrame) -> pd.DataFrame:
    return companies[companies["id"].duplicated(keep=False)]


def dq02_annual_pk_unique(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.duplicated(["company_id", "year"], keep=False)]


def dq03_fk_integrity(child: pd.DataFrame, companies: pd.DataFrame) -> pd.DataFrame:
    return child[~child["company_id"].isin(set(companies["id"]))]


def dq04_balance_sheet_balances(bs: pd.DataFrame, tol: float = 0.01) -> pd.DataFrame:
    gap = (bs["total_assets"] - bs["total_liabilities"]).abs() / bs["total_assets"].where(bs["total_assets"] != 0)
    return bs[gap >= tol]


def dq05_opm_cross_check(pl: pd.DataFrame, tol: float = 1.0) -> pd.DataFrame:
    calc = pl["operating_profit"] / pl["sales"].where(pl["sales"] != 0) * 100
    diff = (pl["opm_percentage"] - calc).abs()
    return pl[diff >= tol]


def dq06_positive_sales(pl: pd.DataFrame, banks: set[str] | None = None) -> pd.DataFrame:
    banks = banks or set()
    return pl[(pl["sales"] <= 0) & ~pl["company_id"].isin(banks)]


def dq07_year_format(df: pd.DataFrame, col: str = "year_std") -> pd.DataFrame:
    return df[~df[col].astype(str).str.match(YEAR_RE)]


def dq08_ticker_format(df: pd.DataFrame, col: str = "company_id") -> pd.DataFrame:
    s = df[col].astype(str)
    ok = (s == s.str.strip().str.upper()) & s.str.len().between(2, 12)
    return df[~ok]


def dq09_net_cash_check(cf: pd.DataFrame, tol: float = 10) -> pd.DataFrame:
    gap = (cf["net_cash_flow"] - (cf["operating_activity"] + cf["investing_activity"] + cf["financing_activity"])).abs()
    return cf[gap > tol]


def dq10_non_negative_fixed_assets(bs: pd.DataFrame) -> pd.DataFrame:
    return bs[bs["fixed_assets"] < 0]


def dq11_tax_rate_range(pl: pd.DataFrame) -> pd.DataFrame:
    return pl[(pl["tax_percentage"] < 0) | (pl["tax_percentage"] > 60)]


def dq12_dividend_payout_cap(pl: pd.DataFrame) -> pd.DataFrame:
    return pl[pl["dividend_payout"] > 200]


def dq14_eps_sign_consistency(pl: pd.DataFrame) -> pd.DataFrame:
    return pl[(pl["net_profit"] > 0) & (pl["eps"] <= 0)]


def dq16_coverage(pl: pd.DataFrame, bs: pd.DataFrame, cf: pd.DataFrame, min_years: int = 5) -> pd.DataFrame:
    """Companies with fewer than `min_years` annual records in any of P&L, BS, CF."""
    rows = []
    for name, df in (("profitandloss", pl), ("balancesheet", bs), ("cashflow", cf)):
        n = df.groupby("company_id")["year"].nunique()
        for cid, cnt in n[n < min_years].items():
            rows.append({"company_id": cid, "table": name, "years": int(cnt)})
    return pd.DataFrame(rows, columns=["company_id", "table", "years"])


def run_all(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Run every offline rule on the cleaned tables; one summary row per rule."""
    co, pl, bs, cf = t["companies"], t["profitandloss"], t["balancesheet"], t["cashflow"]
    banks = set(t["sectors"].loc[t["sectors"]["broad_sector"] == "Financials", "company_id"])
    std = lambda d: d.assign(year_std=d["year"].astype(int).astype(str) + "-03")  # noqa: E731
    out = {
        "DQ-01": len(dq01_company_pk_unique(co)),
        "DQ-02": sum(len(dq02_annual_pk_unique(d)) for d in (pl, bs, cf)),
        "DQ-03": sum(len(dq03_fk_integrity(d, co)) for d in (pl, bs, cf)),
        "DQ-04": len(dq04_balance_sheet_balances(bs)),
        "DQ-05": len(dq05_opm_cross_check(pl)),
        "DQ-06": len(dq06_positive_sales(pl, banks)),
        "DQ-07": sum(len(dq07_year_format(std(d))) for d in (pl, bs, cf)),
        "DQ-08": sum(len(dq08_ticker_format(d)) for d in (co.rename(columns={"id": "company_id"}), pl, bs, cf)),
        "DQ-09": len(dq09_net_cash_check(cf)),
        "DQ-10": len(dq10_non_negative_fixed_assets(bs)),
        "DQ-11": len(dq11_tax_rate_range(pl)),
        "DQ-12": len(dq12_dividend_payout_cap(pl)),
        "DQ-14": len(dq14_eps_sign_consistency(pl)),
        "DQ-16": len(dq16_coverage(pl, bs, cf)),
    }
    return pd.DataFrame({"rule": list(out), "severity": [SEVERITY[k] for k in out], "violations": list(out.values())})
