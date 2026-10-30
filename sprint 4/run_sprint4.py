"""Sprint 4 batch step: rebuild the SQLite store and the valuation outputs."""
import sqlite3
from pathlib import Path

import pandas as pd

from src.analytics.valuation import write_valuation_outputs
from src.data.build_db import DB_PATH, build

ROOT = Path(__file__).parent

if __name__ == "__main__":
    print(build())
    with sqlite3.connect(DB_PATH) as con:
        val = pd.read_sql_query("SELECT * FROM valuation", con)
    write_valuation_outputs(val, ROOT / "output/valuation_summary.xlsx", ROOT / "output/valuation_flags.csv")
    print(val["flag"].value_counts().to_dict())
