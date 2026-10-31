"""Screener-screen logic kept free of Streamlit so it can be unit-tested."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.screener.engine import apply_filters, load_config

# key, label, column, op, min, max, step, default(= "filter off"), number format
SLIDERS = [
    dict(key="roe", label="ROE min (%)", op=">=", lo=-20.0, hi=100.0, step=1.0, default=-20.0, fmt="%.0f"),
    dict(key="de", label="D/E max", op="<=", lo=0.0, hi=15.0, step=0.05, default=15.0, fmt="%.2f"),
    dict(key="fcf", label="FCF min (₹ Cr)", op=">=", lo=-100000.0, hi=50000.0, step=500.0, default=-100000.0, fmt="%.0f"),
    dict(key="rev_cagr_5y", label="Revenue CAGR 5yr min (%)", op=">=", lo=-10.0, hi=40.0, step=1.0, default=-10.0, fmt="%.0f"),
    dict(key="pat_cagr_5y", label="PAT CAGR 5yr min (%)", op=">=", lo=-30.0, hi=130.0, step=1.0, default=-30.0, fmt="%.0f"),
    dict(key="opm", label="OPM min (%)", op=">=", lo=-20.0, hi=100.0, step=1.0, default=-20.0, fmt="%.0f"),
    dict(key="pe", label="P/E max", op="<=", lo=0.0, hi=80.0, step=0.5, default=80.0, fmt="%.1f"),
    dict(key="pb", label="P/B max", op="<=", lo=0.0, hi=15.0, step=0.1, default=15.0, fmt="%.1f"),
    dict(key="div_yield", label="Dividend yield min (%)", op=">=", lo=0.0, hi=5.0, step=0.1, default=0.0, fmt="%.1f"),
    dict(key="icr", label="Interest coverage min (x)", op=">=", lo=0.0, hi=100.0, step=1.0, default=0.0, fmt="%.0f"),
]
SLIDER_BY_KEY = {s["key"]: s for s in SLIDERS}
PRESET_BUTTONS = [("Quality", "quality_compounder"), ("Value", "value_pick"), ("Growth", "growth_accelerator"),
                  ("Dividend", "dividend_champion"), ("Debt-Free", "debt_free_blue_chip"),
                  ("Turnaround", "turnaround_watch")]
LABELS = {
    "roe": "ROE %", "de": "D/E", "fcf": "FCF (Cr)", "rev_cagr_5y": "Revenue CAGR 5y %", "pat_cagr_5y": "PAT CAGR 5y %",
    "opm": "OPM %", "pe": "P/E (SIMULATED)", "pb": "P/B (SIMULATED)", "div_yield": "Div. yield % (SIMULATED)", "icr": "Interest coverage (x)",
    "rev_cagr_3y": "Revenue CAGR 3y %", "dividend_payout": "Payout %", "sales": "Sales (Cr)",
    "fcf_positive": "FCF positive", "de_declining": "D/E declining",
}


def slider_defaults() -> dict[str, float]:
    return {s["key"]: s["default"] for s in SLIDERS}


def preset_to_state(preset_key: str, cfg: dict | None = None) -> tuple[dict[str, float], list[dict]]:
    """Slider values for a preset plus the preset filters the 10 sliders cannot express."""
    cfg = cfg or load_config()
    vals, extras = slider_defaults(), []
    for f in cfg["presets"][preset_key]["filters"]:
        if f["metric"] in SLIDER_BY_KEY and f.get("op") in (">", ">=", "<", "<=", "=="):
            vals[f["metric"]] = float(f["value"])
        else:
            extras.append(f)
    return vals, extras


def build_filters(values: dict[str, float], extras: list[dict] | None = None) -> list[dict]:
    """A slider is active only when moved off its permissive default."""
    out = []
    for s in SLIDERS:
        v = values.get(s["key"], s["default"])
        if v != s["default"]:
            out.append({"metric": s["key"], "op": s["op"], "value": float(v)})
    return out + list(extras or [])


def run(snapshot: pd.DataFrame, values: dict[str, float], extras: list[dict] | None = None,
        cfg: dict | None = None) -> tuple[pd.DataFrame, list[dict]]:
    cfg = cfg or load_config()
    filters = build_filters(values, extras)
    res = apply_filters(snapshot, filters, cfg) if filters else snapshot
    res = res.sort_values("composite_quality_score", ascending=False, na_position="last")
    return res, filters


def view_frame(res: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    """Visible table: ticker, name, sector, composite score + every filtered metric (or a default trio)."""
    metrics = [f["metric"] for f in filters if f["metric"] in res.columns]
    metrics = list(dict.fromkeys(metrics)) or ["roe", "de", "pe"]
    out = res[["company_id", "company_name", "broad_sector", "composite_quality_score"] + metrics].copy()
    out.columns = ["Ticker", "Company", "Sector", "Composite score"] + [LABELS.get(m, m) for m in metrics]
    for c in out.columns[3:]:
        if out[c].dtype == object or out[c].dtype == bool:
            continue
        out[c] = pd.to_numeric(out[c], errors="coerce").round(2)
    for m in metrics:                      # negative / non-positive CAGR base -> TURNAROUND, not a number
        fc = f"{m}_flag"
        if m.endswith(("cagr_3y", "cagr_5y")) and fc in res.columns:
            out[LABELS.get(m, m)] = out[LABELS.get(m, m)].astype(object).where(
                res[fc].reset_index(drop=True) != "Turnaround", "TURNAROUND")
    if "Interest coverage (x)" in out:
        out["Interest coverage (x)"] = out["Interest coverage (x)"].map(
            lambda v: "Debt Free" if (not pd.isna(v) and np.isinf(v)) else v)
    return out.reset_index(drop=True)


def to_csv_bytes(view: pd.DataFrame) -> bytes:
    return view.fillna("N/A").to_csv(index=False).encode("utf-8")
