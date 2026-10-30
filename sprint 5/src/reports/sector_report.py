"""Sector PDF reports: summary page (median KPIs, best/worst, ROE chart) + company table with 8 metrics each."""
from __future__ import annotations

import logging
from xml.sax.saxutils import escape

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepInFrame, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from src.reports import common as C
from src.reports.common import fmt
from src.reports.tearsheet import img

logger = logging.getLogger(__name__)
PW, PH = landscape(A4)
MX, MT, MB = 1.5 * cm, 1.2 * cm, 1.6 * cm
UW = PW - 2 * MX
OUT_DIR = C.ROOT / "reports" / "sector"

# (column, label, decimals, suffix, higher_is_better)
NONFIN = [("roe", "ROE", 1, "%", True), ("roce", "ROCE", 1, "%", True), ("opm", "OPM", 1, "%", True),
          ("npm", "Net margin", 1, "%", True), ("de", "Debt / Equity", 2, "x", False),
          ("rev_cagr_5y", "Revenue CAGR 5Y", 1, "%", True), ("pat_cagr_5y", "Profit CAGR 5Y", 1, "%", True),
          ("cfo_quality_score", "CFO quality (CFO/PAT)", 2, "x", True)]
FIN = [("roe", "ROE", 1, "%", True), ("roa", "ROA", 2, "%", True), ("npm", "Net margin", 1, "%", True),
       ("rev_cagr_5y", "Revenue CAGR 5Y", 1, "%", True), ("pat_cagr_5y", "Profit CAGR 5Y", 1, "%", True),
       ("eps_cagr_5y", "EPS CAGR 5Y", 1, "%", True), ("dividend_payout", "Dividend payout", 0, "%", True),
       ("net_profit", "Net profit (₹ Cr)", 0, "", True)]

S = {
    "title": ParagraphStyle("t", fontName="DV-B", fontSize=18, leading=22, textColor=colors.white),
    "sub": ParagraphStyle("s", fontName="DV", fontSize=8.5, leading=11, textColor=colors.HexColor("#D9E2F3")),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=10.5, leading=13, textColor=C.NAVY, spaceAfter=3),
    "c": ParagraphStyle("c", fontName="DV", fontSize=7.6, leading=9.6),
    "cr": ParagraphStyle("cr", fontName="DV", fontSize=7.6, leading=9.6, alignment=2),
    "ch": ParagraphStyle("ch", fontName="DV-B", fontSize=7.4, leading=9.2, textColor=colors.white, alignment=1),
    "chl": ParagraphStyle("chl", fontName="DV-B", fontSize=7.4, leading=9.2, textColor=colors.white),
    "note": ParagraphStyle("n", fontName="DV-I", fontSize=7, leading=9, textColor=C.GREY),
}


def sector_frame(data: C.Data, sector: str) -> tuple[pd.DataFrame, list]:
    """Latest-year metrics for every company in a sector (+ metric spec)."""
    ids = data.sectors[data.sectors.broad_sector == sector].company_id.tolist()
    d = data.latest[data.latest.company_id.isin(ids)].copy()
    cfi = data.cfi.set_index("company_id")
    d["cfo_quality_score"] = d.company_id.map(cfi.cfo_quality_score)
    d["pattern"] = d.company_id.map(cfi.capital_allocation_label)
    d["name"] = d.company_id.map(data.name)
    d["sub_sector"] = d.company_id.map(data.sub_sector)
    spec = FIN if sector == "Financials" else NONFIN
    missing = set(ids) - set(d.company_id)
    for m in missing:                       # company without any P&L: keep a blank row
        d.loc[len(d)] = {"company_id": m, "name": data.name(m), "sub_sector": data.sub_sector(m), "pattern": "n/a"}
    return d.sort_values("company_id").reset_index(drop=True), spec


def roe_chart(d: pd.DataFrame, med: float, sector: str):
    """Horizontal bars of ROE per company vs sector median."""
    x = d[["company_id", "roe"]].dropna().sort_values("roe")
    h = max(2.6, 0.2 * len(x) + 0.9)
    fig, ax = plt.subplots(figsize=(5.0, h))
    ax.barh(x.company_id, x.roe, color=[C.HEX["navy"] if v >= med else C.HEX["light"] for v in x.roe], height=0.7)
    ax.axvline(med, color=C.HEX["orange"], ls="--", lw=1.1)
    ax.text(med, len(x) - 0.4, f" median {med:.1f}%", color=C.HEX["orange"], fontsize=6.5, va="bottom")
    ax.tick_params(labelsize=6.3, length=2)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.set_title("Return on Equity by company (latest FY, %)", fontsize=8.5, fontweight="bold", color=C.HEX["navy"], loc="left")
    return C.chart_to_png(fig)


def hdr(title: str, sub: str) -> Table:
    """Navy title bar."""
    t = Table([[[Paragraph(escape(title), S["title"]), Paragraph(escape(sub), S["sub"])]]], colWidths=[UW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C.NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def footer(canvas, doc):
    """Footer with provenance."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#BFBFBF")); canvas.line(MX, 1.2 * cm, PW - MX, 1.2 * cm)
    canvas.setFont("DV", 6.5); canvas.setFillColor(C.GREY)
    canvas.drawString(MX, 0.8 * cm, f"Nifty 100 Financial Intelligence Platform | Sector Report | Generated {C.RUN_DATE} | Latest annual financials, ₹ Crore")
    canvas.drawRightString(PW - MX, 0.8 * cm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def build(data: C.Data, sector: str, path) -> int:
    """Write one sector report."""
    d, spec = sector_frame(data, sector)
    n = len(d)
    doc = BaseDocTemplate(str(path), pagesize=landscape(A4), leftMargin=MX, rightMargin=MX, topMargin=MT, bottomMargin=MB,
                          title=f"{sector} – Sector Report", author="Nifty 100 Financial Intelligence Platform")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(MX, MB, UW, PH - MT - MB, leftPadding=0, rightPadding=0,
                                                              topPadding=0, bottomPadding=0)], onPage=footer)])
    fh = PH - MT - MB - 10
    # ---- summary page ----
    rows = [[Paragraph(h, S["chl"] if i == 0 else S["ch"]) for i, h in enumerate(
        ["KPI (latest FY)", "Median", "25th pct", "75th pct", "Best in sector", "Weakest in sector"])]]
    best_w = {}
    for col, label, dec, suf, hb in spec:
        v = d[col].astype(float) if col in d else pd.Series(dtype=float)
        vv = v.dropna()
        if vv.empty:
            rows.append([Paragraph(label, S["c"])] + [Paragraph("n/a", S["cr"])] * 5)
            continue
        b = d.loc[vv.idxmax() if hb else vv.idxmin()]
        w = d.loc[vv.idxmin() if hb else vv.idxmax()]
        best_w[col] = (b.company_id, w.company_id)
        rows.append([Paragraph(label + (" (lower = better)" if not hb else ""), S["c"]),
                     Paragraph(f"<b>{fmt(vv.median(), dec, suf)}</b>", S["cr"]),
                     Paragraph(fmt(vv.quantile(.25), dec, suf), S["cr"]), Paragraph(fmt(vv.quantile(.75), dec, suf), S["cr"]),
                     Paragraph(f"{escape(b.company_id)} ({fmt(b[col], dec, suf)})", S["cr"]),
                     Paragraph(f"{escape(w.company_id)} ({fmt(w[col], dec, suf)})", S["cr"])])
    cw = [4.4 * cm, 2.2 * cm, 1.9 * cm, 1.9 * cm, 3.4 * cm, 3.4 * cm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C.NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C.LIGHT]),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9D9D9")),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    pat = d.pattern.value_counts()
    prow = [[Paragraph("Capital allocation pattern (latest FY)", S["chl"]), Paragraph("Companies", S["ch"])]] + [
        [Paragraph(escape(str(k)), S["c"]), Paragraph(str(v), S["cr"])] for k, v in pat.items()]
    pt = Table(prow, colWidths=[7.0 * cm, 2.2 * cm])
    pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C.NAVY), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9D9D9")),
                            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    med_roe = float(d.roe.median()) if d.roe.notna().any() else 0.0
    chart = img(roe_chart(d, med_roe, sector), 8.6 * cm)
    left = [Paragraph("Sector median KPIs", S["h2"]), t, Spacer(1, 8), Paragraph("Capital allocation mix", S["h2"]), pt]
    right = [chart]
    body = Table([[left, right]], colWidths=[UW - 9.0 * cm, 9.0 * cm])
    body.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    note = ("Financials (banks, NBFCs, insurers): ROCE, operating margin and D/E are structurally not comparable, so ROA, EPS CAGR and "
            "dividend payout replace them." if sector == "Financials" else
            "CFO quality = 5-year average CFO / net profit (years with profit > 0). Medians are computed across companies in this sector using the latest annual year.")
    sub = f"{n} companies  |  {d.sub_sector.nunique()} sub-sectors  |  Generated {C.RUN_DATE}"
    p1 = [hdr(f"Sector Report: {sector}", sub), Spacer(1, 10), body, Spacer(1, 6), Paragraph(note, S["note"])]
    # ---- company table ----
    cols = ["Company", "Sub-sector"] + [m[1] for m in spec] + ["Capital allocation"]
    trs = [[Paragraph(c, S["chl"] if i < 2 else S["ch"]) for i, c in enumerate(cols)]]
    styl = [("BACKGROUND", (0, 0), (-1, 0), C.NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FB")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9D9D9")), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    for ri, (_, r) in enumerate(d.iterrows(), start=1):
        row = [Paragraph(f"<b>{escape(r.company_id)}</b><br/>{escape(str(r['name']))}", S["c"]), Paragraph(escape(str(r.sub_sector)), S["c"])]
        for ci_, (col, label, dec, suf, hb) in enumerate(spec, start=2):
            val = r.get(col)
            row.append(Paragraph(fmt(val, dec, suf), S["cr"]))
            if col in best_w:
                if r.company_id == best_w[col][0] and n > 2:
                    styl.append(("BACKGROUND", (ci_, ri), (ci_, ri), colors.HexColor("#C6E0B4")))
                elif r.company_id == best_w[col][1] and n > 2:
                    styl.append(("BACKGROUND", (ci_, ri), (ci_, ri), colors.HexColor("#F8CBAD")))
        row.append(Paragraph(escape(str(r.pattern)), S["c"]))
        trs.append(row)
    cwid = [5.2 * cm, 3.4 * cm] + [(UW - 5.2 * cm - 3.4 * cm - 3.3 * cm) / len(spec)] * len(spec) + [3.3 * cm]
    ct = Table(trs, colWidths=cwid, repeatRows=1)
    ct.setStyle(TableStyle(styl))
    p2 = [hdr(f"{sector}: all companies", "Latest annual KPIs. Green = best in sector, red = weakest in sector (per column)."), Spacer(1, 8), ct]
    story = [KeepInFrame(UW, fh, p1, mode="shrink"), PageBreak()] + p2
    doc.build(story)
    return n


def run() -> list[str]:
    """Generate one PDF per broad sector."""
    data = C.load_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for sector in sorted(data.sectors.broad_sector.unique()):
        fn = f"{sector.replace(' ', '_')}_report_{C.FILE_DATE}.pdf"
        build(data, sector, OUT_DIR / fn)
        made.append(fn)
    return made


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    m = run()
    print(len(m), "sector reports:", *m, sep="\n  ")
