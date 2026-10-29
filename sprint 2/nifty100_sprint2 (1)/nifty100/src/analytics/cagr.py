"""CAGR engine with the six edge cases (Sprint 2, Day 10)."""
from __future__ import annotations

from typing import Mapping, Optional, Tuple

from .ratios import num

OK = "OK"
DECLINE_TO_LOSS = "DECLINE_TO_LOSS"   # positive start, negative end
TURNAROUND = "TURNAROUND"             # negative start, positive end
BOTH_NEGATIVE = "BOTH_NEGATIVE"
ZERO_BASE = "ZERO_BASE"
INSUFFICIENT = "INSUFFICIENT"
FLAGS = (OK, DECLINE_TO_LOSS, TURNAROUND, BOTH_NEGATIVE, ZERO_BASE, INSUFFICIENT)


def cagr(start, end, n: int) -> Tuple[Optional[float], str]:
    """((end/start)^(1/n) - 1) x 100 with a flag explaining any None."""
    s, e = num(start), num(end)
    if n <= 0 or s is None or e is None:
        return None, INSUFFICIENT
    if s == 0:
        return None, ZERO_BASE
    if s > 0 and e < 0:
        return None, DECLINE_TO_LOSS
    if s < 0 and e > 0:
        return None, TURNAROUND
    if s < 0 and e <= 0:
        return None, BOTH_NEGATIVE
    # s > 0 and e >= 0 (e == 0 gives -100%, a genuine total decline)
    return ((e / s) ** (1.0 / n) - 1) * 100, OK


def shift_year(year: str, n: int) -> str:
    """'2024-03', 5 -> '2019-03' (n fiscal years earlier, same year-end month)."""
    y, m = year.split("-")
    return f"{int(y) - n:04d}-{m}"


def window_cagr(series: Mapping[str, float], year: str, n: int) -> Tuple[Optional[float], str]:
    """CAGR over the n fiscal years ending at `year`.

    `series` maps 'YYYY-MM' -> value for one company. A missing start-year is INSUFFICIENT.
    """
    end = series.get(year)
    start = series.get(shift_year(year, n))
    return cagr(start, end, n)
