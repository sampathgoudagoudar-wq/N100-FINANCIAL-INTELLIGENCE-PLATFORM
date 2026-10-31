"""Shared UI helpers for the dashboard pages."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:            # lets pages import `src.*` when run by streamlit directly
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard.utils import db  # noqa: E402

NA = "N/A"
NAVY, TEAL, AMBER = "#0B2239", "#0F7B6C", "#D9822B"
PALETTE = ["#0F7B6C", "#D9822B", "#2F5D9B", "#B5445A", "#7A6BB5", "#6B8E23", "#C9A227", "#3A8FB7", "#8C5A3C", "#5F6B73"]


def is_na(v) -> bool:
    return v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)) or v is pd.NA


def fmt(v, nd: int = 1, prefix: str = "", suffix: str = "") -> str:
    """Format a number, returning 'N/A' for None/NaN; +inf -> 'Debt Free'."""
    if is_na(v):
        return NA
    if isinstance(v, (float, np.floating)) and np.isinf(v):
        return "Debt Free"
    try:
        return f"{prefix}{float(v):,.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def style_fig(fig, height: int = 420):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), autosize=True,
                      font=dict(size=13), legend=dict(orientation="h", y=-0.15),
                      colorway=PALETTE, template="plotly_white")
    return fig


def company_picker(key: str, label: str = "Search company name or ticker") -> str | None:
    """Text search + autocomplete dropdown. Returns a valid ticker or None."""
    comp = db.get_companies()
    q = st.text_input(label, key=f"{key}_q", placeholder="e.g. TCS, Infosys, HDFC …").strip()
    if q:
        m = comp[comp["company_id"].str.contains(q, case=False, regex=False)
                 | comp["company_name"].str.contains(q, case=False, regex=False)]
    else:
        m = comp
    if m.empty:
        st.warning("Ticker not found — please try another")
        return None
    ids = m["company_id"].tolist()
    names = dict(zip(comp["company_id"], comp["company_name"]))
    default = st.session_state.get("ticker")
    idx = ids.index(default) if default in ids else 0
    pick = st.selectbox("Matching companies", ids, index=idx, key=f"{key}_sel",
                        format_func=lambda t: f"{t} — {names[t]}")
    st.session_state["ticker"] = pick
    return pick


def tiles(items: list[tuple[str, str, str | None]]):
    cols = st.columns(len(items))
    for col, (label, value, help_) in zip(cols, items):
        col.metric(label, value, help=help_)


SIM_NOTE = "⚠️ **SIMULATED** — market cap, P/E, P/B, EV/EBITDA and dividend yield come from the simulated market_cap dataset."


def sim_note():
    st.caption(SIM_NOTE)


def years_note(n_years: int, expected: int = 10):
    if n_years < expected:
        st.info(f"Data available for {n_years} year{'s' if n_years != 1 else ''} only (less than {expected}).")
