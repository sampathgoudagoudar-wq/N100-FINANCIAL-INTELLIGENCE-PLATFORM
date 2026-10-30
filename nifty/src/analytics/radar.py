"""Radar (polar) charts: company vs peer-group average on 8 axes, all scaled 0-100.

Axes: ROE, ROCE, NPM, D/E, FCF score, PAT CAGR 5yr, Revenue CAGR 5yr, Composite score.
Every axis uses the composite-score scale (P10/P90 winsorised, 0-100) so that "outer = better"
on every spoke; the D/E spoke is the leverage score (low debt = outer edge).
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.screener.engine import component_scores

AXES = [("roe", "ROE"), ("roce", "ROCE"), ("npm", "NPM"), ("de", "D/E\n(low = outer)"),
        ("score_fcf", "FCF score"), ("pat_cagr_5y", "PAT CAGR\n5yr"), ("rev_cagr_5y", "Revenue\nCAGR 5yr"),
        ("composite_quality_score", "Composite\nscore")]
TEAL, AMBER, INK = "#0F7B6C", "#D9822B", "#0B2239"


def axis_scores(scored: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """0-100 value per company for each of the 8 radar axes."""
    comp = component_scores(scored, cfg)
    out = pd.DataFrame({"company_id": scored["company_id"].values})
    for key, _ in AXES:
        if key in comp.columns:
            out[key] = comp[key].values
        else:
            out[key] = scored[key].values
    return out.set_index("company_id")


def safe_name(company_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", company_id)


def _radar(company: pd.Series, peer_avg: pd.Series, title: str, subtitle: str, path: Path) -> None:
    labels = [lab + ("\n(n/a)" if pd.isna(company[k]) else "") for k, lab in AXES]
    n = len(AXES)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ang_c = np.append(ang, ang[0])
    comp_v = np.append(company[[k for k, _ in AXES]].fillna(0).to_numpy(float), company[AXES[0][0]] if not pd.isna(company[AXES[0][0]]) else 0)
    peer_v = peer_avg[[k for k, _ in AXES]].fillna(0).to_numpy(float)
    peer_v = np.append(peer_v, peer_v[0])

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"projection": "polar"}, dpi=130)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="#666666")
    ax.set_xticks(ang)
    ax.set_xticklabels(labels, fontsize=11, color=INK)
    ax.tick_params(axis="x", pad=12)
    ax.grid(color="#D0D7DE", linewidth=0.8)
    ax.spines["polar"].set_color("#D0D7DE")

    ax.plot(ang_c, comp_v, color=TEAL, linewidth=2.2, label=company.name)
    ax.fill(ang_c, comp_v, color=TEAL, alpha=0.28)
    ax.plot(ang_c, peer_v, color=AMBER, linewidth=2, linestyle="--", label="Peer group average")
    fig.suptitle(title, fontsize=15, fontweight="bold", color=INK, y=0.97)
    fig.text(0.5, 0.915, subtitle, ha="center", fontsize=10, color="#555555")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=False, fontsize=11)
    fig.subplots_adjust(top=0.82, bottom=0.12)
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def _standalone(row: pd.Series, universe_avg: float, rank: int, n: int, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
    names = [row["company_name"][:28], "Nifty 100 average"]
    vals = [row["composite_quality_score"], universe_avg]
    bars = ax.barh(names, vals, color=[TEAL, AMBER], height=0.5)
    ax.set_xlim(0, 100)
    ax.invert_yaxis()
    for b, v in zip(bars, vals):
        ax.text(v + 1.5, b.get_y() + b.get_height() / 2, f"{v:.1f}", va="center", fontsize=12, color=INK)
    ax.set_xlabel("Composite quality score (0-100)", fontsize=11)
    ax.tick_params(labelsize=11)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.suptitle(f"{row['company_id']} — no peer group assigned", fontsize=14, fontweight="bold", color=INK)
    ax.set_title(f"Rank {rank} of {n} in the Nifty 100 universe", fontsize=10, color="#555555")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def generate_radar_charts(scored: pd.DataFrame, peer_groups: pd.DataFrame, out_dir: str | Path,
                          cfg: dict | None = None) -> dict[str, int]:
    """One PNG per company: <company_id>_radar.png. Returns counts."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ax_scores = axis_scores(scored, cfg)
    grp_of = peer_groups.set_index("company_id")["peer_group_name"]
    members = peer_groups.groupby("peer_group_name")["company_id"].apply(list)
    meta = scored.set_index("company_id")
    n_radar = n_stand = 0
    universe_avg = float(scored["composite_quality_score"].mean())
    ranks = scored["composite_quality_score"].rank(ascending=False, method="min")
    ranks.index = scored["company_id"]

    for cid in scored["company_id"]:
        path = out_dir / f"{safe_name(cid)}_radar.png"
        if cid in grp_of.index:
            g = grp_of[cid]
            peer_avg = ax_scores.loc[[m for m in members[g] if m in ax_scores.index]].mean()
            row = ax_scores.loc[cid].copy()
            row.name = cid
            _radar(row, peer_avg, f"{meta.loc[cid, 'company_name']}", f"vs {g} peer average", path)
            n_radar += 1
        else:
            r = meta.loc[cid].copy()
            r["company_id"] = cid
            _standalone(r, universe_avg, int(ranks[cid]), len(scored), path)
            n_stand += 1
    return {"radar": n_radar, "standalone": n_stand}
