import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import PALETTE, sim_note, style_fig  # noqa: E402

st.title("Capital Allocation Map")
cap = db.get_capital()
cap["size"] = cap["market_cap_crore"].fillna(cap["market_cap_crore"].median()).clip(lower=1)
sim_note()
n_pat = cap["pattern"].nunique()

order = cap.groupby("pattern")["size"].sum().sort_values(ascending=False).index.tolist()
cmap = {p: c for p, c in zip(order, PALETTE)}
fig = px.treemap(cap, path=["pattern", "company_name"], values="size", color="pattern", color_discrete_map=cmap,
                 hover_data={"company_id": True, "size": ":,.0f"})
fig.update_traces(textinfo="label", root_color="#F5F7FA",
                  hovertemplate="%{label}<br>Market cap ₹ %{value:,.0f} Cr<extra></extra>")
fig.update_layout(title="Patterns of operating / investing / financing cash flow (latest FY; tile size = market cap)")
st.plotly_chart(style_fig(fig, 560), width="stretch")
st.caption("Click a pattern in the map to drill into its companies, or pick one below. "
           "Pattern = signs of CFO / CFI / CFF: e.g. Self-funded Reinvestor = (+, −, −).")

counts = cap.groupby("pattern").size().sort_values(ascending=False)
pattern = st.selectbox("Pattern", counts.index.tolist(), format_func=lambda p: f"{p} ({counts[p]})")
rows = cap[cap["pattern"] == pattern][["company_id", "company_name", "broad_sector", "year", "cfo", "cfi", "cff"]]
rows.columns = ["Ticker", "Company", "Sector", "FY", "CFO (Cr)", "CFI (Cr)", "CFF (Cr)"]
st.dataframe(rows, hide_index=True, width="stretch")
st.caption(f"{len(cap)} companies in {n_pat} groups.")
