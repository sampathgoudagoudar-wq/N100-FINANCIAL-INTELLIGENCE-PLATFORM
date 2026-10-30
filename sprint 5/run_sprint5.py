"""Run the full Sprint 5 pipeline end to end (ETL -> ratios -> NLP -> cash flow -> PDFs -> verification)."""
from __future__ import annotations

import logging

import pandas as pd

from src.analytics import cashflow_kpis, ratios
from src.nlp import parser, pros_cons_generator
from src.reports import portfolio_report, qa, sector_report, tearsheet
from src.etl.clean import OUT, ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def verify() -> pd.DataFrame:
    """Check every Sprint 5 exit criterion and return a pass/fail table."""
    cos = pd.read_excel(ROOT / "data/raw/companies.xlsx", header=1).id.str.strip().str.upper().tolist()
    pc = pd.read_csv(OUT / "pros_cons_generated.csv")
    cfi = pd.read_excel(OUT / "cashflow_intelligence.xlsx", sheet_name="Cashflow Intelligence")
    skipped = pd.read_csv(OUT / "skipped_tearsheets.csv")
    ts = sorted((ROOT / "reports/tearsheets").glob("*_tearsheet.pdf"))
    tqa = pd.read_csv(OUT / "tearsheet_qa.csv")
    required = ["company_id", "sector", "cfo_quality_score", "cfo_quality_label", "capex_intensity_pct", "capex_label",
                "fcf_cagr_5yr", "fcf_conversion_pct", "distress_flag", "deleveraging_flag", "capital_allocation_label"]
    rows = [
        ("pros_cons: >=1 pro and >=1 con for every company", not pros_cons_generator.verify(pc, cos)),
        ("pros_cons: all confidences > 60", bool((pc.confidence_pct > 60).all())),
        ("pros_cons columns", list(pc.columns) == ["company_id", "type", "rule_id", "text", "confidence_pct"]),
        ("cashflow_intelligence.xlsx has 92 rows", len(cfi) == 92),
        ("cashflow_intelligence.xlsx has all required columns", all(c in cfi.columns for c in required)),
        (f"tearsheets = 92 - skipped ({len(skipped)})", len(ts) == 92 - len(skipped)),
        ("every tearsheet >= 30 KB", all(p.stat().st_size >= 30 * 1024 for p in ts)),
        ("every tearsheet exactly 2 pages, no blank, no overflow (automated)", bool(tqa.ok.all())),
        ("sector PDFs generated (one per broad sector)", len(list((ROOT / "reports/sector").glob("*.pdf"))) == 10),
        ("portfolio summary PDF has 92 pages", True),
    ]
    from pypdf import PdfReader
    pf = next((ROOT / "reports/portfolio").glob("*.pdf"))
    rows[-1] = (rows[-1][0], len(PdfReader(pf).pages) == 92)
    return pd.DataFrame(rows, columns=["check", "passed"])


if __name__ == "__main__":
    ratios.run()
    parser.run()
    pros_cons_generator.run()
    cashflow_kpis.run()
    tearsheet.run()
    sector_report.run()
    portfolio_report.run()
    import sys
    sys.argv = ["qa"]
    from pathlib import Path
    df = pd.DataFrame([qa.check_tearsheet(p) for p in sorted((ROOT / "reports/tearsheets").glob("*_tearsheet.pdf"))])
    df.to_csv(OUT / "tearsheet_qa.csv", index=False)
    v = verify()
    v.to_csv(OUT / "sprint5_verification.csv", index=False)
    print(v.to_string(index=False))
