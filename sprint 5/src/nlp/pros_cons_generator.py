"""Rule-based pros/cons generator: 12 pro rules + 12 con rules with confidence scores."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from src.analytics.ratios import build_panel, company_cagrs
from src.etl.clean import OUT, SUP

logger = logging.getLogger(__name__)
MIN_CONF = 60.0          # include only if confidence > 60
BASE_CONF = 65.0         # confidence of a rule that only just triggers
SPAN_CONF = 30.0         # extra confidence earned by signal strength (0..1)
SIM_PENALTY = 15.0       # source dataset is simulated
SPARSE_PENALTY = 10.0    # < 5 annual rows of history

PRO_TEXT = {
    "P1": "Consistently high return on equity above 20% demonstrates exceptional capital efficiency",
    "P2": "Strong free cash flow generation over 5 years signals healthy business fundamentals",
    "P3": "Debt-free balance sheet provides financial flexibility and eliminates interest burden",
    "P4": "Revenue growing at above 15% CAGR over 5 years reflects strong business momentum",
    "P5": "Operating profit margin above 25% indicates strong pricing power and cost discipline",
    "P6": "Net profit compounding at above 20% over 5 years creates significant shareholder value",
    "P7": "Very high interest coverage ratio reflects negligible financial stress from debt servicing",
    "P8": "Consistent dividend yield above 2% backed by positive free cash flow",
    "P9": "Earnings per share growing above 15% CAGR indicates strong earnings quality and compounding",
    "P10": "Return on equity improving for 3 consecutive years shows strengthening business quality",
    "P11": "Revenue growing slower than profits shows improving operating leverage and scale benefits",
    "P12": "Growing asset base funded by internal accruals reflects self-sustaining growth",
}
CON_TEXT = {
    "C1": "Debt-to-equity ratio of {x:.2f} is elevated for a non-financial company and warrants monitoring",
    "C2": "Free cash flow negative for 3 consecutive years raises concern about cash generation quality",
    "C3": "Operating margins declining for 3 consecutive years suggest pricing or cost pressure",
    "C4": "Company reported a net loss in the most recent financial year",
    "C5": "Revenue contraction over 2 consecutive years indicates demand weakness or market share loss",
    "C6": "Interest coverage ratio below 1.5x indicates the company is at risk of not meeting its debt obligations",
    "C7": "Dividend payout ratio above 100% means the company is paying dividends from reserves, which is unsustainable",
    "C8": "Rising debt-to-equity ratio over 3 years suggests increasing financial leverage risk",
    "C9": "Earnings per share declining for 3 consecutive years reflects deteriorating profitability",
    "C10": "Return on capital employed below 10% suggests the business is not generating sufficient returns on invested capital",
    "C11": "Net debt exceeding 3 times EBITDA is a high leverage ratio and limits financial flexibility",
    "C12": "Revenue growing at below 5% over 5 years lags inflation and suggests limited business momentum",
}


@dataclass
class Hit:
    rule: str
    strength: float          # 0..1
    evidence: str
    text: str | None = None
    penalty: float = 0.0


def clip01(x: float) -> float:
    """Clamp to [0, 1]."""
    return float(min(1.0, max(0.0, x)))


def trailing_run(vals: list[float], test: Callable[[float], bool]) -> int:
    """Length of the run of values at the end of the list for which test() is True."""
    n = 0
    for v in reversed(vals):
        if v is None or pd.isna(v) or not test(v):
            break
        n += 1
    return n


def strict_trend(vals: list[float], k: int, up: bool) -> bool:
    """True if the last k+1 values strictly increase (up) or decrease over k steps."""
    s = [v for v in vals]
    if len(s) < k + 1 or any(pd.isna(v) for v in s[-(k + 1):]):
        return False
    t = s[-(k + 1):]
    return all((t[i + 1] > t[i]) if up else (t[i + 1] < t[i]) for i in range(k))


def evaluate_company(g: pd.DataFrame, cg: pd.Series, div_yield: float | None) -> tuple[list[Hit], list[Hit]]:
    """Return (pro_hits, con_hits) for one company's annual panel g (sorted by year)."""
    g = g.sort_values("fy")
    last = g.iloc[-1]
    fin = bool(last.is_financial)
    pros: list[Hit] = []
    cons: list[Hit] = []
    sparse = SPARSE_PENALTY if len(g) < 5 else 0.0
    roe, fcf, opm, de = g.roe.tolist(), g.fcf.tolist(), g.opm.tolist(), g.de.tolist()
    eps, rev = g.eps.tolist(), g.sales.tolist()
    g_cg = lambda k: None if pd.isna(cg.get(k)) else float(cg[k])  # noqa: E731
    rev5, pat5, eps5 = g_cg("rev_cagr_5y"), g_cg("pat_cagr_5y"), g_cg("eps_cagr_5y")

    # ---------------- PRO RULES ----------------
    n = trailing_run(roe, lambda v: v > 20)
    if n >= 3:
        m = min(roe[-n:])
        pros.append(Hit("P1", 0.5 * clip01((n - 3) / 7) + 0.5 * clip01((m - 20) / 20),
                        f"ROE>20% for {n} straight yrs (min {m:.1f}%)", penalty=sparse))
    if not fin:
        n = trailing_run(fcf, lambda v: v > 0)
        if n >= 5:
            pros.append(Hit("P2", clip01((n - 5) / 5) * 0.5 + 0.5 * clip01(
                np.nanmin(fcf[-n:]) / max(1.0, abs(last.sales)) * 20), f"FCF positive {n} yrs", penalty=sparse))
        if last.borrowings == 0 and not pd.isna(last.borrowings):
            hist = [b for b in g.borrowings.tolist() if not pd.isna(b)]
            pros.append(Hit("P3", 0.6 + 0.4 * clip01(trailing_run(hist, lambda v: v == 0) / 5),
                            f"borrowings = 0 in {last.year}", penalty=sparse))
    if rev5 is not None and rev5 > 15:
        pros.append(Hit("P4", clip01((rev5 - 15) / 15), f"Revenue CAGR 5y {rev5:.1f}%", penalty=sparse))
    if not fin and not pd.isna(last.opm) and last.opm > 25:
        pros.append(Hit("P5", clip01((last.opm - 25) / 25), f"OPM {last.opm:.1f}% in {last.year}", penalty=sparse))
    if pat5 is not None and pat5 > 20:
        pros.append(Hit("P6", clip01((pat5 - 20) / 20), f"PAT CAGR 5y {pat5:.1f}%", penalty=sparse))
    if not fin and (last.debt_free or (not pd.isna(last.icr) and last.icr > 10)):
        s = 1.0 if last.debt_free else clip01((last.icr - 10) / 30)
        pros.append(Hit("P7", max(s, 0.5) if last.debt_free else s,
                        "debt free" if last.debt_free else f"ICR {last.icr:.1f}x", penalty=sparse))
    if (not fin and div_yield is not None and div_yield > 2 and not pd.isna(last.fcf) and last.fcf > 0):
        pros.append(Hit("P8", clip01((div_yield - 2) / 2.5), f"div yield {div_yield:.2f}% (simulated), FCF {last.fcf:.0f}",
                        penalty=sparse + SIM_PENALTY))
    if eps5 is not None and eps5 > 15:
        pros.append(Hit("P9", clip01((eps5 - 15) / 15), f"EPS CAGR 5y {eps5:.1f}%", penalty=sparse))
    if strict_trend(roe, 3, up=True):
        gain = roe[-1] - roe[-4]
        pros.append(Hit("P10", clip01(gain / 15), f"ROE {roe[-4]:.1f}%->{roe[-1]:.1f}% over 3 yrs", penalty=sparse))
    # NOTE: spec heading says 'Revenue CAGR > PAT CAGR' but its text says revenue grows SLOWER than profit.
    # We implement the text's meaning (PAT CAGR > Revenue CAGR), otherwise the sentence would be false.
    if rev5 is not None and pat5 is not None and rev5 > 0 and pat5 - rev5 >= 2:
        pros.append(Hit("P11", clip01((pat5 - rev5) / 15), f"PAT CAGR {pat5:.1f}% vs revenue CAGR {rev5:.1f}%",
                        penalty=sparse))
    if not fin and len(g) >= 4:
        a0, a1 = g.total_assets.iloc[-4], g.total_assets.iloc[-1]
        b0, b1 = g.borrowings.iloc[-4], g.borrowings.iloc[-1]
        if not any(pd.isna(x) for x in (a0, a1, b0, b1)) and a1 > a0 and b1 < b0 and b0 > 0:
            pros.append(Hit("P12", 0.5 * clip01((a1 / a0 - 1) / 0.5) + 0.5 * clip01((1 - b1 / b0) / 0.5),
                            f"assets {a0:.0f}->{a1:.0f}, borrowings {b0:.0f}->{b1:.0f}", penalty=sparse))

    # ---------------- CON RULES ----------------
    if not fin and not pd.isna(last.de) and last.de > 2.0:
        cons.append(Hit("C1", clip01((last.de - 2) / 4), f"D/E {last.de:.2f}", CON_TEXT["C1"].format(x=last.de), sparse))
    if not fin and trailing_run(fcf, lambda v: v < 0) >= 3:
        k = trailing_run(fcf, lambda v: v < 0)
        cons.append(Hit("C2", clip01((k - 3) / 4) * 0.5 + 0.5, f"FCF negative {k} yrs", penalty=sparse))
    if not fin and strict_trend(opm, 3, up=False):
        cons.append(Hit("C3", clip01((opm[-4] - opm[-1]) / 15), f"OPM {opm[-4]:.1f}%->{opm[-1]:.1f}%", penalty=sparse))
    if not pd.isna(last.net_profit) and last.net_profit < 0:
        cons.append(Hit("C4", 0.5 + 0.5 * clip01(abs(last.net_profit) / max(1.0, abs(last.sales)) * 5),
                        f"net profit {last.net_profit:.0f} in {last.year}", penalty=sparse))
    k = trailing_run(list(np.diff(rev)), lambda v: v < 0) if len(rev) > 2 else 0
    if k >= 2:
        drop = 1 - rev[-1] / rev[-1 - k]
        cons.append(Hit("C5", clip01(drop / 0.2) * 0.5 + clip01((k - 2) / 3) * 0.5,
                        f"revenue down {k} yrs ({drop*100:.1f}%)", penalty=sparse))
    if not fin and not pd.isna(last.icr) and last.interest > 0 and last.icr < 1.5:
        cons.append(Hit("C6", clip01((1.5 - last.icr) / 1.5), f"ICR {last.icr:.2f}x", penalty=sparse))
    pay = last.dividend_payout
    if not pd.isna(pay) and 100 < pay <= 200:          # >200 is a DQ-12 data-entry suspect
        cons.append(Hit("C7", clip01((pay - 100) / 100), f"payout {pay:.0f}%", penalty=sparse))
    if not fin and strict_trend(de, 3, up=True) and de[-1] > 0.1:
        cons.append(Hit("C8", clip01((de[-1] - de[-4]) / 1.5), f"D/E {de[-4]:.2f}->{de[-1]:.2f}", penalty=sparse))
    if strict_trend(eps, 3, up=False):
        cons.append(Hit("C9", clip01((eps[-4] - eps[-1]) / max(1.0, abs(eps[-4])) / 0.4),
                        f"EPS {eps[-4]:.0f}->{eps[-1]:.0f}", penalty=sparse))
    if not fin and not pd.isna(last.roce) and last.roce < 10:
        cons.append(Hit("C10", clip01((10 - last.roce) / 10), f"ROCE {last.roce:.1f}%", penalty=sparse))
    if not fin and not pd.isna(last.nd_ebitda) and last.nd_ebitda > 3:
        cons.append(Hit("C11", clip01((last.nd_ebitda - 3) / 5), f"net debt/EBITDA {last.nd_ebitda:.1f}x", penalty=sparse))
    if rev5 is not None and rev5 < 5:
        cons.append(Hit("C12", clip01((5 - rev5) / 8), f"Revenue CAGR 5y {rev5:.1f}%", penalty=sparse))
    return pros, cons


def confidence(h: Hit) -> float:
    """Map strength (0..1) and penalties to a 0-100 confidence score."""
    return round(min(100.0, max(0.0, BASE_CONF + SPAN_CONF * h.strength - h.penalty)), 1)


def sector_relative_fallback(latest: pd.DataFrame, panel: pd.DataFrame) -> dict[str, tuple[list, list]]:
    """Factual fallback observations, used only when no rule fires for a side.

    Tier 1: metric above/below the sector median. Tier 2: largest year-over-year move.
    Tier 3: strongest/weakest metric relative to sector peers (even if on the 'wrong' side of the median).
    """
    d = latest
    metrics = {"roe": "Return on equity", "npm": "Net profit margin", "rev_cagr_5y": "5-year revenue CAGR",
               "pat_cagr_5y": "5-year net profit CAGR", "roce": "Return on capital employed",
               "opm": "Operating profit margin"}
    fin_skip = {"roce", "opm"}
    med = {(sec, m): d[d.broad_sector == sec][m].median() for sec in d.broad_sector.dropna().unique() for m in metrics}
    out: dict[str, tuple[list, list]] = {}
    for _, r in d.iterrows():
        gaps = []
        for m, label in metrics.items():
            if m in fin_skip and r.is_financial:
                continue
            v, md = r.get(m), med.get((r.broad_sector, m))
            if pd.isna(v) or pd.isna(md):
                continue
            gaps.append((label, float(v), float(md), (float(v) - float(md)) / max(abs(float(md)), 1.0)))
        pros, cons = [], []
        if gaps:
            best, worst = max(gaps, key=lambda x: x[3]), min(gaps, key=lambda x: x[3])
            if best[3] > 0:
                pros.append(Hit("P-REL", clip01(best[3]) * 0.3, f"{best[0]} {best[1]:.1f}% vs sector median {best[2]:.1f}%",
                                f"{best[0]} of {best[1]:.1f}% is above the {r.broad_sector} sector median of {best[2]:.1f}%"))
            if worst[3] < 0:
                cons.append(Hit("C-REL", clip01(-worst[3]) * 0.3, f"{worst[0]} {worst[1]:.1f}% vs sector median {worst[2]:.1f}%",
                                f"{worst[0]} of {worst[1]:.1f}% is below the {r.broad_sector} sector median of {worst[2]:.1f}%"))
        # tier 2: year-over-year movement
        g = panel[panel.company_id == r.company_id].sort_values("fy")
        if len(g) >= 2:
            yo = []
            for m, label in (("roe", "Return on equity"), ("npm", "Net profit margin"), ("opm", "Operating profit margin")):
                if m == "opm" and r.is_financial:
                    continue
                a, b = g[m].iloc[-2], g[m].iloc[-1]
                if not (pd.isna(a) or pd.isna(b)):
                    yo.append((label, float(a), float(b), float(b) - float(a)))
            if yo:
                up, dn = max(yo, key=lambda x: x[3]), min(yo, key=lambda x: x[3])
                if up[3] > 0:
                    pros.append(Hit("P-YOY", clip01(up[3] / 10) * 0.3, f"{up[0]} {up[1]:.1f}%->{up[2]:.1f}%",
                                    f"{up[0]} improved from {up[1]:.1f}% to {up[2]:.1f}% in the latest financial year"))
                if dn[3] < 0:
                    cons.append(Hit("C-YOY", clip01(-dn[3] / 10) * 0.3, f"{dn[0]} {dn[1]:.1f}%->{dn[2]:.1f}%",
                                    f"{dn[0]} eased from {dn[1]:.1f}% to {dn[2]:.1f}% in the latest financial year"))
        # tier 3: relative best / weakest metric versus sector peers
        if gaps:
            best, worst = max(gaps, key=lambda x: x[3]), min(gaps, key=lambda x: x[3])
            pros.append(Hit("P-BEST", 0.0, f"{best[0]} {best[1]:.1f}% vs sector median {best[2]:.1f}%",
                            f"{best[0]} ({best[1]:.1f}%) is the strongest of its core metrics relative to {r.broad_sector} sector peers (median {best[2]:.1f}%)"))
            cons.append(Hit("C-BEST", 0.0, f"{worst[0]} {worst[1]:.1f}% vs sector median {worst[2]:.1f}%",
                            f"{worst[0]} ({worst[1]:.1f}%) is the weakest of its core metrics relative to {r.broad_sector} sector peers (median {worst[2]:.1f}%)"))
        out[r.company_id] = (pros, cons)
    return out


def run() -> pd.DataFrame:
    """Generate output/pros_cons_generated.csv (+ evidence file) for all companies."""
    p = build_panel()
    cg = company_cagrs(p).set_index("company_id")
    mc = pd.read_excel(SUP / "market_cap.xlsx")
    mc["company_id"] = mc.company_id.str.strip().str.upper()
    dy = mc.sort_values("year").groupby("company_id").tail(1).set_index("company_id").dividend_yield_pct
    cos = pd.read_excel(OUT.parent / "data/raw/companies.xlsx", header=1).id.str.strip().str.upper().tolist()
    latest = p.sort_values("fy").groupby("company_id").tail(1).merge(
        cg.reset_index()[["company_id", "rev_cagr_5y", "pat_cagr_5y"]], on="company_id", how="left")
    fb = sector_relative_fallback(latest, p)

    rows, ev = [], []
    for cid in cos:
        g = p[p.company_id == cid]
        pros, cons = evaluate_company(g, cg.loc[cid], dy.get(cid)) if len(g) else ([], [])
        for side, hits, texts in (("pro", pros, PRO_TEXT), ("con", cons, CON_TEXT)):
            kept = [h for h in hits if confidence(h) > MIN_CONF]
            if not kept:   # coverage guarantee: use factual sector-relative observation
                cand = [h for h in fb.get(cid, ([], []))[0 if side == "pro" else 1] if confidence(h) > MIN_CONF]
                kept = cand[:1]
            for h in kept:
                rows.append(dict(company_id=cid, type=side, rule_id=h.rule,
                                 text=h.text or texts[h.rule], confidence_pct=confidence(h)))
                ev.append(dict(company_id=cid, type=side, rule_id=h.rule, evidence=h.evidence))
    df = pd.DataFrame(rows).sort_values(["company_id", "type", "confidence_pct"], ascending=[True, False, False])
    df.to_csv(OUT / "pros_cons_generated.csv", index=False)
    pd.DataFrame(ev).to_csv(OUT / "pros_cons_evidence.csv", index=False)
    return df


def verify(df: pd.DataFrame, companies: list[str]) -> list[str]:
    """Return companies missing at least one pro or one con."""
    c = df.groupby(["company_id", "type"]).size().unstack(fill_value=0)
    c = c.reindex(companies, fill_value=0)
    for col in ("pro", "con"):
        if col not in c:
            c[col] = 0
    return list(c[(c.pro < 1) | (c.con < 1)].index)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = run()
    cos = pd.read_excel(OUT.parent / "data/raw/companies.xlsx", header=1).id.str.strip().str.upper().tolist()
    print(len(df), "rows;", df.company_id.nunique(), "companies; missing:", verify(df, cos))
    print(df.groupby(["type", "rule_id"]).size().unstack(0).fillna(0).astype(int))
    print(df.confidence_pct.describe())
