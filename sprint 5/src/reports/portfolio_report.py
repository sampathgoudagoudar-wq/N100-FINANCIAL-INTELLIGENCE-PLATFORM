"""Portfolio summary PDF: one page per company (alphabetical), top 6 KPIs with trend arrows."""
from __future__ import annotations

import logging

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from src.reports import common as C
from src.reports.common import fmt, month_label

logger = logging.getLogger(__name__)
PW, PH = A4
MX = 2.2 * cm
UW = PW - 2 * MX
FLAT_PCT = 2.0           # change within +/-2% (relative) counts as flat
OUT_DIR = C.ROOT / "reports" / "portfolio"

NONFIN = [("roe", "Return on Equity", 1, "%", True), ("roce", "Return on Capital Employed", 1, "%", True),
          ("opm", "Operating Profit Margin", 1, "%", True), ("npm", "Net Profit Margin", 1, "%", True),
          ("de", "Debt / Equity (lower is better)", 2, "x", False), ("sales", "Revenue (₹ Cr)", 0, "", True)]
FIN = [("roe", "Return on Equity", 1, "%", True), ("roa", "Return on Assets", 2, "%", True),
       ("npm", "Net Profit Margin", 1, "%", True), ("sales", "Revenue (₹ Cr)", 0, "", True),
       ("net_profit", "Net Profit (₹ Cr)", 0, "", True), ("eps", "EPS (₹)", 1, "", True)]
PB = ParagraphStyle("pb", fontName="DV", fontSize=8.4, leading=11)


def trend(new: float, old: float, higher_better: bool) -> str:
    """'up' if improved, 'down' if worsened, 'flat' if within 2% (relative), 'na' if not comparable."""
    if pd.isna(new) or pd.isna(old):
        return "na"
    base = abs(old) if old != 0 else 1.0
    rel = (new - old) / base * 100
    if abs(rel) <= FLAT_PCT:
        return "flat"
    return "up" if (rel > 0) == higher_better else "down"


def arrow(c: canvas.Canvas, x: float, y: float, kind: str, size: float = 14) -> None:
    """Draw an up / down / right arrow centred at (x, y)."""
    col = {"up": C.GREEN, "down": C.RED, "flat": C.GREY, "na": colors.HexColor("#BFBFBF")}[kind]
    c.setFillColor(col)
    s = size / 2
    p = c.beginPath()
    if kind == "up":
        p.moveTo(x, y + s); p.lineTo(x + s, y - s * .6); p.lineTo(x + s * .35, y - s * .6); p.lineTo(x + s * .35, y - s)
        p.lineTo(x - s * .35, y - s); p.lineTo(x - s * .35, y - s * .6); p.lineTo(x - s, y - s * .6)
    elif kind == "down":
        p.moveTo(x, y - s); p.lineTo(x + s, y + s * .6); p.lineTo(x + s * .35, y + s * .6); p.lineTo(x + s * .35, y + s)
        p.lineTo(x - s * .35, y + s); p.lineTo(x - s * .35, y + s * .6); p.lineTo(x - s, y + s * .6)
    elif kind == "flat":
        p.moveTo(x + s, y); p.lineTo(x - s * .6, y + s); p.lineTo(x - s * .6, y + s * .35); p.lineTo(x - s, y + s * .35)
        p.lineTo(x - s, y - s * .35); p.lineTo(x - s * .6, y - s * .35); p.lineTo(x - s * .6, y - s)
    else:
        c.rect(x - s * .6, y - 1, s * 1.2, 2, stroke=0, fill=1)
        return
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def draw_para(c, text: str, x: float, y_top: float, w: float, style=PB) -> float:
    """Draw a wrapping paragraph; return its height."""
    p = Paragraph(text, style)
    _, h = p.wrapOn(c, w, 500)
    p.drawOn(c, x, y_top - h)
    return h


def page(c: canvas.Canvas, data: C.Data, cid: str, n: int, total: int) -> None:
    """Draw one company page."""
    c.bookmarkPage(cid)
    c.addOutlineEntry(f"{cid} – {data.name(cid)}", cid, level=0)
    g = data.hist(cid)
    g = g.assign(roa=g.net_profit / g.total_assets.where(g.total_assets > 0) * 100) if len(g) else g
    fin = data.sector(cid) == "Financials"
    spec = FIN if fin else NONFIN
    c.setFillColor(C.NAVY); c.rect(MX, PH - 3.6 * cm, UW, 2.4 * cm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("DV-B", 10); c.drawRightString(MX + UW - 10, PH - 2.0 * cm, cid)
    draw_para(c, f'<font color="white" size="16"><b>{C.escape(data.name(cid)) if hasattr(C, "escape") else data.name(cid).replace("&", "&amp;")}</b></font>',
              MX + 10, PH - 1.45 * cm, UW - 3.6 * cm, ParagraphStyle("h", fontName="DV-B", fontSize=16, leading=19))
    c.setFont("DV", 8.5); c.setFillColor(colors.HexColor("#D9E2F3"))
    c.drawString(MX + 10, PH - 3.25 * cm, f"{data.sector(cid)}  |  {data.sub_sector(cid)}")
    c.drawRightString(MX + UW - 10, PH - 3.25 * cm, f"Portfolio page {n} of {total}")
    y = PH - 4.6 * cm
    c.setFillColor(C.NAVY); c.setFont("DV-B", 11)
    if len(g) == 0:
        c.drawString(MX, y, "No annual financial data available in source."); return
    last, prev = g.iloc[-1], (g.iloc[-2] if len(g) > 1 else None)
    c.drawString(MX, y, f"Top 6 KPIs – latest FY {month_label(last.year)}"
                 + (f" vs {month_label(prev.year)}" if prev is not None else "")); y -= 0.5 * cm
    cols = [MX, MX + 7.2 * cm, MX + 10.4 * cm, MX + 13.6 * cm, MX + 15.4 * cm]
    c.setFillColor(C.LIGHT); c.rect(MX, y - 0.75 * cm, UW, 0.75 * cm, stroke=0, fill=1)
    c.setFillColor(C.NAVY); c.setFont("DV-B", 8)
    for x, t in zip(cols, ["KPI", "Latest", "Previous", "Trend"]):
        c.drawString(x + 4, y - 0.5 * cm, t)
    y -= 0.75 * cm
    for i, (col, label, dec, suf, hb) in enumerate(spec):
        v = last.get(col); o = prev.get(col) if prev is not None else float("nan")
        row_h = 1.25 * cm
        if i % 2:
            c.setFillColor(colors.HexColor("#F6F8FB")); c.rect(MX, y - row_h, UW, row_h, stroke=0, fill=1)
        c.setFillColor(colors.black); c.setFont("DV", 9)
        c.drawString(cols[0] + 4, y - 0.75 * cm, label)
        c.setFont("DV-B", 11); c.setFillColor(C.NAVY); c.drawString(cols[1] + 4, y - 0.78 * cm, fmt(v, dec, suf))
        c.setFont("DV", 9); c.setFillColor(C.GREY); c.drawString(cols[2] + 4, y - 0.78 * cm, fmt(o, dec, suf))
        arrow(c, cols[3] + 14, y - 0.62 * cm, trend(v, o, hb))
        y -= row_h
    c.setStrokeColor(colors.HexColor("#D9D9D9")); c.line(MX, y, MX + UW, y)
    y -= 0.5 * cm
    c.setFont("DV", 6.8); c.setFillColor(C.GREY)
    c.drawString(MX, y, "Trend: up = improved, down = declined, right = flat (change within 2%). For D/E, lower is better.")
    y -= 0.9 * cm
    ci = data.cfi[data.cfi.company_id == cid]
    label = ci.capital_allocation_label.iloc[0] if len(ci) else "Insufficient data"
    c.setFillColor(C.NAVY); c.setFont("DV-B", 10); c.drawString(MX, y, "Capital allocation (latest FY)")
    c.setFillColor(C.PATTERN_COLOURS.get(label, C.GREY)); c.roundRect(MX + 6.4 * cm, y - 0.28 * cm, 6.2 * cm, 0.8 * cm, 6, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("DV-B", 9); c.drawCentredString(MX + 9.5 * cm, y - 0.02 * cm, str(label)[:34])
    y -= 1.3 * cm
    pcs = data.pc[data.pc.company_id == cid].sort_values("confidence_pct", ascending=False)
    for typ, colr, head in (("pro", "#2E7D32", "Top strength"), ("con", "#C62828", "Top concern")):
        s = pcs[pcs.type == typ]
        c.setFillColor(colors.HexColor(colr)); c.setFont("DV-B", 9.5); c.drawString(MX, y, head); y -= 0.25 * cm
        txt = (s.text.iloc[0] + f"  ({s.confidence_pct.iloc[0]:.0f}% confidence)") if len(s) else "None triggered"
        h = draw_para(c, txt.replace("&", "&amp;"), MX, y, UW)
        y -= h + 0.7 * cm
    c.setFont("DV", 6.5); c.setFillColor(C.GREY)
    c.drawString(MX, 1.1 * cm, f"Nifty 100 Financial Intelligence Platform | Portfolio Summary | Generated {C.RUN_DATE} | ₹ Crore, latest annual financials")
    c.drawRightString(MX + UW, 1.1 * cm, f"{n}")


def run() -> str:
    """Write reports/portfolio/portfolio_summary_YYYYMMDD.pdf (all companies, alphabetical)."""
    data = C.load_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"portfolio_summary_{C.FILE_DATE}.pdf"
    ids = sorted(data.companies.id.tolist())
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle("Nifty 100 Portfolio Summary"); c.setAuthor("Nifty 100 Financial Intelligence Platform")
    for i, cid in enumerate(ids, 1):
        page(c, data, cid, i, len(ids))
        c.showPage()
    c.save()
    return str(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
