"""Nifty 100 Analytics — Streamlit entry point.   Run:  streamlit run src/dashboard/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Nifty 100 Analytics", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = Path(__file__).parent / "pages"
nav = st.navigation([
    st.Page(PAGES / "01_home.py", title="Home", icon="🏠", default=True),
    st.Page(PAGES / "02_profile.py", title="Company Profile", icon="🏢"),
    st.Page(PAGES / "03_screener.py", title="Screener", icon="🔎"),
    st.Page(PAGES / "04_peers.py", title="Peer Comparison", icon="⚖️"),
    st.Page(PAGES / "05_trends.py", title="Trend Analysis", icon="📈"),
    st.Page(PAGES / "06_sectors.py", title="Sector Analysis", icon="🧭"),
    st.Page(PAGES / "07_capital.py", title="Capital Allocation", icon="💰"),
    st.Page(PAGES / "08_reports.py", title="Annual Reports", icon="📄"),
])
st.sidebar.caption("Nifty 100 Financial Intelligence Platform · 92 companies · ₹ Crore unless stated")
nav.run()
