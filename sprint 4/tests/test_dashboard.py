"""Dashboard QA: every screen x every ticker, screener extremes/presets/CSV, profile load time."""
import io
import os
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ["NIFTY_LINK_CHECK"] = "0"            # no live HTTP calls in tests
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.dashboard.utils import screen  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src/dashboard/pages"
DB = ROOT / "data/nifty100.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="run run_sprint4.py first")


def tickers():
    with sqlite3.connect(DB) as con:
        return [r[0] for r in con.execute("SELECT id FROM companies ORDER BY id")]


def page(name, **state):
    at = AppTest.from_file(str(PAGES / name), default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_all_eight_pages_load():
    for f in sorted(p.name for p in PAGES.glob("0*.py")):
        assert not page(f).exception, f


@pytest.mark.parametrize("name", ["02_profile.py", "05_trends.py", "08_reports.py"])
def test_company_pages_for_all_92_tickers(name):
    bad = {}
    for t in tickers():
        at = page(name, ticker=t)
        if at.exception:
            bad[t] = at.exception[0].value[:200]
    assert not bad, bad


def test_peers_page_every_group_and_company():
    at = page("04_peers.py")
    groups = at.selectbox[0].options
    assert len(groups) == 11
    for g in groups:
        at.selectbox[0].select(g).run()
        assert not at.exception, g
        for c in at.selectbox[1].options:
            at.selectbox[1].select(c).run()
            assert not at.exception, (g, c)


def test_home_every_year_and_sector_page():
    at = page("01_home.py")
    for y in range(2019, 2025):
        at.sidebar.selectbox[0].select(y).run()
        assert not at.exception, y
    at = page("06_sectors.py")
    for s in at.selectbox[0].options:
        at.selectbox[0].select(s).run()
        assert not at.exception, s


def test_trends_three_metric_overlay():
    at = page("05_trends.py", ticker="TCS")
    at.multiselect[0].set_value(["Revenue (₹ Cr)", "ROE %", "Free cash flow (₹ Cr)"]).run()
    assert not at.exception


def test_profile_unknown_ticker_message():
    at = page("02_profile.py")
    at.text_input[0].input("zzzzqq").run()
    assert not at.exception
    assert any("Ticker not found — please try another" in w.value for w in at.warning)


def test_partial_history_shows_note():
    with sqlite3.connect(DB) as con:
        short = [r[0] for r in con.execute(
            "SELECT company_id FROM financial_ratios GROUP BY company_id HAVING COUNT(*) < 10 LIMIT 1")]
    if short:
        at = page("02_profile.py", ticker=short[0])
        assert not at.exception and any("Data available for" in i.value for i in at.info)


# ── screener ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def snap():
    from src.dashboard.utils import db
    return db.get_snapshot.__wrapped__() if hasattr(db.get_snapshot, "__wrapped__") else db.get_snapshot()


def test_screener_extremes_no_crash(snap):
    lo = {s["key"]: s["lo"] for s in screen.SLIDERS}
    hi = {s["key"]: s["hi"] for s in screen.SLIDERS}
    for vals in (lo, hi, screen.slider_defaults()):
        res, f = screen.run(snap, vals)
        view = screen.view_frame(res, f)
        screen.to_csv_bytes(view)
    assert len(screen.run(snap, screen.slider_defaults())[0]) == 92


@pytest.mark.parametrize("name", ["quality_compounder", "growth_accelerator", "dividend_champion",
                                  "debt_free_blue_chip", "turnaround_watch", "value_pick"])
def test_slider_presets_match_sprint3_engine(snap, name):
    from src.screener.engine import run_preset
    vals, extras = screen.preset_to_state(name)
    res, _ = screen.run(snap, vals, extras)
    assert abs(len(res) - len(run_preset(snap, name))) <= 1   # sliders use >=/<=, presets use strict >/<


def test_csv_is_well_formed(snap):
    vals, extras = screen.preset_to_state("quality_compounder")
    res, f = screen.run(snap, vals, extras)
    view = screen.view_frame(res, f)
    back = pd.read_csv(io.BytesIO(screen.to_csv_bytes(view)))
    assert list(back.columns) == list(view.columns) and len(back) == len(view)
    assert back.columns[:4].tolist() == ["Ticker", "Company", "Sector", "Composite score"]


def test_screener_page_preset_buttons_and_download():
    at = page("03_screener.py")
    at.button(key="btn_quality_compounder").click().run()
    assert not at.exception
    assert at.session_state["sl_roe"] == 15.0 and at.session_state["sl_de"] == 1.0
    assert any("companies match your filters" in s.value for s in at.subheader)


# ── performance ───────────────────────────────────────────────────────────────
def test_profile_loads_under_3_seconds():
    page("02_profile.py", ticker="TCS")                        # warm caches / imports
    times = {}
    for t in ["INFY", "HDFCBANK", "HINDUNILVR", "RELIANCE", "SUNPHARMA"]:
        s = time.perf_counter()
        at = page("02_profile.py", ticker=t)
        times[t] = time.perf_counter() - s
        assert not at.exception
    assert max(times.values()) < 3, times
