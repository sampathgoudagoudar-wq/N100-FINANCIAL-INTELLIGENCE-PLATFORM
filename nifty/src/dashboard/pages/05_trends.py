import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import PALETTE, company_picker, style_fig, years_note  # noqa: E402

METRICS = {"Revenue (₹ Cr)": "sales", "Net profit (₹ Cr)": "net_profit", "EPS (₹)": "eps", "ROE %": "roe",
           "ROCE %": "roce", "Net margin %": "npm", "Operating margin %": "opm", "D/E": "de",
           "Free cash flow (₹ Cr)": "fcf", "Asset turnover": "asset_turnover"}


def yoy(s):
    prev = s.shift(1)
    return ((s / prev.where(prev > 0)) - 1) * 100       # undefined when the base is <= 0


st.title("Trend Analysis")
ticker = company_picker("trend")
if ticker is None:
    st.stop()
chosen = st.multiselect("Metrics (overlay up to 3)", list(METRICS), default=["Revenue (₹ Cr)"], max_selections=3)
df = db.get_ratios(ticker).tail(10)
years_note(len(df))
if not chosen:
    st.info("Pick at least one metric.")
    st.stop()

fig = go.Figure()
layout = {"xaxis": dict(domain=[0.0, 0.88 if len(chosen) > 2 else 0.95], dtick=1, title="Fiscal year")}
for i, name in enumerate(chosen):
    col = METRICS[name]
    s = df[col].astype(float)
    g = yoy(s)
    txt = [("" if np.isnan(v) else f"{v:+.1f}%") for v in g]
    ax = "y" if i == 0 else f"y{i + 1}"
    fig.add_trace(go.Scatter(x=df["year"], y=s, name=name, mode="lines+markers+text", text=txt,
                             textposition="top center", textfont=dict(size=10, color=PALETTE[i]),
                             line=dict(color=PALETTE[i]), yaxis=ax, connectgaps=False,
                             hovertemplate=name + ": %{y:,.2f}<br>YoY: %{text}<extra></extra>"))
    key = "yaxis" if i == 0 else f"yaxis{i + 1}"
    layout[key] = dict(title=dict(text=name, font=dict(color=PALETTE[i])), tickfont=dict(color=PALETTE[i]),
                       showgrid=(i == 0))
    if i == 1:
        layout[key].update(overlaying="y", side="right")
    if i == 2:
        layout[key].update(overlaying="y", side="right", anchor="free", position=0.97)
fig.update_layout(**layout, title=f"{ticker}: {', '.join(chosen)}  (labels = YoY % change)")
st.plotly_chart(style_fig(fig, 500), width="stretch")
st.caption("YoY % is shown as blank where the previous year is missing, zero or negative. Each metric has its own axis.")
