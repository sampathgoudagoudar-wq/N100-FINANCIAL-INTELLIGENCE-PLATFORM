import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import fmt, sim_note, style_fig, tiles  # noqa: E402

st.title("Nifty 100 Analytics")
year = st.sidebar.selectbox("Fiscal year", list(range(2024, 2018, -1)), index=0,
                            help="All metrics on this page are as of the selected fiscal year.")
snap = db.get_snapshot(year)
non_fin = snap[snap["broad_sector"] != "Financials"]

debt_free = int((non_fin["de"] <= 0.05).sum())
tiles([
    ("Average ROE", fmt(snap["roe"].mean(), 1, suffix="%"), "Mean of company ROE (%)"),
    ("Median P/E (SIMULATED)", fmt(snap["pe"].median(), 1, suffix="x"), None),
    ("Median D/E", fmt(non_fin["de"].median(), 2), "Excludes Financials, where D/E is not meaningful"),
    ("Total Companies", f"{len(snap)}", None),
    ("Median Revenue CAGR 5yr", fmt(snap["rev_cagr_5y"].median(), 1, suffix="%"), None),
    ("Debt-Free Companies", f"{debt_free}", "Non-financials with D/E ≤ 0.05"),
])
st.caption(f"FY{year} · valuation multiples from the {year} market snapshot · {snap['roe'].isna().sum()} companies without ROE are excluded from the average.")

sim_note()
left, right = st.columns([1, 1])
with left:
    st.subheader("Companies by sector")
    sec = snap.groupby("broad_sector").size().reset_index(name="companies").sort_values("companies", ascending=False)
    fig = px.pie(sec, names="broad_sector", values="companies", hole=0.55)
    fig.update_traces(textinfo="value", hovertemplate="%{label}: %{value} companies<extra></extra>")
    st.plotly_chart(style_fig(fig, 400), width="stretch")
    st.caption(f"{len(sec)} broad sectors exist in sectors.xlsx (the project brief mentions 11).")
with right:
    st.subheader("Top 5 by composite quality score")
    top = snap.sort_values("composite_quality_score", ascending=False).head(5)
    view = top[["company_id", "company_name", "broad_sector", "composite_quality_score", "roe"]].copy()
    view.columns = ["Ticker", "Company", "Sector", "Quality score", "ROE %"]
    st.dataframe(view.round(1), hide_index=True, width="stretch")
    st.caption("Score 0–100: profitability 35 · cash quality 30 · growth 20 · leverage 15.")
