"""Run every statement in notebooks/exploratory_queries.sql and print row counts / head."""
import sqlite3
import sys
import pandas as pd
from .loader import ROOT

def main():
    sql = (ROOT / "notebooks" / "exploratory_queries.sql").read_text()
    con = sqlite3.connect(ROOT / "data" / "nifty100.db")
    stmts = [s.strip() for s in sql.split(";") if "SELECT" in s]
    for i, s in enumerate(stmts, 1):
        df = pd.read_sql(s, con)
        print(f"--- Q{i:02d}: {len(df)} rows"); print(df.head(4).to_string(index=False))
    return len(stmts)

if __name__ == "__main__":
    sys.exit(0 if main() == 10 else 1)
