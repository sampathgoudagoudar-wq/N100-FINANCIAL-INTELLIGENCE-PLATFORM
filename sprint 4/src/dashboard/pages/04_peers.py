import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.analytics.radar import AXES  # noqa: E402
from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import AMBER, TEAL, fmt, style_fig  # noqa: E402

st.title("Peer Comparison")
groups = db.get_peer_groups()
group = st.selectbox("Peer group", groups)
peers = db.get_peers(group)
if peers.empty:
    st.warning("No data for this peer group.")
    st.stop()

bench = peers.loc[peers["is_benchmark"] == 1, "company_id"].tolist()
ids = peers["company_id"].tolist()
names = dict(zip(peers["company_id"], peers["company_name"]))
company = st.selectbox("Company", ids, index=ids.index(bench[0]) if bench else 0,
                       format_func=lambda t: f"{t} — {names[t]}" + ("  ★ benchmark" if t in bench else ""))

axes = db.get_peer_axes()
labels = [lab.replace("\n", " ") for _, lab in AXES]
keys = [k for k, _ in AXES]
comp_v = axes.loc[company, keys].astype(float)
peer_v = axes.loc[ids, keys].astype(float).mean()

fig = go.Figure()
fig.add_trace(go.Scatterpolar(r=comp_v.fillna(0).tolist() + [comp_v.fillna(0).iloc[0]], theta=labels + [labels[0]],
                              fill="toself", name=company, line=dict(color=TEAL), fillcolor="rgba(15,123,108,0.25)"))
fig.add_trace(go.Scatterpolar(r=peer_v.fillna(0).tolist() + [peer_v.fillna(0).iloc[0]], theta=labels + [labels[0]],
                              name=f"{group} average", line=dict(color=AMBER, dash="dash")))
fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], tickvals=[20, 40, 60, 80, 100])),
                  title=f"{names[company]} vs {group} average (axis score 0–100, outer = better)")
st.plotly_chart(style_fig(fig, 480), width="stretch")
if comp_v.isna().any():
    st.caption("Axes with no value for this company (shown at 0): " + ", ".join(l for l, v in zip(labels, comp_v) if v != v))

st.subheader(f"{group}: side-by-side KPIs")
cols = [("roe", "ROE %"), ("roce", "ROCE %"), ("npm", "NPM %"), ("de", "D/E"), ("fcf", "FCF (Cr)"),
        ("pat_cagr_5y", "PAT CAGR 5y %"), ("rev_cagr_5y", "Rev CAGR 5y %"), ("eps_cagr_5y", "EPS CAGR 5y %"),
        ("icr", "ICR (x)"), ("asset_turnover", "Asset turnover"), ("composite_quality_score", "Composite")]
tbl = peers[["company_id", "company_name"]].copy()
tbl["Benchmark"] = ["★" if b == 1 else "" for b in peers["is_benchmark"]]
for k, lab in cols:
    tbl[lab] = peers[k].where(peers[k] < 1e9, float("inf")).astype(float)
tbl = tbl.rename(columns={"company_id": "Ticker", "company_name": "Company"})
isb = (peers["is_benchmark"] == 1).tolist()
num = [lab for _, lab in cols]
sty = (tbl.style.format({c: (lambda v: fmt(v, 2)) for c in num}, na_rep="N/A")
       .apply(lambda r: ["background-color:#FFD966;font-weight:600" if isb[r.name] else "" for _ in r], axis=1))
st.dataframe(sty, hide_index=True, width="stretch")

with st.expander("Percentile ranks within the group"):
    pp = db.get_peer_percentiles(group).pivot(index="company_id", columns="metric", values="percentile_rank")
    st.dataframe((pp * 100).round(0).reindex(ids), width="stretch")
    st.caption("PERCENT_RANK within the group; D/E inverted (lower debt = higher percentile).")
