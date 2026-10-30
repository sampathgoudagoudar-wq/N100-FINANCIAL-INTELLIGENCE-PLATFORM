"""Shared data access, formatting and chart helpers for all PDF reports."""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402

from src.analytics.ratios import build_panel, company_cagrs  # noqa: E402
from src.etl.clean import OUT, RAW  # noqa: E402

logger = logging.getLogger(__name__)
ROOT = OUT.parent
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DV", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DV-B", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("DV-I", str(FONT_DIR / "DejaVuSans-Oblique.ttf")))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-B")

NAVY = colors.HexColor("#1F3864")
TEAL = colors.HexColor("#2E75B6")
GREEN = colors.HexColor("#2E7D32")
RED = colors.HexColor("#C62828")
AMBER = colors.HexColor("#E69F00")
GREY = colors.HexColor("#595959")
LIGHT = colors.HexColor("#EEF2F8")
HEX = dict(navy="#1F3864", teal="#2E75B6", green="#2E7D32", red="#C62828", amber="#E69F00", grey="#7F7F7F",
           orange="#ED7D31", light="#9DC3E6")
RUN_DATE = "29 Oct 2026"
FILE_DATE = "20261029"


def fmt(v, d: int = 1, suffix: str = "", na: str = "n/a") -> str:
    """Format a number with thousands separators; NaN/None -> na."""
    if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
        return na
    return f"{v:,.{d}f}{suffix}"


def month_label(y: str) -> str:
    """'2024-03' -> 'Mar-24'."""
    mons = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{mons[int(y[5:7]) - 1]}-{y[2:4]}"


PATTERN_COLOURS = {"Reinvestor": GREEN, "Shareholder Returns": GREEN, "Aggressive Expander": AMBER,
                   "Cash Accumulator": TEAL, "Cash Burn - Divestment Funded": AMBER, "Cash Drain": RED,
                   "Distress Signal": RED, "Distress - Asset Liquidation": RED}


@dataclass
class Data:
    """All analytical tables needed by the report writers."""
    panel: pd.DataFrame
    cagr: pd.DataFrame
    cfi: pd.DataFrame
    pc: pd.DataFrame
    companies: pd.DataFrame
    sectors: pd.DataFrame
    latest: pd.DataFrame

    def name(self, cid: str) -> str:
        """Company display name."""
        r = self.companies[self.companies.id == cid]
        return str(r.company_name.iloc[0]) if len(r) else cid

    def sector(self, cid: str) -> str:
        """Broad sector."""
        r = self.sectors[self.sectors.company_id == cid]
        return str(r.broad_sector.iloc[0]) if len(r) else "n/a"

    def sub_sector(self, cid: str) -> str:
        """Sub sector."""
        r = self.sectors[self.sectors.company_id == cid]
        return str(r.sub_sector.iloc[0]) if len(r) else "n/a"

    def hist(self, cid: str) -> pd.DataFrame:
        """Annual panel rows for a company (chronological)."""
        return self.panel[self.panel.company_id == cid].sort_values("fy")


@lru_cache(maxsize=1)
def load_data() -> Data:
    """Load every input once (panel, CAGRs, Sprint-5 outputs)."""
    p = build_panel()
    cg = company_cagrs(p)
    co = pd.read_excel(RAW / "companies.xlsx", header=1)
    co["id"] = co.id.str.strip().str.upper()
    co["company_name"] = co.company_name.astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    sec = pd.read_excel(ROOT / "data/supporting/sectors.xlsx")
    sec["company_id"] = sec.company_id.str.strip().str.upper()
    cfi = pd.read_excel(OUT / "cashflow_intelligence.xlsx", sheet_name="Cashflow Intelligence")
    pc = pd.read_csv(OUT / "pros_cons_generated.csv")
    latest = p.sort_values("fy").groupby("company_id").tail(1).merge(cg, on="company_id", how="left")
    latest["roa"] = latest.net_profit / latest.total_assets.where(latest.total_assets > 0) * 100
    return Data(p, cg, cfi, pc, co, sec, latest)


def chart_to_png(fig, dpi: int = 170) -> io.BytesIO:
    """Render a matplotlib figure to an in-memory PNG."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=6.5, length=2)
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.set_axisbelow(True)


def empty_chart(w: float, h: float, msg: str, title: str) -> io.BytesIO:
    """Placeholder panel for charts with no source data."""
    fig, ax = plt.subplots(figsize=(w, h))
    ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=8, color=HEX["grey"], wrap=True)
    ax.set_title(title, fontsize=8.5, fontweight="bold", color=HEX["navy"], loc="left")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#D9D9D9")
    return chart_to_png(fig)


def bar_chart(g: pd.DataFrame, col: str, title: str, color: str, w: float = 3.3, h: float = 2.2) -> io.BytesIO:
    """10-year bar chart of a P&L column (negatives in red)."""
    g = g.tail(10)
    if g.empty or g[col].dropna().empty:
        return empty_chart(w, h, "No data in source", title)
    fig, ax = plt.subplots(figsize=(w, h))
    vals = g[col].astype(float).values
    ax.bar(range(len(g)), vals, color=[HEX["red"] if v < 0 else color for v in vals], width=0.68)
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels([month_label(y) for y in g.year], rotation=55, ha="right")
    ax.set_title(title, fontsize=8.5, fontweight="bold", color=HEX["navy"], loc="left")
    ax.set_ylabel("₹ Cr", fontsize=6.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    _style(ax)
    return chart_to_png(fig)


def roe_roce_chart(g: pd.DataFrame, fin: bool, w: float = 6.8, h: float = 2.3) -> io.BytesIO:
    """ROE (left axis) and ROCE (right axis) dual-axis line chart; ROCE omitted for financials."""
    g = g.tail(10)
    title = "Return on Equity vs Return on Capital Employed" if not fin else "Return on Equity (ROCE not meaningful for financials)"
    if g.empty or g.roe.dropna().empty:
        return empty_chart(w, h, "ROE not computable (no balance sheet / non-positive equity)", title)
    fig, ax = plt.subplots(figsize=(w, h))
    x = range(len(g))
    ax.plot(x, g.roe, color=HEX["navy"], marker="o", ms=3, lw=1.6, label="ROE % (left)")
    ax.set_ylabel("ROE %", fontsize=7, color=HEX["navy"])
    ax.set_xticks(list(x))
    ax.set_xticklabels([month_label(y) for y in g.year], rotation=0, fontsize=6.5)
    handles = ax.get_lines()
    if not fin and g.roce.dropna().size:
        ax2 = ax.twinx()
        ax2.plot(x, g.roce, color=HEX["orange"], marker="s", ms=3, lw=1.6, ls="--", label="ROCE % (right)")
        ax2.set_ylabel("ROCE %", fontsize=7, color=HEX["orange"])
        ax2.tick_params(labelsize=6.5, length=2)
        ax2.spines["top"].set_visible(False)
        handles = handles + ax2.get_lines()
    if len(handles) > 1:
        ax.legend(handles=handles, labels=[h_.get_label() for h_ in handles], fontsize=6.5, loc="upper center",
                  bbox_to_anchor=(0.5, -0.08), frameon=False, ncol=2)
    ax.set_title(title, fontsize=8.5, fontweight="bold", color=HEX["navy"], loc="left")
    _style(ax)
    return chart_to_png(fig)


def bs_chart(g: pd.DataFrame, w: float = 3.5, h: float = 2.5) -> io.BytesIO:
    """Stacked bar: equity, borrowings, other liabilities by year."""
    title = "Balance Sheet Composition (₹ Cr)"
    g = g.tail(10)
    g = g[g.total_equity.notna() & g.borrowings.notna() & g.other_liabilities.notna()]
    if g.empty:
        return empty_chart(w, h, "No balance sheet in source", title)
    fig, ax = plt.subplots(figsize=(w, h))
    x = np.arange(len(g))
    eq = g.total_equity.clip(lower=0).values
    ax.bar(x, eq, color=HEX["navy"], width=0.7, label="Equity")
    ax.bar(x, g.borrowings.values, bottom=eq, color=HEX["red"], width=0.7, label="Borrowings")
    ax.bar(x, g.other_liabilities.values, bottom=eq + g.borrowings.values, color=HEX["light"], width=0.7, label="Other liabilities")
    ax.set_xticks(x)
    ax.set_xticklabels([month_label(y) for y in g.year], rotation=55, ha="right")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(fontsize=6.5, frameon=False, loc="upper left")
    ax.set_title(title, fontsize=8.5, fontweight="bold", color=HEX["navy"], loc="left")
    _style(ax)
    return chart_to_png(fig)


def cf_waterfall(row: pd.Series | None, w: float = 3.3, h: float = 2.5) -> io.BytesIO:
    """Waterfall CFO -> CFI -> CFF -> Net cash flow for one year."""
    if row is None or pd.isna(row.operating_activity):
        return empty_chart(w, h, "No cash-flow statement in source", "Cash Flow Waterfall")
    cfo, cfi, cff = float(row.operating_activity), float(row.investing_activity), float(row.financing_activity)
    net = cfo + cfi + cff
    title = f"Cash Flow Waterfall – {month_label(row.year)} (₹ Cr)"
    fig, ax = plt.subplots(figsize=(w, h))
    steps = [("CFO", 0, cfo), ("CFI", cfo, cfi), ("CFF", cfo + cfi, cff)]
    for i, (_, start, d) in enumerate(steps):
        ax.bar(i, d, bottom=start, color=HEX["green"] if d >= 0 else HEX["red"], width=0.6)
    ax.bar(3, net, color=HEX["navy"], width=0.6)
    tops = [cfo, cfo + cfi, cfo + cfi + cff, net]
    for i, v in enumerate([cfo, cfi, cff, net]):
        ax.annotate(f"{v:,.0f}", (i, tops[i]), ha="center", va="bottom" if v >= 0 else "top", fontsize=6.5,
                    xytext=(0, 2 if v >= 0 else -2), textcoords="offset points")
    ax.plot([0.3, 0.7], [cfo, cfo], color=HEX["grey"], lw=0.6)
    ax.plot([1.3, 1.7], [cfo + cfi] * 2, color=HEX["grey"], lw=0.6)
    ax.plot([2.3, 2.7], [net] * 2, color=HEX["grey"], lw=0.6)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(range(4)); ax.set_xticklabels(["CFO", "CFI", "CFF", "Net cash flow"])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ymin, ymax = min(0, cfo, cfo + cfi, net), max(0, cfo, cfo + cfi, net)
    pad = (ymax - ymin) * 0.18 or 1
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_title(title, fontsize=8.5, fontweight="bold", color=HEX["navy"], loc="left")
    _style(ax)
    return chart_to_png(fig)
