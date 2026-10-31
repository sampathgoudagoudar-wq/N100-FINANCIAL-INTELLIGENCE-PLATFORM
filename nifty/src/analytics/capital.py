"""Capital-allocation pattern from the sign of CFO / CFI / CFF (8 patterns)."""
import numpy as np
import pandas as pd

PATTERNS = {
    ("+", "-", "-"): "Self-funded Reinvestor",       # ops fund capex and debt paydown / payouts
    ("+", "-", "+"): "Leveraged Expander",           # ops + outside capital fund heavy investment
    ("+", "+", "-"): "Harvester",                    # ops + asset sales return cash / repay debt
    ("+", "+", "+"): "Cash Accumulator",
    ("-", "-", "+"): "Externally Funded Builder",
    ("-", "+", "+"): "Distress Funding",
    ("-", "+", "-"): "Asset Liquidator",
    ("-", "-", "-"): "Cash Depletion",
}


def classify(cfo, cfi, cff):
    if any(pd.isna(v) for v in (cfo, cfi, cff)):
        return None
    sg = lambda v: "+" if v >= 0 else "-"  # noqa: E731
    return PATTERNS[(sg(cfo), sg(cfi), sg(cff))]


def capital_allocation(cf: pd.DataFrame) -> pd.DataFrame:
    """Latest-year pattern per company (company_id, year, cfo, cfi, cff, pattern)."""
    last = cf.sort_values("year").groupby("company_id").tail(1)
    out = last[["company_id", "year", "operating_activity", "investing_activity", "financing_activity"]].copy()
    out.columns = ["company_id", "year", "cfo", "cfi", "cff"]
    out["pattern"] = [classify(*r) for r in out[["cfo", "cfi", "cff"]].itertuples(index=False)]
    return out.reset_index(drop=True)
