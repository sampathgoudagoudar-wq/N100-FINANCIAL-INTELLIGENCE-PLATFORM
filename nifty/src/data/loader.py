"""Load and clean the raw Nifty 100 Excel files (the ETL steps Sprint 3 depends on).

Cleaning rules (mirrors DQ-02/03/07/08/10 of the project document):
  * tickers: strip + upper-case                                  (DQ-08)
  * year labels -> integer fiscal-year-end calendar year         (DQ-07)
      'Mar 2024' / 'Mar-24' / '2024'  -> 2024
      'TTM', '2024.5', '... 9m', '... 15' (non-12-month periods) -> dropped
      balance-sheet 'Sep 2024' half-year snapshots -> dropped when the company
      reports a Mar/Jun/Dec year-end
  * orphan tickers (not in companies.xlsx) rejected              (DQ-03)
  * duplicate (company_id, year) keep last                       (DQ-02)
  * negative fixed_assets coerced to 0                           (DQ-10)
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path("/mnt/user-data/attachments/e33744ea-470c-59d1-b695-14656315ae27")

_FILES = {
    "companies": ("companies_1.xlsx", 1),
    "profitandloss": ("profitandloss_1.xlsx", 1),
    "balancesheet": ("balancesheet_1.xlsx", 1),
    "cashflow": ("cashflow_1.xlsx", 1),
    "sectors": ("sectors_1.xlsx", 0),
    "market_cap": ("market_cap_1.xlsx", 0),
    "peer_groups": ("peer_groups_1.xlsx", 0),
    "financial_ratios": ("financial_ratios_1.xlsx", 0),
    "documents": ("documents_1.xlsx", 1),
    "prosandcons": ("prosandcons_1.xlsx", 1),
}

_MONTHS = ("Mar", "Jun", "Sep", "Dec")


def _find(name: str, data_dir: Path) -> Path:
    hits = sorted(data_dir.glob(f"*{name}"))
    if not hits:
        raise FileNotFoundError(f"{name} not found in {data_dir}")
    return hits[0]


def read_raw(table: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Read one raw file. Core files carry a metadata row, so header=1."""
    fname, header = _FILES[table]
    df = pd.read_excel(_find(fname, data_dir), header=header)
    if "id" in df.columns and table == "companies":
        df["id"] = df["id"].astype(str)
    return df


def normalize_ticker(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


_RE_MON_YEAR = re.compile(r"^(Mar|Jun|Sep|Dec)[ -](\d{4}|\d{2})$", re.I)
_RE_BARE_YEAR = re.compile(r"^(\d{4})$")


def normalize_year(label) -> tuple[int | None, str | None]:
    """Return (fiscal_year, month_tag) for an annual period, else (None, None)."""
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None, None
    text = str(label).strip()
    if text.upper() == "TTM":
        return None, None
    m = _RE_MON_YEAR.match(text)
    if m:
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
        return year, m.group(1).title()
    m = _RE_BARE_YEAR.match(text)
    if m:
        return int(m.group(1)), None
    return None, None  # 9m / 15-month / x.5 interim periods


def _clean_time_series(df: pd.DataFrame, valid_ids: set[str], table: str,
                       log: list[dict]) -> pd.DataFrame:
    df = df.copy()
    df["company_id"] = normalize_ticker(df["company_id"])
    n0 = len(df)

    orphan = ~df["company_id"].isin(valid_ids)
    log.append({"table": table, "rule": "DQ-03 orphan tickers rejected",
                "rows": int(orphan.sum()),
                "detail": ", ".join(sorted(df.loc[orphan, "company_id"].unique()))})
    df = df[~orphan]

    parsed = df["year"].apply(normalize_year)
    df["fy"] = [p[0] for p in parsed]
    df["_mon"] = [p[1] for p in parsed]
    bad = df["fy"].isna()
    log.append({"table": table, "rule": "DQ-07 non-annual / unparseable period dropped",
                "rows": int(bad.sum()),
                "detail": ", ".join(sorted(df.loc[bad, "year"].astype(str).unique())[:12])})
    df = df[~bad]

    if table == "balancesheet":
        # Sep-2024 half-year snapshots sit next to annual Mar rows
        has_annual = (df[df["_mon"].isin(["Mar", "Jun", "Dec"])]
                      .groupby("company_id").size().rename("n_ann"))
        df = df.join(has_annual, on="company_id")
        interim = (df["_mon"] == "Sep") & df["n_ann"].notna()
        log.append({"table": table, "rule": "interim Sep balance sheet dropped",
                    "rows": int(interim.sum()), "detail": ""})
        df = df[~interim].drop(columns="n_ann")

    df["year"] = df["fy"].astype(int)
    dup = df.duplicated(["company_id", "year"], keep="last")
    log.append({"table": table, "rule": "DQ-02 duplicate (company, year) removed",
                "rows": int(dup.sum()), "detail": ""})
    df = df[~dup].drop(columns=["fy", "_mon"])
    return df.sort_values(["company_id", "year"]).reset_index(drop=True)


def load_clean(data_dir: Path = DATA_DIR) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return (cleaned tables, cleaning log)."""
    log: list[dict] = []
    t: dict[str, pd.DataFrame] = {}

    co = read_raw("companies", data_dir)
    co["id"] = normalize_ticker(co["id"])
    co["company_name"] = (co["company_name"].astype(str).str.split("\n").str[0].str.strip())
    t["companies"] = co
    valid = set(co["id"])

    for tbl in ("profitandloss", "balancesheet", "cashflow"):
        t[tbl] = _clean_time_series(read_raw(tbl, data_dir), valid, tbl, log)
    fa = t["balancesheet"]["fixed_assets"]
    neg = fa < 0
    if neg.any():
        t["balancesheet"].loc[neg, "fixed_assets"] = 0
    log.append({"table": "balancesheet", "rule": "DQ-10 negative fixed_assets -> 0",
                "rows": int(neg.sum()), "detail": ""})

    # Cross-company duplicate series: ABB's cash flow is a verbatim copy of ADANIENSOL's (CFO > ABB's
    # whole revenue).  When two tickers share an identical CFO/CFI/CFF triple in >= 5 years, the
    # series is dropped for the ticker where it is least plausible (largest CFO relative to sales).
    cf = t["cashflow"]
    sig = cf.groupby(["year", "operating_activity", "investing_activity", "financing_activity"])["company_id"].apply(list)
    pair_hits: dict[tuple, int] = {}
    for ids in sig[sig.apply(len) > 1]:
        if len(ids) == 2 and cf.loc[cf.company_id.isin(ids), "operating_activity"].abs().sum() > 0:
            pair_hits[tuple(sorted(ids))] = pair_hits.get(tuple(sorted(ids)), 0) + 1
    sales = t["profitandloss"].groupby("company_id")["sales"].median()
    cfo = cf.groupby("company_id")["operating_activity"].apply(lambda s: s.abs().median())
    for pair, n in pair_hits.items():
        if n >= 5:
            drop = max(pair, key=lambda c: cfo.get(c, 0) / max(sales.get(c, 1), 1))
            t["cashflow"] = t["cashflow"][t["cashflow"]["company_id"] != drop]
            log.append({"table": "cashflow", "rule": "cross-company duplicate series dropped",
                        "rows": int(n), "detail": f"{drop} duplicates {[c for c in pair if c != drop][0]}"})

    for tbl in ("sectors", "market_cap", "peer_groups"):
        d = read_raw(tbl, data_dir)
        d["company_id"] = normalize_ticker(d["company_id"])
        t[tbl] = d[d["company_id"].isin(valid)].reset_index(drop=True)
    t["peer_groups"]["is_benchmark"] = t["peer_groups"]["is_benchmark"].astype(bool)
    return t, pd.DataFrame(log)
