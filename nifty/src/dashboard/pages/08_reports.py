import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import requests  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard.utils import db  # noqa: E402
from src.dashboard.utils.ui import company_picker, is_na  # noqa: E402


@st.cache_data(ttl=3600, show_spinner=False)
def check_urls(urls: tuple[str, ...]) -> dict[str, str]:
    """HEAD every URL: 'ok' (<400), 'missing' (404/410), 'error' (other status) or 'unknown' (no response)."""
    def one(u):
        try:
            r = requests.head(u, timeout=3, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            return u, "ok" if r.status_code < 400 else ("missing" if r.status_code in (404, 410) else "error")
        except requests.RequestException:
            return u, "unknown"
    with ThreadPoolExecutor(max_workers=16) as ex:
        return dict(ex.map(one, urls))


BADGE = "<span style='padding:2px 9px;border-radius:10px;font-size:0.8rem;color:{fg};background:{bg}'>{txt}</span>"
STATES = {
    "ok": ("#137333", "#E6F4EA", "Available"),
    "missing": ("#C5221F", "#FCE8E6", "Report unavailable"),
    "error": ("#C5221F", "#FCE8E6", "Report unavailable"),
    "unknown": ("#5F6368", "#ECEFF1", "Not verified"),
    "none": ("#C5221F", "#FCE8E6", "Report unavailable"),
}

st.title("Annual Reports")
ticker = company_picker("reports")
if ticker is None:
    st.stop()
docs = db.get_docs(ticker)
live = st.checkbox("Check links live (BSE)", value=os.environ.get("NIFTY_LINK_CHECK", "1") != "0")
if docs.empty:
    st.info("No annual reports on file for this company.")
    st.stop()

urls = tuple(u for u in docs["Annual_Report"].tolist() if not is_na(u) and str(u).startswith("http"))
status = check_urls(urls) if (live and urls) else {}
st.write(f"{len(docs)} report years on file · {len(urls)} with a link")
for _, r in docs.iterrows():
    u = r["Annual_Report"]
    if is_na(u) or not str(u).startswith("http"):
        state = "none"
    else:
        state = status.get(u, "unknown")
    fg, bg, txt = STATES[state]
    c1, c2, c3 = st.columns([1, 4, 2])
    c1.markdown(f"**{int(r['year'])}**")
    c2.markdown(f"[Open annual report (PDF)]({u})" if state != "none" else "—")
    c3.markdown(BADGE.format(fg=fg, bg=bg, txt=txt), unsafe_allow_html=True)
if live and status and all(v == "unknown" for v in status.values()):
    st.caption("Link status could not be verified from this network; links are still clickable.")
