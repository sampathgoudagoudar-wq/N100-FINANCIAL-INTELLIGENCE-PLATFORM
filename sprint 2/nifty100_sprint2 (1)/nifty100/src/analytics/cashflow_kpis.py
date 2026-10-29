"""Cash-flow KPIs and capital-allocation classifier (Sprint 2, Day 11)."""
from __future__ import annotations

from typing import Iterable, Optional, Tuple

from .ratios import num

HIGH_QUALITY, MODERATE, ACCRUAL_RISK = "High Quality", "Moderate", "Accrual Risk"
ASSET_LIGHT, CAPEX_MODERATE, CAPITAL_INTENSIVE = "Asset Light", "Moderate", "Capital Intensive"
MIN_CFO_QUALITY_YEARS = 3   # of the latest 5 fiscal years


def free_cash_flow(operating_activity, investing_activity) -> Optional[float]:
    """CFO + CFI. Negative values are allowed."""
    o, i = num(operating_activity), num(investing_activity)
    return None if o is None or i is None else o + i


def capex_proxy(investing_activity) -> Optional[float]:
    i = num(investing_activity)
    return None if i is None else abs(i)


def cfo_pat_ratio(cfo, pat) -> Optional[float]:
    """CFO / PAT for one year. None if PAT is 0, missing or negative (ratio not meaningful)."""
    c, p = num(cfo), num(pat)
    if c is None or p is None or p <= 0:
        return None
    return c / p


def cfo_quality_label(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score > 1.0:
        return HIGH_QUALITY
    if score >= 0.5:
        return MODERATE
    return ACCRUAL_RISK


def cfo_quality_score(pairs: Iterable[Tuple[object, object]],
                      min_years: int = MIN_CFO_QUALITY_YEARS) -> Tuple[Optional[float], Optional[str]]:
    """Average CFO/PAT over the supplied (cfo, pat) pairs (up to 5 years)."""
    vals = [r for r in (cfo_pat_ratio(c, p) for c, p in pairs) if r is not None]
    if len(vals) < min_years:
        return None, None
    score = sum(vals) / len(vals)
    return score, cfo_quality_label(score)


def capex_intensity(investing_activity, sales) -> Optional[float]:
    """abs(investing_activity) / sales x 100."""
    i, s = num(investing_activity), num(sales)
    if i is None or s is None or s <= 0:
        return None
    return abs(i) / s * 100


def capex_intensity_label(pct: Optional[float]) -> Optional[str]:
    if pct is None:
        return None
    if pct < 3:
        return ASSET_LIGHT
    if pct <= 8:
        return CAPEX_MODERATE
    return CAPITAL_INTENSIVE


def fcf_conversion(fcf, operating_profit) -> Optional[float]:
    """FCF / operating_profit x 100; None if operating_profit is 0 or missing."""
    f, o = num(fcf), num(operating_profit)
    if f is None or o is None or o == 0:
        return None
    return f / o * 100


def sign(x) -> Optional[str]:
    v = num(x)
    if v is None:
        return None
    return "+" if v > 0 else "-" if v < 0 else "0"


# The spec lists 8 labels but uses (+,-,-) twice and omits (-,+,-); the latter gets
# the label below (decision recorded in the Sprint 2 notes).
PATTERNS = {
    ("+", "-", "-"): "Reinvestor",
    ("+", "+", "-"): "Liquidating Assets",
    ("-", "+", "+"): "Distress Signal",
    ("-", "-", "+"): "Growth Funded by Debt",
    ("+", "+", "+"): "Cash Accumulator",
    ("-", "-", "-"): "Pre-Revenue",
    ("+", "-", "+"): "Mixed",
    ("-", "+", "-"): "Asset Sales Fund Outflows",
}
SHAREHOLDER_RETURNS = "Shareholder Returns"
UNDETERMINED = "Undetermined"
HIGH_CFO_PAT = 1.0


def capital_allocation_pattern(cfo, cfi, cff, cfo_pat: Optional[float] = None) -> str:
    """Classify a company-year by the signs of (CFO, CFI, CFF).

    (+,-,-) is Shareholder Returns when CFO/PAT > 1.0, otherwise Reinvestor.
    A zero or missing component gives 'Undetermined'.
    """
    key = (sign(cfo), sign(cfi), sign(cff))
    if None in key or "0" in key:
        return UNDETERMINED
    if key == ("+", "-", "-") and cfo_pat is not None and cfo_pat > HIGH_CFO_PAT:
        return SHAREHOLDER_RETURNS
    return PATTERNS[key]
