"""Parse growth-metric text fields in analysis.xlsx into a structured table."""
from __future__ import annotations

import logging
import re

import pandas as pd

from src.analytics.ratios import build_panel, company_cagrs
from src.etl.clean import OUT, RAW, normalize_ticker

logger = logging.getLogger(__name__)
FIELDS = ["compounded_sales_growth", "compounded_profit_growth", "stock_price_cagr", "roe"]
SPEC_PATTERN = re.compile(r"(\d+)\s*Years?:?\s*([\d.]+)%")          # mandated pattern
NEG_PATTERN = re.compile(r"(\d+)\s*Years?:?\s*(-\s*[\d.]+)%")       # negative values, e.g. '1 Year: -2%'
DIVERGENCE_PP = 5.0


def parse_text(text: object) -> tuple[int, float] | None:
    """Return (period_years, value_pct) or None if the text does not match."""
    s = str(text)
    m = SPEC_PATTERN.search(s)
    if m:
        return int(m.group(1)), float(m.group(2))
    m = NEG_PATTERN.search(s)
    if m:
        return int(m.group(1)), float(m.group(2).replace(" ", ""))
    return None


def run() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Write analysis_parsed.csv, parse_failures.csv and cross_validation.csv."""
    an = pd.read_excel(RAW / "analysis.xlsx", header=1)
    an["company_id"] = normalize_ticker(an["company_id"])
    valid = set(pd.read_excel(RAW / "companies.xlsx", header=1)["id"].str.strip().str.upper())
    parsed, fails = [], []
    for _, r in an.iterrows():
        for f in FIELDS:
            raw = r[f]
            res = parse_text(raw)
            if r.company_id not in valid:
                fails.append(dict(company_id=r.company_id, metric_type=f, raw_text=raw,
                                  reason="company not in companies master (orphan, DQ-03)"))
            elif res is None:
                reason = ("period label is not numeric ('TTM'/'Last Year') - no period_years"
                          if re.search(r"TTM|Last Year", str(raw)) else "no pattern match")
                fails.append(dict(company_id=r.company_id, metric_type=f, raw_text=raw, reason=reason))
            else:
                parsed.append(dict(company_id=r.company_id, metric_type=f, period_years=res[0], value_pct=res[1]))
    pr = pd.DataFrame(parsed, columns=["company_id", "metric_type", "period_years", "value_pct"])
    fl = pd.DataFrame(fails, columns=["company_id", "metric_type", "raw_text", "reason"])
    pr.to_csv(OUT / "analysis_parsed.csv", index=False)
    fl.to_csv(OUT / "parse_failures.csv", index=False)

    # ---- cross-validation vs Ratio Engine ----
    p = build_panel()
    rows = []
    for cid, g in p.groupby("company_id"):
        if cid not in set(pr.company_id):
            continue
        for metric, col in (("compounded_sales_growth", "sales"), ("compounded_profit_growth", "net_profit")):
            for _, r in pr[(pr.company_id == cid) & (pr.metric_type == metric)].iterrows():
                from src.analytics.ratios import cagr
                comp, flag = cagr(g[col], g["fy"], int(r.period_years))
                div = None if comp is None else abs(comp - r.value_pct)
                rows.append(dict(company_id=cid, metric_type=metric, period_years=r.period_years,
                                 parsed_pct=r.value_pct, computed_pct=None if comp is None else round(comp, 2),
                                 computed_flag=flag, divergence_pp=None if div is None else round(div, 2),
                                 review_flag="MANUAL REVIEW" if (div is not None and div > DIVERGENCE_PP)
                                 else ("NOT COMPARABLE" if comp is None else "OK")))
    cv = pd.DataFrame(rows)
    cv.to_csv(OUT / "cross_validation.csv", index=False)
    return pr, fl, cv


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pr, fl, cv = run()
    print("parsed", len(pr), "failures", len(fl)); print(fl.reason.value_counts())
    print(cv.review_flag.value_counts()); print(cv.to_string())
