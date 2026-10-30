"""Schema / data-quality validator: DQ-01 ... DQ-16 (Sprint 1, Day 03).

Every rule is a function that takes DataFrame(s) and returns the (possibly
cleaned) frame plus a list of failure records. A failure record is a dict with
the columns in FAILURE_COLUMNS, so the loader can dump them straight into
output/validation_failures.csv.

Row-level rules never mutate their input.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

import pandas as pd

from .normaliser import (MISSING, PARSE_ERROR, TICKER_ALIASES, TTM, YEAR_FORMAT, is_valid_ticker,
                         normalize_ticker, normalize_year)

FAILURE_COLUMNS = ["rule_id", "rule_name", "severity", "table", "source_id",
                   "company_id", "year", "detail", "action", "status"]

RULE_NAMES = {
    "DQ-01": "Company PK uniqueness", "DQ-02": "Annual PK uniqueness",
    "DQ-03": "FK integrity", "DQ-04": "Balance sheet balance",
    "DQ-05": "OPM cross-check", "DQ-06": "Positive sales",
    "DQ-07": "Year format", "DQ-08": "Ticker format",
    "DQ-09": "Net cash check", "DQ-10": "Non-negative fixed assets",
    "DQ-11": "Tax rate range", "DQ-12": "Dividend payout cap",
    "DQ-13": "URL validity", "DQ-14": "EPS sign consistency",
    "DQ-15": "BS strict balance (info)", "DQ-16": "Coverage check",
}
SEVERITY = {
    "DQ-01": "CRITICAL", "DQ-02": "CRITICAL", "DQ-03": "CRITICAL", "DQ-07": "CRITICAL",
    "DQ-08": "CRITICAL", "DQ-15": "INFO",
}  # everything else is WARNING

# status values: REJECTED, RESOLVED (auto-fixed / deduped / excluded), FLAGGED (needs analyst), INFO
Failure = dict


def _f(rule: str, table: str, row: Optional[pd.Series], detail: str, action: str,
       status: str, severity: Optional[str] = None, company_id=None, year=None) -> Failure:
    get = (lambda k: row.get(k) if row is not None else None)
    return {
        "rule_id": rule, "rule_name": RULE_NAMES[rule],
        "severity": severity or SEVERITY.get(rule, "WARNING"),
        "table": table,
        "source_id": get("source_id") if row is not None and "source_id" in row else get("id"),
        "company_id": company_id if company_id is not None else get("company_id"),
        "year": year if year is not None else get("year"),
        "detail": detail, "action": action, "status": status,
    }


def failures_frame(failures: Iterable[Failure]) -> pd.DataFrame:
    return pd.DataFrame(list(failures), columns=FAILURE_COLUMNS)


# ----------------------------------------------------------------- pre-load rules
def dq08_tickers(df: pd.DataFrame, table: str, col: str = "company_id"):
    """Normalise tickers silently; reject missing / out-of-range-length ones."""
    df = df.copy()
    df[col] = df[col].map(normalize_ticker)
    fixed = df[col].isin(TICKER_ALIASES)
    fails0 = [_f("DQ-08", table, r, f"known typo {r[col]!r} corrected to {TICKER_ALIASES[r[col]]!r}",
                 "Ticker remapped via TICKER_ALIASES", "RESOLVED", severity="WARNING")
              for _, r in df[fixed].iterrows()]
    df[col] = df[col].replace(TICKER_ALIASES)
    bad = ~df[col].map(is_valid_ticker)
    fails = fails0 + [_f("DQ-08", table, r, f"ticker {r[col]!r} invalid (len must be 2-12)",
                         "Row rejected", "REJECTED") for _, r in df[bad].iterrows()]
    return df[~bad].reset_index(drop=True), fails, int(bad.sum())


def dq07_years(df: pd.DataFrame, table: str, col: str = "year"):
    """Normalise year labels to YYYY-MM. Returns (clean, failures, n_rejected, n_ttm).

    TTM rows are valid but not a fiscal year: they are excluded and logged as INFO.
    Anything else unparseable is a CRITICAL reject.
    """
    df = df.copy()
    raw = df[col].copy()
    df[col] = raw.map(normalize_year)
    fails: list[Failure] = []
    ttm = df[col] == TTM
    bad = df[col] == PARSE_ERROR
    for i in df.index[ttm]:
        fails.append(_f("DQ-07", table, df.loc[i], "TTM row is not a fiscal year",
                        "Excluded from fiscal time series", "RESOLVED", severity="INFO",
                        year=raw[i]))
    for i in df.index[bad]:
        fails.append(_f("DQ-07", table, df.loc[i], f"unparseable year {raw[i]!r}",
                        "Row rejected; raw value logged", "REJECTED", year=raw[i]))
    keep = ~(ttm | bad)
    return df[keep].reset_index(drop=True), fails, int(bad.sum()), int(ttm.sum())


def dq01_company_pk(companies: pd.DataFrame):
    """CRITICAL: ticker must be unique. Returns (ok, failures)."""
    col = "company_id" if "company_id" in companies.columns else "id"
    dup = companies[companies[col].duplicated(keep=False)]
    fails = [_f("DQ-01", "companies", r, f"duplicate ticker {r[col]}", "Halt load", "REJECTED",
                company_id=r[col]) for _, r in dup.iterrows()]
    return (len(dup) == 0), fails


def dq03_fk(df: pd.DataFrame, table: str, valid_ids: set, col: str = "company_id"):
    """Reject orphan rows whose company_id is not in companies."""
    orphan = ~df[col].isin(valid_ids)
    fails = []
    for _, r in df[orphan].iterrows():
        fails.append(_f("DQ-03", table, r, f"company_id {r[col]!r} not in companies",
                        "Orphan row excluded (out-of-universe ticker)", "RESOLVED"))
    return df[~orphan].reset_index(drop=True), fails, int(orphan.sum())


def dq02_dedupe(df: pd.DataFrame, table: str, keys: list[str], value_cols: Optional[list[str]] = None):
    """Deduplicate on keys, keeping the last occurrence.

    Refinement of 'keep last': an all-zero numeric row never beats a populated one
    (the cash-flow source has zero-filled placeholder duplicates).
    Identical duplicates are logged as INFO-level resolved; conflicting ones are
    logged as FLAGGED so an analyst can confirm the surviving row.
    """
    if not df.duplicated(keys).any():
        return df, [], 0
    value_cols = value_cols or [c for c in df.columns
                                if c not in keys and c not in ("id", "source_id") and
                                pd.api.types.is_numeric_dtype(df[c])]
    out_idx, fails, removed = [], [], 0
    for key, g in df.groupby(keys, sort=False):
        if len(g) == 1:
            out_idx.append(g.index[0]); continue
        cmp_cols = [c for c in df.columns if c not in ("id", "source_id")]
        conflicting = len(g[cmp_cols].drop_duplicates()) > 1
        pool = g
        if value_cols:
            nonzero = g[(g[value_cols].fillna(0) != 0).any(axis=1)]
            if len(nonzero):
                pool = nonzero
        keep = pool.index[-1]
        out_idx.append(keep)
        removed += len(g) - 1
        k = key if isinstance(key, tuple) else (key,)
        label = "/".join(str(x) for x in k)
        dropped_ids = [str(g.loc[i].get("source_id", g.loc[i].get("id"))) for i in g.index if i != keep]
        fails.append(_f("DQ-02", table, df.loc[keep],
                        f"{len(g)} rows for {label}; {'CONFLICTING values' if conflicting else 'identical values'}; "
                        f"dropped source ids {','.join(dropped_ids)}",
                        "Kept last populated occurrence",
                        "FLAGGED" if conflicting else "RESOLVED",
                        severity="CRITICAL"))
    out_idx = sorted(set(out_idx))
    return df.loc[out_idx].reset_index(drop=True), fails, removed


# ---------------------------------------------------------------- post-clean rules
def dq04_bs_balance(bs: pd.DataFrame, tol: float = 0.01):
    fails, strict = [], 0
    for _, r in bs.iterrows():
        ta, tl = r["total_assets"], r["total_liabilities"]
        if pd.isna(ta) or pd.isna(tl) or ta == 0:
            continue
        gap = abs(ta - tl) / abs(ta)
        if gap >= tol:
            fails.append(_f("DQ-04", "balancesheet", r,
                            f"assets={ta:g}, liabilities={tl:g}, gap={gap:.2%}",
                            "Row flagged for analyst review", "FLAGGED"))
        elif ta != tl:
            strict += 1       # DQ-15: passes DQ-04 but not strictly equal
    return fails, strict


def dq05_opm(pl: pd.DataFrame, tol: float = 1.0):
    fails = []
    for _, r in pl.iterrows():
        if pd.isna(r["opm_percentage"]) or pd.isna(r["operating_profit"]) or not r["sales"]:
            continue
        calc = r["operating_profit"] / r["sales"] * 100
        if abs(r["opm_percentage"] - calc) >= tol:
            fails.append(_f("DQ-05", "profitandloss", r,
                            f"source OPM={r['opm_percentage']:g}, computed={calc:.2f}",
                            "Flagged; Ratio Engine uses computed OPM", "FLAGGED"))
    return fails


def dq06_positive_sales(pl: pd.DataFrame, bank_ids: set):
    bad = pl[(pl["sales"] <= 0) & ~pl["company_id"].isin(bank_ids)]
    return [_f("DQ-06", "profitandloss", r, f"sales={r['sales']:g}",
               "Flagged; exclude from growth CAGR", "FLAGGED") for _, r in bad.iterrows()]


def dq09_net_cash(cf: pd.DataFrame, tol: float = 10.0):
    cf = cf.copy()
    fails = []
    comp = cf[["operating_activity", "investing_activity", "financing_activity"]]
    ok_rows = comp.notna().all(axis=1) & cf["net_cash_flow"].notna()
    calc = comp.sum(axis=1)
    mism = ok_rows & ((cf["net_cash_flow"] - calc).abs() > tol)
    for i in cf.index[mism]:
        r = cf.loc[i]
        fails.append(_f("DQ-09", "cashflow", r,
                        f"net_cash_flow={r['net_cash_flow']:g}, CFO+CFI+CFF={calc[i]:g}",
                        "net_cash_flow recomputed from components", "RESOLVED"))
        cf.loc[i, "net_cash_flow"] = calc[i]
    return cf, fails


def dq10_fixed_assets(bs: pd.DataFrame):
    bs = bs.copy()
    neg = bs["fixed_assets"] < 0
    fails = [_f("DQ-10", "balancesheet", bs.loc[i], f"fixed_assets={bs.loc[i, 'fixed_assets']:g}",
                "Coerced to 0", "RESOLVED") for i in bs.index[neg]]
    bs.loc[neg, "fixed_assets"] = 0
    return bs, fails


def dq11_tax(pl: pd.DataFrame):
    bad = pl[pl["tax_percentage"].notna() & ~pl["tax_percentage"].between(0, 60)]
    return [_f("DQ-11", "profitandloss", r, f"tax_percentage={r['tax_percentage']:g}",
               "Flagged", "FLAGGED") for _, r in bad.iterrows()]


def dq12_dividend(pl: pd.DataFrame):
    bad = pl[pl["dividend_payout"] > 200]
    return [_f("DQ-12", "profitandloss", r, f"dividend_payout={r['dividend_payout']:g}",
               "Flagged for analyst confirmation", "FLAGGED") for _, r in bad.iterrows()]


def dq14_eps(pl: pd.DataFrame):
    bad = pl[(pl["net_profit"] > 0) & ~(pl["eps"] > 0)]
    return [_f("DQ-14", "profitandloss", r,
               f"net_profit={r['net_profit']:g}, eps={r['eps'] if pd.notna(r['eps']) else 'null'}",
               "Flagged; derive from net_profit/shares downstream", "FLAGGED")
            for _, r in bad.iterrows()]


def dq13_urls(documents: pd.DataFrame, enabled: bool = False, timeout: float = 5.0):
    """HEAD-check annual report URLs. Off by default (network-bound)."""
    if not enabled:
        return [_f("DQ-13", "documents", None, "URL validation skipped (CHECK_URLS=false)",
                   "Run with CHECK_URLS=true on a networked host", "INFO", severity="INFO",
                   company_id="*", year="*")]
    import requests
    fails = []
    for _, r in documents.dropna(subset=["annual_report"]).iterrows():
        try:
            code = requests.head(r["annual_report"], timeout=timeout, allow_redirects=True).status_code
        except Exception as exc:  # noqa: BLE001
            code = f"error:{type(exc).__name__}"
        if code != 200:
            fails.append(_f("DQ-13", "documents", r, f"status={code}", "Logged; row kept", "FLAGGED"))
    return fails


def dq16_coverage(companies: pd.DataFrame, tables: dict[str, pd.DataFrame], min_years: int = 5):
    fails = []
    for tname, df in tables.items():
        counts = df.groupby("company_id")["year"].nunique()
        for cid in companies["id"]:
            n = int(counts.get(cid, 0))
            if n < min_years:
                note = "exclude from CAGR (<3 yrs)" if n < 3 else "short history"
                fails.append(_f("DQ-16", tname, None, f"{n} year(s) of data; {note}",
                                "Flagged", "FLAGGED", company_id=cid, year=f"{n} yrs"))
    return fails


def check_year_format(series: pd.Series) -> bool:
    """DQ-07 post-condition: every value matches YYYY-MM."""
    return bool(series.astype(str).map(lambda s: bool(YEAR_FORMAT.match(s))).all())
