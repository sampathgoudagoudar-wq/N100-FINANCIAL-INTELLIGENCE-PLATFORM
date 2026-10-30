"""Field normalisers used by the ETL pipeline (Sprint 1, Day 02)."""
from __future__ import annotations

import math
import re
from typing import Any, Optional

PARSE_ERROR = "PARSE_ERROR"
TTM = "TTM"          # trailing-twelve-months row: valid label, but not a fiscal year
MISSING = "MISSING"

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ISO = re.compile(r"^(\d{4})-(\d{2})$")
_FY = re.compile(r"^FY\s*[-']?\s*(\d{4}|\d{2})$", re.I)
# "Mar-23", "Mar 23", "March-2023", "Mar 2023", plus a trailing period tag such as
# "Mar 2016 9m" or "Mar 2023 15" (transition-period years) which is ignored.
_MON_YR = re.compile(r"^([A-Za-z]{3,9})\.?[\s\-/']*(\d{4}|\d{2})(?:\s+\S+)?$")
_YEAR_ONLY = re.compile(r"^\d{4}(\.0+)?$")

YEAR_FORMAT = re.compile(r"^\d{4}-\d{2}$")


def _full_year(y: str) -> int:
    n = int(y)
    if len(y) == 4:
        return n
    return 2000 + n if n <= 69 else 1900 + n


def _fmt(year: int, month: int) -> str:
    if not (1990 <= year <= 2100 and 1 <= month <= 12):
        return PARSE_ERROR
    return f"{year:04d}-{month:02d}"


def normalize_year(raw: Any) -> str:
    """Return 'YYYY-MM', 'TTM' for trailing-twelve-month rows, or 'PARSE_ERROR'."""
    if raw is None:
        return PARSE_ERROR
    if isinstance(raw, bool):
        return PARSE_ERROR
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and (math.isnan(raw) or raw != int(raw)):
            return PARSE_ERROR           # e.g. 2024.5 is not a year
        return _fmt(int(raw), 3)         # integer year -> assume March FY close
    s = str(raw).replace("\xa0", " ").strip()
    if not s:
        return PARSE_ERROR
    if s.upper() == "TTM":
        return TTM
    m = _ISO.match(s)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)))
    if _YEAR_ONLY.match(s):
        return _fmt(int(float(s)), 3)
    m = _FY.match(s)
    if m:
        return _fmt(_full_year(m.group(1)), 3)
    m = _MON_YR.match(s)
    if m:
        month = _MONTHS.get(m.group(1)[:3].lower())
        if month is None or (len(m.group(1)) > 3 and
                             not _full_month(m.group(1))):
            return PARSE_ERROR
        return _fmt(_full_year(m.group(2)), month)
    return PARSE_ERROR


_FULL = {"january", "february", "march", "april", "may", "june", "july",
         "august", "september", "sept", "october", "november", "december"}


def _full_month(word: str) -> bool:
    return word.lower() in _FULL


# Known source typos -> canonical NSE ticker (found in Day 06 manual review).
TICKER_ALIASES = {"AGTL": "ATGL"}   # Adani Total Gas: 7 cash-flow rows were keyed AGTL


def normalize_ticker(raw: Any) -> str:
    """Strip + upper-case an NSE ticker. Hyphens and ampersands are preserved.

    Returns 'MISSING' for null/blank input.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return MISSING
    s = str(raw).replace("\xa0", " ").strip().upper()
    return s if s else MISSING


def is_valid_ticker(t: str) -> bool:
    return t != MISSING and 2 <= len(t) <= 12




def parse_growth_text(raw: Any) -> tuple[Optional[str], Optional[float]]:
    """Parse strings such as '10 Years:     15%' -> ('10Y', 15.0).

    Returns (None, None) when the cell is empty or unparseable.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None, None
    s = str(raw).strip()
    m = re.match(r"^\s*(\d+)\s*Years?\s*:?\s*(-?\d+(?:\.\d+)?)\s*%\s*$", s, re.I)
    if m:
        return f"{int(m.group(1))}Y", float(m.group(2))
    m = re.match(r"^\s*(TTM|Last\s+Year|1\s+Year)\s*:?\s*(-?\d+(?:\.\d+)?)\s*%\s*$", s, re.I)
    if m:
        tag = re.sub(r"\s+", " ", m.group(1)).upper()
        return {"TTM": "TTM", "LAST YEAR": "LY", "1 YEAR": "1Y"}[tag], float(m.group(2))
    return None, None
