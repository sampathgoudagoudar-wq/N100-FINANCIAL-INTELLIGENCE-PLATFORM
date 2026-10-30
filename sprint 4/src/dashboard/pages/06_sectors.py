import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import AMBER, TEAL, style_fig  # noqa: E402

st.title("Sector Analysis")
snap = db.get_snapshot()
val = db.get_valuation()[["company_id", "market_cap_crore"]]
df = snap.merge(val, on="company_id", how="left")
sectors = sorted(df["broad_sector"].dropna().unique())
sector = st.selectbox("Sector", ["All sectors"] + sectors)
sub = df if sector == "All sectors" else df[df["broad_sector"] == sector]
log_x = st.checkbox("Log scale for revenue", value=True)

plot = sub.dropna(subset=["sales", "roe", "market_cap_crore"])
plot = plot[plot["sales"] > 0]
missing = len(sub) - len(plot)
fig = px.scatter(plot, x="sales", y="roe", size="market_cap_crore", color="sub_sector", hover_name="company_name",
                 hover_data={"company_id": True, "market_cap_crore": ":,.0f", "sales": ":,.0f", "roe": ":.1f"},
                 size_max=45, log_x=log_x, labels={"sales": "Revenue (₹ Cr)", "roe": "ROE %", "sub_sector": "Sub-sector"})
fig.update_layout(title=f"{sector}: revenue vs ROE (bubble = market cap)")
st.plotly_chart(style_fig(fig, 480), width="stretch")
if missing:
    st.caption(f"{missing} companies omitted from the bubble chart (no ROE, revenue or market cap).")

kpis = {"ROE %": "roe", "ROCE %": "roce", "Net margin %": "npm", "Operating margin %": "opm",
        "Revenue CAGR 5y %": "rev_cagr_5y", "PAT CAGR 5y %": "pat_cagr_5y", "Dividend yield %": "div_yield"}
med_sel = sub[list(kpis.values())].median()
med_all = df[list(kpis.values())].median()
fig = go.Figure()
fig.add_bar(x=list(kpis), y=med_sel.values, name=f"{sector} median", marker_color=TEAL)
fig.add_bar(x=list(kpis), y=med_all.values, name="Nifty 100 median", marker_color=AMBER)
fig.update_layout(barmode="group", title="Median KPIs", yaxis_title="%")
st.plotly_chart(style_fig(fig, 380), width="stretch")
summary = (df.groupby("broad_sector").agg(companies=("company_id", "count"), median_roe=("roe", "median"),
           median_pe=("pe", "median"), median_npm=("npm", "median")).round(1).reset_index())
st.dataframe(summary.rename(columns={"broad_sector": "Sector"}), hide_index=True, width="stretch")
