"""Profitability, leverage and efficiency ratios (Sprint 2, Days 08-09).

Every function takes plain numbers (None / NaN allowed) and returns a float or
None. None always means "not computable"; it is never silently replaced by 0,
with one documented exception: debt-to-equity is 0 for debt-free companies.
"""
from __future__ import annotations

import math
from typing import Optional

Num = Optional[float]
OPM_TOLERANCE_PP = 1.0
HIGH_DE_THRESHOLD = 5.0
ICR_WARNING_THRESHOLD = 1.5
DEBT_FREE_LABEL = "Debt Free"


def num(x) -> Num:
    """Coerce to float; None for None/NaN/unparseable."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _ratio(n, d, scale: float = 1.0) -> Num:
    n, d = num(n), num(d)
    if n is None or d is None or d == 0:
        return None
    return n / d * scale


def total_equity(equity_capital, reserves) -> Num:
    e, r = num(equity_capital), num(reserves)
    if e is None and r is None:
        return None
    return (e or 0.0) + (r or 0.0)


# ------------------------------------------------------------ profitability
def net_profit_margin(net_profit, sales) -> Num:
    """net_profit / sales x 100; None if sales = 0."""
    return _ratio(net_profit, sales, 100)


def operating_profit_margin(operating_profit, sales) -> Num:
    return _ratio(operating_profit, sales, 100)


def opm_mismatch(source_opm, computed_opm, tol: float = OPM_TOLERANCE_PP) -> bool:
    """True when the source opm_percentage differs from the computed one by more than tol pp."""
    s, c = num(source_opm), num(computed_opm)
    return s is not None and c is not None and abs(s - c) > tol


def return_on_equity(net_profit, equity_capital, reserves) -> Num:
    """net_profit / (equity_capital + reserves) x 100; None if equity+reserves <= 0."""
    eq = total_equity(equity_capital, reserves)
    if eq is None or eq <= 0:
        return None
    return _ratio(net_profit, eq, 100)


def ebit(operating_profit, depreciation) -> Num:
    """EBIT = operating_profit - depreciation (project spec, section 5.2)."""
    op, dep = num(operating_profit), num(depreciation)
    if op is None or dep is None:
        return None
    return op - dep


def return_on_capital_employed(operating_profit, depreciation, equity_capital, reserves, borrowings) -> Num:
    """EBIT / (equity + reserves + borrowings) x 100; None if capital employed <= 0."""
    eq, b, e = total_equity(equity_capital, reserves), num(borrowings), ebit(operating_profit, depreciation)
    if eq is None or e is None:
        return None
    cap = eq + (b or 0.0)
    if cap <= 0:
        return None
    return e / cap * 100


def return_on_assets(net_profit, total_assets) -> Num:
    return _ratio(net_profit, total_assets, 100)


# ----------------------------------------------------------------- leverage
def debt_to_equity(borrowings, equity_capital, reserves) -> Num:
    """borrowings / (equity + reserves). Returns 0.0 (not None) for debt-free companies."""
    b = num(borrowings)
    if b is None:
        return None
    if b == 0:
        return 0.0
    eq = total_equity(equity_capital, reserves)
    if eq is None or eq <= 0:
        return None
    return b / eq


def high_leverage_flag(de: Num, is_financial: bool) -> bool:
    """D/E > 5 for non-Financials. Suppressed for Financials (structural leverage)."""
    return bool(de is not None and de > HIGH_DE_THRESHOLD and not is_financial)


def interest_coverage(operating_profit, other_income, interest) -> Num:
    """(operating_profit + other_income) / interest; None when interest is 0 or missing."""
    op, oi, i = num(operating_profit), num(other_income), num(interest)
    if op is None or i is None or i == 0:
        return None
    return (op + (oi or 0.0)) / i


def icr_label(interest) -> Optional[str]:
    """'Debt Free' when interest is exactly 0 (ICR is undefined)."""
    i = num(interest)
    return DEBT_FREE_LABEL if i == 0 else None


def icr_warning_flag(icr: Num) -> bool:
    """ICR < 1.5: at risk of not covering interest payments."""
    return bool(icr is not None and icr < ICR_WARNING_THRESHOLD)


def net_debt(borrowings, investments) -> Num:
    """borrowings - investments (investments used as liquid-asset proxy)."""
    b, i = num(borrowings), num(investments)
    if b is None:
        return None
    return b - (i or 0.0)


# --------------------------------------------------------------- efficiency
def asset_turnover(sales, total_assets) -> Num:
    return _ratio(sales, total_assets)


def book_value_per_share(equity_capital, reserves, face_value) -> Num:
    """(equity + reserves) / (equity_capital / face_value)."""
    eq, ec, fv = total_equity(equity_capital, reserves), num(equity_capital), num(face_value)
    if eq is None or ec is None or fv is None or ec == 0 or fv == 0:
        return None
    return eq / (ec / fv)
