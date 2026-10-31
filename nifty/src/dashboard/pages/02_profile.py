import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import AMBER, NAVY, TEAL, company_picker, fmt, style_fig, tiles, years_note  # noqa: E402

st.title("Company Profile")
ticker = company_picker("profile")
if ticker is None:
    st.stop()

comp = db.get_companies().set_index("company_id").loc[ticker]
snap = db.get_snapshot()
row = snap[snap["company_id"] == ticker].iloc[0]
ratios = db.get_ratios(ticker).tail(10)

with st.container(border=True):
    st.subheader(comp["company_name"])
    st.markdown(f"**Sector:** {comp['broad_sector']} · **Sub-sector:** {comp['sub_sector']} · "
                f"**NSE ticker:** `{ticker}` · **Cap class:** {comp['market_cap_category']}")
    if comp["about_company"]:
        st.write(comp["about_company"])

tiles([
    ("ROE", fmt(row["roe"], 1, suffix="%"), None),
    ("ROCE", fmt(row["roce"], 1, suffix="%"), None),
    ("Net profit margin", fmt(row["npm"], 1, suffix="%"), None),
    ("Debt / Equity", fmt(row["de"], 2), "Not meaningful for banks / NBFCs / insurers" if row["broad_sector"] == "Financials" else None),
    ("Revenue CAGR 5yr", "TURNAROUND" if row.get("rev_cagr_5y_flag") == "Turnaround" else fmt(row["rev_cagr_5y"], 1, suffix="%"), "TURNAROUND = base year or end value not positive, CAGR not calculated"),
    (f"FCF FY{int(row['fy']) if row['fy'] == row['fy'] else 'N/A'} (₹ Cr)", fmt(row["fcf"], 0), None),
])
years_note(len(ratios))

c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    fig.add_bar(x=ratios["year"], y=ratios["sales"], name="Revenue", marker_color=TEAL)
    fig.add_bar(x=ratios["year"], y=ratios["net_profit"], name="Net profit", marker_color=AMBER)
    fig.update_layout(barmode="group", title="Revenue & net profit (₹ Cr)", xaxis=dict(dtick=1))
    st.plotly_chart(style_fig(fig), width="stretch")
with c2:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=ratios["year"], y=ratios["roe"], name="ROE %", mode="lines+markers", line=dict(color=NAVY), secondary_y=False)
    fig.add_scatter(x=ratios["year"], y=ratios["roce"], name="ROCE %", mode="lines+markers", line=dict(color=AMBER), secondary_y=True)
    fig.update_yaxes(title_text="ROE %", secondary_y=False)
    fig.update_yaxes(title_text="ROCE %", secondary_y=True, showgrid=False)
    fig.update_layout(title="ROE & ROCE", xaxis=dict(dtick=1))
    st.plotly_chart(style_fig(fig), width="stretch")
    if ratios["roe"].isna().all():
        st.caption("ROE/ROCE history is N/A: this company's balance sheet is on a different scale from its P&L (see sprint notes).")

st.subheader("Pros & cons")
pc = db.get_proscons(ticker)
p, c = st.columns(2)
badge = ("<div style='padding:6px 10px;margin:4px 0;border-radius:8px;background:{bg};color:{fg};"
         "border:1px solid {fg}33'>{icon} {txt}</div>")
with p:
    for t in pc["pros"] or []:
        st.markdown(badge.format(bg="#E6F4EA", fg="#137333", icon="✔", txt=t), unsafe_allow_html=True)
    if not pc["pros"]:
        st.caption("No pros flagged by the rules.")
with c:
    for t in pc["cons"] or []:
        st.markdown(badge.format(bg="#FCE8E6", fg="#C5221F", icon="✖", txt=t), unsafe_allow_html=True)
    if not pc["cons"]:
        st.caption("No cons flagged by the rules.")
