"""Sprint 4 batch step: rebuild the SQLite store and the valuation outputs."""
import sqlite3
from pathlib import Path

import pandas as pd

from src.analytics.valuation import write_valuation_outputs
from src.data.build_db import DB_PATH, build

ROOT = Path(__file__).parent


def export_tracker_csvs() -> None:
    """D-02 load_audit, D-03 validation_failures, D-06 capital_allocation, D-14 pros_cons_generated."""
    from src.analytics.proscons import generate
    from src.data.loader import load_clean
    from src.dq.rules import run_all
    t, log = load_clean()
    out = ROOT / "output"
    log.to_csv(out / "load_audit.csv", index=False)
    run_all(t).query("violations > 0").to_csv(out / "validation_failures.csv", index=False)
    with sqlite3.connect(DB_PATH) as con:
        pd.read_sql_query("SELECT * FROM capital_allocation", con).to_csv(out / "capital_allocation.csv", index=False)
        snap = pd.read_sql_query("SELECT * FROM kpi_snapshot WHERE snapshot_year = 2024", con)
        panel = pd.read_sql_query("SELECT * FROM financial_ratios", con)
    rows = []
    for _, r in snap.iterrows():
        pros, cons = generate(r, panel[panel.company_id == r["company_id"]])
        rows += [{"company_id": r["company_id"], "type": "pro", "text": x} for x in pros]
        rows += [{"company_id": r["company_id"], "type": "con", "text": x} for x in cons]
    pd.DataFrame(rows).to_csv(out / "pros_cons_generated.csv", index=False)

if __name__ == "__main__":
    print(build())
    with sqlite3.connect(DB_PATH) as con:
        val = pd.read_sql_query("SELECT * FROM valuation", con)
    write_valuation_outputs(val, ROOT / "output/valuation_summary.xlsx", ROOT / "output/valuation_flags.csv")
    print(val["flag"].value_counts().to_dict())
    export_tracker_csvs()
