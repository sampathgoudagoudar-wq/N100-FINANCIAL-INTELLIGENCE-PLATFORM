"""Screener filter engine + composite quality score.

* thresholds live in config/screener_config.yaml (analyst-editable)
* 15 filterable metrics, 6 presets, free-form custom filters
* composite_quality_score (0-100) with P10/P90 winsorisation, universe- and sector-relative
"""
from __future__ import annotations

import operator
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "screener_config.yaml"
_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}
_DE_METRICS = {"de", "de_declining"}


# ────────────────────────────────── config ──────────────────────────────────
def load_config(path: str | Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _column(metric: str, cfg: dict) -> str:
    spec = cfg.get("filterable_metrics", {}).get(metric)
    return spec["column"] if spec else metric


# ────────────────────────────────── filters ─────────────────────────────────
def _condition(df: pd.DataFrame, flt: dict, cfg: dict) -> pd.Series:
    """Boolean mask for one filter. Missing values never pass."""
    metric, op = flt["metric"], flt["op"]
    col = _column(metric, cfg)
    if col not in df.columns:
        raise KeyError(f"Unknown screener metric '{metric}' (column '{col}' not in data)")
    if op == "is_true":
        return df[col].fillna(False).astype(bool)
    if op not in _OPS:
        raise ValueError(f"Unsupported operator '{op}' for metric '{metric}'")
    values = pd.to_numeric(df[col], errors="coerce")
    if col == "icr" and cfg.get("icr_debt_free_is_infinite", True):
        # 'Debt Free' companies carry ICR = +inf, so they pass every ICR minimum
        values = values.where(df.get("icr_label", "") != "Debt Free", np.inf)
    return _OPS[op](values, flt["value"]).fillna(False)


def apply_filters(df: pd.DataFrame, filters: list[dict], cfg: dict | None = None) -> pd.DataFrame:
    """Apply a list of {metric, op, value} filters (logical AND).

    D/E rule: while any D/E-type filter is active, companies in `de_exempt_sectors`
    (Financials) are skipped — excluded from the result by default, or only exempted from
    the D/E test when `de_financials_policy: exempt`.
    """
    cfg = cfg or load_config()
    mask = pd.Series(True, index=df.index)
    exempt = df["broad_sector"].isin(cfg.get("de_exempt_sectors", []))
    policy = cfg.get("de_financials_policy", "exclude")
    de_active = any(f["metric"] in _DE_METRICS for f in filters)

    if de_active and policy == "exclude":
        mask &= ~exempt
    for flt in filters:
        cond = _condition(df, flt, cfg)
        if flt["metric"] in _DE_METRICS and policy == "exempt":
            cond = cond | exempt
        mask &= cond
    return df[mask]


def custom_filters(**thresholds) -> list[dict]:
    """Translate shorthand such as roe_min=15, de_max=1 into filter dicts (>= / <=)."""
    out = []
    for key, value in thresholds.items():
        if key.endswith("_min"):
            op, metric = ">=", key[:-4]
        elif key.endswith("_max"):
            op, metric = "<=", key[:-4]
        else:
            raise ValueError(f"'{key}' must end in _min or _max")
        out.append({"metric": metric, "op": op, "value": value})
    return out


# ──────────────────────────── composite quality score ───────────────────────
def _winsor_scale(x: pd.Series, lo_pct: float, hi_pct: float, ref: pd.Series | None = None) -> pd.Series:
    """Clip at the P10/P90 of `ref` (default: x itself) and scale to 0-100."""
    ref = x if ref is None else ref
    ref = ref[np.isfinite(ref)]
    if len(ref) < 2:
        return pd.Series(np.nan, index=x.index)
    lo, hi = np.percentile(ref, [lo_pct, hi_pct])
    if hi == lo:
        return pd.Series(50.0, index=x.index).where(x.notna())
    return ((x.clip(lo, hi) - lo) / (hi - lo) * 100)


def _component_scores(df: pd.DataFrame, cfg: dict, group_by: str | None) -> pd.DataFrame:
    sc = cfg["composite_score"]
    lo, hi = sc["winsor_low_pct"], sc["winsor_high_pct"]
    na_fin = df["broad_sector"].isin(cfg.get("de_exempt_sectors", []))
    out = pd.DataFrame(index=df.index)

    for comp in sc["components"]:
        m, method = comp["metric"], comp["method"]
        x = pd.to_numeric(df[m], errors="coerce") if m in df else pd.Series(np.nan, index=df.index)
        if method == "flag":
            s = df[m].map({True: 100.0, False: 0.0})
        elif method in ("de_curve", "icr_curve"):
            curve = sc[method]
            s = pd.Series(np.interp(x.clip(upper=1e6), curve["x"], curve["y"]), index=df.index).where(x.notna())
            if method == "de_curve":
                s = s.mask(x > curve["x"][-1], 0.0)          # D/E > 5 -> 0
            if method == "icr_curve":
                s = s.mask(np.isinf(x), 100.0)                # Debt Free -> 100
            s = s.mask(na_fin)                                # leverage not applicable to financials
        else:
            if group_by is None:
                s = _winsor_scale(x.replace([np.inf, -np.inf], np.nan), lo, hi)
            else:
                s = pd.Series(np.nan, index=df.index)
                universe = _winsor_scale(x, lo, hi)
                for _, idx in df.groupby(group_by).groups.items():
                    sub = x.loc[idx]
                    if sub.notna().sum() >= sc["sector_min_companies"]:
                        s.loc[idx] = _winsor_scale(sub, lo, hi)
                    else:
                        s.loc[idx] = universe.loc[idx]       # tiny sector: universe scale
            # CAGR with an undefined (turnaround / negative) end-point scores 0, not "missing"
            flag_col = f"{m}_flag"
            if flag_col in df:
                s = s.mask(df[flag_col] == "Turnaround", 0.0)
        out[m] = s
    return out


def component_scores(df: pd.DataFrame, cfg: dict | None = None, by_sector: bool = False) -> pd.DataFrame:
    """Public wrapper: 0-100 score of every composite component (used by the radar charts)."""
    cfg = cfg or load_config()
    return _component_scores(df, cfg, "broad_sector" if by_sector else None)


def _weighted(scores: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    w = pd.Series(weights)
    avail = scores[w.index].notna()
    num = (scores[w.index].fillna(0) * w).sum(axis=1)
    den = (avail * w).sum(axis=1)
    return (num / den.where(den > 0))


def add_composite_score(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Add composite_quality_score (universe scaling), sector_relative_score (scaling inside
    each broad_sector), the four dimension scores and the sorted rank.

    Missing inputs (no history, not applicable to financials) are dropped and the remaining
    weights re-normalised; a score needs at least half of the total weight to be reported.
    """
    cfg = cfg or load_config()
    comps = cfg["composite_score"]["components"]
    weights = {c["metric"]: c["weight"] for c in comps}
    total_w = sum(weights.values())
    df = df.copy()

    uni = _component_scores(df, cfg, None)
    sec = _component_scores(df, cfg, "broad_sector")

    def overall(scores):
        s = _weighted(scores, weights)
        avail_w = (scores[list(weights)].notna() * pd.Series(weights)).sum(axis=1)
        return s.where(avail_w >= total_w / 2).round(2)

    df["composite_quality_score"] = overall(uni)
    df["sector_relative_score"] = overall(sec)
    for dim in dict.fromkeys(c["dim"] for c in comps):
        dw = {c["metric"]: c["weight"] for c in comps if c["dim"] == dim}
        df[f"score_{dim.lower().replace(' ', '_')}"] = _weighted(uni, dw).round(2)
    df["score_fcf"] = df["score_cash_quality"]               # alias used by the radar chart
    return df.sort_values("composite_quality_score", ascending=False, na_position="last").reset_index(drop=True)


# ───────────────────────────────── public API ───────────────────────────────
def run_screen(df: pd.DataFrame, filters: list[dict], cfg: dict | None = None) -> pd.DataFrame:
    """Filter, then return the survivors sorted by composite_quality_score (desc)."""
    cfg = cfg or load_config()
    if "composite_quality_score" not in df.columns:
        df = add_composite_score(df, cfg)
    res = apply_filters(df, filters, cfg)
    return res.sort_values("composite_quality_score", ascending=False, na_position="last").reset_index(drop=True)


def run_preset(df: pd.DataFrame, preset: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    if preset not in cfg["presets"]:
        raise KeyError(f"Unknown preset '{preset}'. Available: {', '.join(cfg['presets'])}")
    return run_screen(df, cfg["presets"][preset]["filters"], cfg)


def run_all_presets(df: pd.DataFrame, cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    cfg = cfg or load_config()
    scored = add_composite_score(df, cfg)
    return {name: run_screen(scored, p["filters"], cfg) for name, p in cfg["presets"].items()}
