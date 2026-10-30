"""2-page company tearsheet PDF (ReportLab). Every table cell is a wrapping Paragraph (no text overflow)."""
from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepInFrame, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

from src.reports import common as C
from src.reports.common import Data, fmt, month_label

logger = logging.getLogger(__name__)
PAGE_W, PAGE_H = A4
MARGIN_X, MARGIN_TOP, MARGIN_BOT = 2.2 * cm, 1.3 * cm, 1.7 * cm
UW = PAGE_W - 2 * MARGIN_X                      # 16.6 cm usable width
MAX_PROS, MAX_CONS = 6, 5
MIN_YEARS = 3
OUT_DIR = C.ROOT / "reports" / "tearsheets"

ST = {
    "name": ParagraphStyle("name", fontName="DV-B", fontSize=15, leading=18, textColor=colors.white),
    "ticker": ParagraphStyle("ticker", fontName="DV-B", fontSize=14, leading=17, textColor=colors.white, alignment=2),
    "sub": ParagraphStyle("sub", fontName="DV", fontSize=7.5, leading=10, textColor=colors.HexColor("#D9E2F3")),
    "sub_r": ParagraphStyle("sub_r", fontName="DV", fontSize=7.5, leading=10, textColor=colors.HexColor("#D9E2F3"), alignment=2),
    "tl": ParagraphStyle("tl", fontName="DV", fontSize=7, leading=9, textColor=C.GREY),
    "tv": ParagraphStyle("tv", fontName="DV-B", fontSize=16, leading=19, textColor=C.NAVY),
    "ts": ParagraphStyle("ts", fontName="DV", fontSize=6.8, leading=8.5, textColor=C.GREY),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=9.5, leading=12, textColor=C.NAVY, spaceAfter=2),
    "bul": ParagraphStyle("bul", fontName="DV", fontSize=7.6, leading=9.8, leftIndent=9, bulletIndent=0, spaceAfter=2.5),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=7.4, leading=9.4),
    "cellb": ParagraphStyle("cellb", fontName="DV-B", fontSize=7.4, leading=9.4, textColor=colors.white),
    "note": ParagraphStyle("note", fontName="DV-I", fontSize=6.6, leading=8.4, textColor=C.GREY),
}

CAGR_FLAG_TEXT = {"TURNAROUND": "Turnaround (base was negative)", "DECLINE_TO_LOSS": "Turned loss-making",
                  "INSUFFICIENT": "Insufficient history", "BOTH_NEGATIVE": "Loss-making", "ZERO_BASE": "Zero base year"}


class Badge(Flowable):
    """Rounded coloured badge with centred text."""

    def __init__(self, text: str, colour, width: float = 6.2 * cm, height: float = 0.85 * cm):
        super().__init__()
        self.text, self.colour, self.width, self.height = text, colour, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        self.canv.setFillColor(self.colour)
        self.canv.roundRect(0, 0, self.width, self.height, 6, stroke=0, fill=1)
        self.canv.setFillColor(colors.white)
        size = 9.5
        while self.canv.stringWidth(self.text, "DV-B", size) > self.width - 10 and size > 5:
            size -= 0.5
        self.canv.setFont("DV-B", size)
        self.canv.drawCentredString(self.width / 2, self.height / 2 - size / 3, self.text)


def img(buf, width: float) -> Image:
    """Image scaled to a given width, preserving aspect ratio."""
    w, h = ImageReader(buf).getSize()
    buf.seek(0)
    return Image(buf, width=width, height=width * h / w)


def kpi_tiles(g: pd.DataFrame, cg: pd.Series, fin: bool) -> list[dict]:
    """Six KPI tiles (label, value, subtext, colour) for a company."""
    g = g.assign(roa=g.net_profit / g.total_assets.where(g.total_assets > 0) * 100)
    last = g.iloc[-1]
    prev = g.iloc[-2] if len(g) > 1 else None

    def delta(col: str, higher_better: bool = True, unit: str = " pts", dec: int = 1) -> tuple[str, object]:
        if prev is None or pd.isna(last[col]) or pd.isna(prev[col]):
            return "no prior-year comparison", C.GREY
        d = float(last[col] - prev[col])
        good = (d >= 0) == higher_better
        arrow = "▲" if d > 0 else ("▼" if d < 0 else "►")
        return f"{arrow} {d:+.{dec}f}{unit} vs {month_label(prev.year)}", (C.GREEN if good else C.RED) if abs(d) > 1e-9 else C.GREY

    def cagr_tile(key: str, label: str) -> dict:
        v, f = cg.get(f"{key}_cagr_5y"), cg.get(f"{key}_cagr_5y_flag", "INSUFFICIENT")
        if pd.isna(v):
            return dict(label=label, value="n/a", sub=CAGR_FLAG_TEXT.get(f, f), col=C.GREY)
        return dict(label=label, value=fmt(v, 1, "%"), sub="compound annual rate", col=C.GREEN if v >= 10 else C.GREY)

    roe_sub, roe_c = delta("roe")
    t = [dict(label="Return on Equity", value=fmt(last.roe, 1, "%"), sub=roe_sub, col=roe_c)]
    if fin:
        s, c = delta("roa")
        t.append(dict(label="Return on Assets", value=fmt(last.roa, 2, "%"), sub=s, col=c))
        s, c = delta("npm")
        t.append(dict(label="Net Profit Margin", value=fmt(last.npm, 1, "%"), sub=s, col=c))
        t += [cagr_tile("rev", "Revenue CAGR (5Y)"), cagr_tile("pat", "Net Profit CAGR (5Y)"), cagr_tile("eps", "EPS CAGR (5Y)")]
    else:
        s, c = delta("roce")
        t.append(dict(label="Return on Capital Employed", value=fmt(last.roce, 1, "%"), sub=s, col=c))
        s, c = delta("opm")
        t.append(dict(label="Operating Profit Margin", value=fmt(last.opm, 1, "%"), sub=s, col=c))
        s, c = delta("de", higher_better=False, unit="x", dec=2)
        de_txt = "Debt free" if last.debt_free else fmt(last.de, 2, "x")
        t.append(dict(label="Debt / Equity", value=de_txt, sub=s, col=c))
        t += [cagr_tile("rev", "Revenue CAGR (5Y)"), cagr_tile("pat", "Net Profit CAGR (5Y)")]
    return t


def tile_table(tiles: list[dict]) -> Table:
    """2 rows x 3 columns of KPI tiles."""
    cells = []
    for tl in tiles:
        sub_style = ParagraphStyle("s", parent=ST["ts"], textColor=tl["col"])
        cells.append([Paragraph(escape(tl["label"]).upper(), ST["tl"]), Paragraph(escape(tl["value"]), ST["tv"]),
                      Paragraph(escape(tl["sub"]), sub_style)])
    rows = [cells[0:3], cells[3:6]]
    gap = 0.25 * cm
    w = (UW - 2 * gap) / 3
    full = []
    for r in rows:
        line = []
        for i, c in enumerate(r):
            inner = Table([[c[0]], [c[1]], [c[2]]], colWidths=[w])
            inner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C.LIGHT), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LINEBEFORE", (0, 0), (0, -1), 3, C.TEAL)]))
            line.append(inner)
            if i < 2:
                line.append("")
        full.append(line)
    t = Table(full, colWidths=[w, gap, w, gap, w])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def header(name: str, ticker: str, sector: str, sub: str, fy: str, page: int) -> Table:
    """Navy header bar with company name and ticker."""
    left = [Paragraph(escape(name), ST["name"]),
            Paragraph(escape(f"{sector}  |  {sub}  |  Latest FY: {fy}  |  ₹ Crore"), ST["sub"])]
    right = [Paragraph(escape(ticker), ST["ticker"]), Paragraph(f"Tearsheet – page {page} of 2", ST["sub_r"])]
    t = Table([[left, right]], colWidths=[UW * 0.72, UW * 0.28])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C.NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def bullets(items: list[tuple[str, float]], colour, empty: str) -> list:
    """Coloured bullet paragraphs with confidence."""
    hexc = colour.hexval()[2:] if hasattr(colour, "hexval") else "000000"
    if not items:
        return [Paragraph(empty, ST["note"])]
    return [Paragraph(f'{escape(t)} <font size="6.2" color="#7F7F7F">({c:.0f}%)</font>', ST["bul"],
                      bulletText="●") for t, c in items] if False else [
        Paragraph(f'<font color="#{hexc}">●</font>&nbsp;{escape(t)} <font size="6.2" color="#7F7F7F">({c:.0f}%)</font>',
                  ParagraphStyle("b", parent=ST["bul"], leftIndent=0, firstLineIndent=0)) for t, c in items]


def footer(canvas, doc):
    """Page footer with provenance and page number."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#BFBFBF"))
    canvas.line(MARGIN_X, 1.35 * cm, PAGE_W - MARGIN_X, 1.35 * cm)
    canvas.setFont("DV", 6.3)
    canvas.setFillColor(C.GREY)
    canvas.drawString(MARGIN_X, 1.0 * cm, "Nifty 100 Financial Intelligence Platform  |  Company Tearsheet  |  Generated " + C.RUN_DATE)
    canvas.drawRightString(PAGE_W - MARGIN_X, 1.0 * cm, f"Page {canvas.getPageNumber()} of 2")
    canvas.drawString(MARGIN_X, 0.65 * cm, "Source: company financial statements (annual). Pros/cons are rule-based with confidence scores; not investment advice.")
    canvas.restoreState()


def annual_years(data: Data, cid: str) -> int:
    """Number of annual P&L rows available for a company."""
    return len(data.hist(cid))


def build(cid: str, data: Data, path: Path) -> int:
    """Create the 2-page tearsheet; returns number of pages written."""
    g = data.hist(cid)
    last = g.iloc[-1]
    fin = bool(last.is_financial)
    cg = data.cagr[data.cagr.company_id == cid].iloc[0]
    name, sector = data.name(cid), data.sector(cid)
    frame_h = PAGE_H - MARGIN_TOP - MARGIN_BOT - 12
    doc = BaseDocTemplate(str(path), pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=MARGIN_TOP,
                          bottomMargin=MARGIN_BOT, title=f"{name} ({cid}) – Tearsheet", author="Nifty 100 Financial Intelligence Platform")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(MARGIN_X, MARGIN_BOT, UW, PAGE_H - MARGIN_TOP - MARGIN_BOT,
                                                             leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=footer)])
    half = UW / 2 - 0.15 * cm
    # ---------------- page 1 ----------------
    two = Table([[img(C.bar_chart(g, "sales", "Revenue (₹ Cr)", C.HEX["teal"], h=2.9), half),
                  img(C.bar_chart(g, "net_profit", "Net Profit (₹ Cr)", C.HEX["green"], h=2.9), half)]], colWidths=[UW / 2, UW / 2])
    two.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    p1 = [header(name, cid, sector, data.sub_sector(cid), month_label(last.year), 1), Spacer(1, 10),
          Paragraph("Key Performance Indicators", ST["h2"]), tile_table(kpi_tiles(g, cg, fin)), Spacer(1, 4),
          Paragraph("10-Year Revenue and Net Profit", ST["h2"]), two, Spacer(1, 4),
          Paragraph("Return on Equity and Return on Capital Employed", ST["h2"]),
          img(C.roe_roce_chart(g, fin, h=3.2), UW)]
    if fin:
        p1.append(Paragraph("Note: for banks / NBFCs / insurers, ROCE, operating margin and D/E are structurally not comparable "
                            "to non-financial companies and are therefore not shown.", ST["note"]))
    # ---------------- page 2 ----------------
    cfrows = g[g.operating_activity.notna()]
    cfl = cfrows.iloc[-1] if len(cfrows) else None
    pair = Table([[img(C.bs_chart(g, h=3.3), half), img(C.cf_waterfall(cfl, h=3.3), half)]], colWidths=[UW / 2, UW / 2])
    pair.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    ci = data.cfi[data.cfi.company_id == cid]
    ci = ci.iloc[0] if len(ci) else None
    label = (ci.capital_allocation_label if ci is not None else "Insufficient data")
    col = C.PATTERN_COLOURS.get(label, C.GREY)
    hist = cfrows.tail(4)
    hist_txt = "  →  ".join(f"{month_label(r.year)}: {r.pattern_label}" for _, r in hist.iterrows()) or "No cash-flow history in source"
    badge_tbl = Table([[Badge(label, col), Paragraph(f"<b>Pattern history</b> (CFO / CFI / CFF signs): {escape(hist_txt)}", ST["cell"])]],
                      colWidths=[6.5 * cm, UW - 6.5 * cm])
    badge_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    # cash-flow intelligence strip
    def cell(h, v, sub=""):
        vs = ParagraphStyle("v", parent=ST["cell"], fontName="DV-B", fontSize=10, leading=12, textColor=C.NAVY)
        return [Paragraph(h, ST["tl"]), Paragraph(v, vs), Paragraph(sub or "&nbsp;", ST["ts"])]
    if ci is not None and not pd.isna(ci.cfo_quality_score):
        flags = ", ".join(x for x, on in (("Distress signal", ci.distress_flag), ("Deleveraging", ci.deleveraging_flag)) if on) or "None"
        fcf_sub = "" if not pd.isna(ci.fcf_cagr_5yr) else CAGR_FLAG_TEXT.get(str(ci.fcf_cagr_flag), "")
        strip = [cell("CFO QUALITY (5Y CFO/PAT)", fmt(ci.cfo_quality_score, 2, "x"), escape(str(ci.cfo_quality_label))),
                 cell("CAPEX INTENSITY", fmt(ci.capex_intensity_pct, 1, "%"), escape(str(ci.capex_label))),
                 cell("FCF CONVERSION", fmt(ci.fcf_conversion_pct, 0, "%"), "FCF / operating profit"),
                 cell("FCF CAGR (5Y)", fmt(ci.fcf_cagr_5yr, 1, "%"), escape(fcf_sub)),
                 cell("FLAGS", escape(flags) if len(flags) < 14 else "2 flags", escape(flags) if len(flags) >= 14 else "")]
    else:
        strip = [cell("CASH FLOW INTELLIGENCE", "n/a", "No cash-flow statement in source")] + [""] * 4
    w5 = [UW * 0.24, UW * 0.2, UW * 0.2, UW * 0.2, UW * 0.16]
    st = Table([[strip[i] for i in range(5)]], colWidths=w5)
    st.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C.LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    pcs = data.pc[data.pc.company_id == cid]
    pros = pcs[pcs.type == "pro"].sort_values("confidence_pct", ascending=False)
    cons = pcs[pcs.type == "con"].sort_values("confidence_pct", ascending=False)
    pl = [Paragraph("<font color='#2E7D32'>Pros</font>", ST["h2"])] + bullets(
        list(zip(pros.text[:MAX_PROS], pros.confidence_pct[:MAX_PROS])), colors.HexColor("#2E7D32"), "No pro rule triggered.")
    cl = [Paragraph("<font color='#C62828'>Cons</font>", ST["h2"])] + bullets(
        list(zip(cons.text[:MAX_CONS], cons.confidence_pct[:MAX_CONS])), colors.HexColor("#C62828"), "No con rule triggered.")
    extra = []
    if len(pros) > MAX_PROS:
        pl.append(Paragraph(f"+{len(pros) - MAX_PROS} more in pros_cons_generated.csv", ST["note"]))
    if len(cons) > MAX_CONS:
        cl.append(Paragraph(f"+{len(cons) - MAX_CONS} more in pros_cons_generated.csv", ST["note"]))
    pcw = Table([[pl, cl]], colWidths=[UW / 2, UW / 2])
    pcw.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 10),
                             ("LEFTPADDING", (1, 0), (1, 0), 10), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                             ("LINEAFTER", (0, 0), (0, 0), 0.5, colors.HexColor("#D9D9D9"))]))
    p2 = [header(name, cid, sector, data.sub_sector(cid), month_label(last.year), 2), Spacer(1, 8),
          Paragraph("Balance Sheet Composition and Latest-Year Cash Flow", ST["h2"]), pair, Spacer(1, 4),
          Paragraph("Capital Allocation", ST["h2"]), badge_tbl, Spacer(1, 6),
          Paragraph("Cash Flow Intelligence", ST["h2"]), st, Spacer(1, 8), pcw]
    story = [KeepInFrame(UW, frame_h, p1, mode="shrink"), PageBreak(), KeepInFrame(UW, frame_h, p2, mode="shrink")]
    doc.build(story)
    return 2


def run(only: list[str] | None = None) -> pd.DataFrame:
    """Batch-generate tearsheets for all companies; log skipped (<3 years) to output/skipped_tearsheets.csv."""
    data = C.load_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skipped, done = [], []
    for cid in (only or data.companies.id.tolist()):
        n = annual_years(data, cid)
        if n < MIN_YEARS:
            skipped.append(dict(company_id=cid, company_name=data.name(cid), annual_years=n,
                                reason=f"fewer than {MIN_YEARS} years of annual data"))
            continue
        try:
            build(cid, data, OUT_DIR / f"{cid}_tearsheet.pdf")
            done.append(cid)
        except Exception as exc:  # noqa: BLE001
            logger.exception("tearsheet failed for %s", cid)
            skipped.append(dict(company_id=cid, company_name=data.name(cid), annual_years=n, reason=f"error: {exc}"))
    if only is None:
        pd.DataFrame(skipped, columns=["company_id", "company_name", "annual_years", "reason"]).to_csv(
            C.OUT / "skipped_tearsheets.csv", index=False)
    return pd.DataFrame(skipped)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    r = run(sys.argv[1:] or None)
    print("skipped/errors:", r.to_dict("records"))
