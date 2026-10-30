"""Load and clean raw Nifty 100 Excel files (header=1 core files)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
SUP = ROOT / "data" / "supporting"
OUT = ROOT / "output"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def normalize_ticker(s: pd.Series) -> pd.Series:
    """Strip whitespace and upper-case tickers."""
    return s.astype(str).str.strip().str.upper()


def normalize_year(raw: object) -> str:
    """Map labels such as 'Mar 2023', 'Mar-23', 2023 to 'YYYY-MM'; else PARSE_ERROR."""
    s = str(raw).strip()
    m = re.match(r"^([A-Za-z]{3})[ -](\d{4})$", s)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    m = re.match(r"^([A-Za-z]{3})[ -](\d{2})$", s)
    if m and m.group(1).lower() in MONTHS:
        return f"20{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    m = re.match(r"^(\d{4})(\.0)?$", s)
    if m:
        return f"{m.group(1)}-03"
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return s
    # '9m' partial period / '15' 15-month period: keep the closing month, flag later
    m = re.match(r"^([A-Za-z]{3}) (\d{4}) (\d+m?)$", s)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    return "PARSE_ERROR"


def _load(name: str) -> pd.DataFrame:
    return pd.read_excel(RAW / f"{name}.xlsx", header=1)


def load_clean() -> dict[str, pd.DataFrame]:
    """Return cleaned companies, pl, bs, cf, sectors plus a data-quality log."""
    dq: list[dict] = []

    def log(table, cid, year, issue, sev, action):
        dq.append(dict(table=table, company_id=cid, year=year, issue=issue, severity=sev, action=action))

    co = _load("companies")
    co["id"] = normalize_ticker(co["id"])
    co["company_name"] = co["company_name"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    valid = set(co["id"])
    sec = pd.read_excel(SUP / "sectors.xlsx")
    sec["company_id"] = normalize_ticker(sec["company_id"])

    out: dict[str, pd.DataFrame] = {"companies": co, "sectors": sec}
    for name in ("profitandloss", "balancesheet", "cashflow"):
        df = _load(name)
        df["company_id"] = normalize_ticker(df["company_id"])
        df["raw_year"] = df["year"].astype(str)
        orphans = df[~df.company_id.isin(valid)]
        for t, n in orphans.groupby("company_id").size().items():
            log(name, t, "", f"orphan ticker not in companies ({n} rows)", "CRITICAL", "rejected (DQ-03)")
        df = df[df.company_id.isin(valid)].copy()
        ttm = df[df.raw_year.str.upper() == "TTM"]
        df = df[df.raw_year.str.upper() != "TTM"].copy()          # TTM is not an annual period
        if name == "profitandloss":
            out["ttm"] = ttm
        df["year"] = df["raw_year"].map(normalize_year)
        bad = df[df.year == "PARSE_ERROR"]
        for _, r in bad.iterrows():
            log(name, r.company_id, r.raw_year, "unparseable year", "CRITICAL", "rejected (DQ-07)")
        df = df[df.year != "PARSE_ERROR"].copy()
        df["partial_period"] = df.raw_year.str.contains(r"\d{4} \d+m?$")
        for _, r in df[df.partial_period].iterrows():
            log(name, r.company_id, r.raw_year, "non-12-month period label", "WARNING", "kept; closing month used")
        out[name] = df

    # ---- de-duplication (DQ-02) ----
    pl = out["profitandloss"]
    d = pl.duplicated(["company_id", "year"], keep="first")
    for _, r in pl[d].iterrows():
        log("profitandloss", r.company_id, r.year, "duplicate (company_id, year)", "CRITICAL", "dropped exact repeat")
    out["profitandloss"] = pl[~d].reset_index(drop=True)

    bs = out["balancesheet"]
    d = bs.duplicated(["company_id", "year"], keep="first")
    for _, r in bs[d].iterrows():
        log("balancesheet", r.company_id, r.year, "duplicate (company_id, year)", "CRITICAL", "dropped repeat")
    out["balancesheet"] = bs[~d].reset_index(drop=True)

    cf = out["cashflow"]
    # all-zero / all-null rows carry no information
    zero = cf[["operating_activity", "investing_activity", "financing_activity"]].fillna(0).abs().sum(axis=1) == 0
    for _, r in cf[zero].iterrows():
        log("cashflow", r.company_id, r.year, "all-zero/null cash flow row", "WARNING", "dropped")
    cf = cf[~zero]
    # duplicated keys with DIFFERENT values: second block is scale-inconsistent with the
    # company's own P&L (e.g. ABB FY15 CFI -1864 on sales 2289). Keep lowest-id block
    # (aligned with the P&L id sequence) and log it.
    cf = cf.sort_values("id")
    d = cf.duplicated(["company_id", "year"], keep="first")
    for _, r in cf[d].iterrows():
        log("cashflow", r.company_id, r.year, "duplicate key with conflicting values", "CRITICAL",
            "kept lowest-id row (matches P&L scale); later row dropped")
    cf = cf[~d]
    out["cashflow"] = cf.reset_index(drop=True)

    # half-year (Sep-2024) balance sheets have no matching annual P&L: interim, not annual
    pk = set(zip(out["profitandloss"].company_id, out["profitandloss"].year))
    bs = out["balancesheet"]
    interim = (bs.year == "2024-09") & ~pd.Series(list(zip(bs.company_id, bs.year)), index=bs.index).isin(pk)
    for _, r in bs[interim].iterrows():
        log("balancesheet", r.company_id, r.raw_year, "interim (half-year) balance sheet", "WARNING",
            "excluded from annual panel")
    out["balancesheet"] = bs[~interim].reset_index(drop=True)

    # sort chronological
    for k in ("profitandloss", "balancesheet", "cashflow"):
        out[k] = out[k].sort_values(["company_id", "year"]).reset_index(drop=True)

    out["dq_log"] = pd.DataFrame(dq)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    t = load_clean()
    for k, v in t.items():
        print(k, v.shape)
    t["dq_log"].to_csv(OUT / "validation_failures.csv", index=False)
    print(t["dq_log"].groupby(["table", "issue"]).size())
