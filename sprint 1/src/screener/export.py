"""screener_output.xlsx — one sheet per preset, 20 KPI columns, green/red threshold colouring."""
from __future__ import annotations

import operator
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .engine import load_config

GREEN = PatternFill("solid", start_color="C6EFCE", end_color="C6EFCE")
RED = PatternFill("solid", start_color="FFC7CE", end_color="FFC7CE")
HEADER = PatternFill("solid", start_color="0B2239", end_color="0B2239")
_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}

# (column, header, number format)  — the 20 KPI columns
KPI_COLUMNS = [
    ("roe", "ROE %", "0.0"), ("roce", "ROCE %", "0.0"), ("npm", "Net margin %", "0.0"),
    ("opm", "Op. margin %", "0.0"), ("de", "Debt/Equity", "0.00"), ("icr", "Int. coverage (x)", "0.0"),
    ("fcf", "FCF (Cr)", "#,##0"), ("cfo_pat", "CFO / PAT", "0.00"),
    ("rev_cagr_5y", "Revenue CAGR 5y %", "0.0"), ("rev_cagr_3y", "Revenue CAGR 3y %", "0.0"),
    ("pat_cagr_5y", "PAT CAGR 5y %", "0.0"), ("eps_cagr_5y", "EPS CAGR 5y %", "0.0"),
    ("asset_turnover", "Asset turnover (x)", "0.00"), ("pe", "P/E", "0.0"), ("pb", "P/B", "0.00"),
    ("div_yield", "Div. yield %", "0.00"), ("dividend_payout", "Payout %", "0"),
    ("sales", "Sales (Cr)", "#,##0"), ("net_profit", "Net profit (Cr)", "#,##0"),
    ("market_cap", "Market cap (Cr)", "#,##0"),
]
_THIN = Side(style="thin", color="D0D7DE")


def _thresholds(preset: dict, cfg: dict) -> dict[str, tuple[str, float]]:
    """Preset thresholds win over generic benchmarks."""
    th = {k: (v["op"], v["value"]) for k, v in cfg["benchmarks"].items()}
    for f in preset["filters"]:
        if f["op"] in _OPS:
            col = cfg.get("filterable_metrics", {}).get(f["metric"], {}).get("column", f["metric"])
            th[col] = (f["op"], f["value"])
    return th


def _passes(value, op: str, thr: float):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return bool(_OPS[op](value, thr))


def write_screener_workbook(results: dict[str, pd.DataFrame], path: str | Path,
                            cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    wb = Workbook()
    wb.remove(wb.active)
    ident = ["Rank", "Company ID", "Company", "Sector", "FY", "Composite score", "Sector-relative score"]

    for key, df in results.items():
        preset = cfg["presets"][key]
        ws = wb.create_sheet(preset["label"][:31])
        th = _thresholds(preset, cfg)
        own_cols = {cfg.get("filterable_metrics", {}).get(f["metric"], {}).get("column", f["metric"])
                    for f in preset["filters"]}
        crit = "; ".join(
            f"{f['metric']} {f['op']} {f['value']}" if "value" in f else f"{f['metric']} = true"
            for f in preset["filters"])

        ws["A1"] = f"{preset['label']} — {len(df)} companies"
        ws["A1"].font = Font(bold=True, size=14, color="0B2239")
        ws["A2"] = f"Filters: {crit}.  Sorted by composite quality score (desc).  FY = latest annual period."
        ws["A3"] = ("Green = meets threshold, red = fails.  Preset-filter columns use the preset threshold "
                    "(bold header); other KPI columns use the benchmarks in screener_config.yaml; "
                    "no fill = no threshold / not available.")
        for c in ("A2", "A3"):
            ws[c].font = Font(italic=True, size=9, color="555555")

        header_row = 5
        headers = ident + [h for _, h, _ in KPI_COLUMNS]
        for j, h in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=j, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEADER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for j, (col, _, _) in enumerate(KPI_COLUMNS, len(ident) + 1):
            if col in own_cols:
                ws.cell(row=header_row, column=j).fill = PatternFill("solid", start_color="1F6F5C", end_color="1F6F5C")
        ws.row_dimensions[header_row].height = 32

        for i, (_, r) in enumerate(df.iterrows(), 1):
            row = header_row + i
            base = [i, r["company_id"], r["company_name"], r["broad_sector"],
                    int(r["fy"]) if pd.notna(r["fy"]) else None,
                    r["composite_quality_score"], r["sector_relative_score"]]
            for j, v in enumerate(base, 1):
                c = ws.cell(row=row, column=j, value=None if pd.isna(v) else v)
                c.border = Border(bottom=_THIN)
                if j in (6, 7):
                    c.number_format = "0.0"
            for j, (col, _, fmt) in enumerate(KPI_COLUMNS, len(ident) + 1):
                v = r.get(col)
                shown = "Debt Free" if col == "icr" and isinstance(v, float) and np.isinf(v) else v
                if isinstance(shown, float) and np.isnan(shown):
                    shown = None
                c = ws.cell(row=row, column=j, value=shown)
                c.number_format = fmt
                c.border = Border(bottom=_THIN)
                if col in th and shown is not None:
                    ok = _passes(np.inf if shown == "Debt Free" else shown, *th[col])
                    if ok is not None:
                        c.fill = GREEN if ok else RED

        widths = [6, 13, 32, 22, 7, 11, 12] + [11] * len(KPI_COLUMNS)
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = ws.cell(row=header_row + 1, column=4)
        if len(df):
            ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(headers))}{header_row + len(df)}"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
