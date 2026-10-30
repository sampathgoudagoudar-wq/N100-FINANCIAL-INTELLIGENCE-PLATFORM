"""Automated QA for generated PDFs: page count, size, blank pages, margin overflow, shrunk fonts."""
from __future__ import annotations

import sys
from pathlib import Path

import pdfplumber
import pandas as pd

MIN_KB = 30
LEFT, RIGHT = 2.2 * 28.3465 - 1, 595.28 - 2.2 * 28.3465 + 1      # tearsheet margins (pt)


def check_tearsheet(path: Path) -> dict:
    """Return QA metrics for one tearsheet PDF."""
    res = dict(file=path.name, kb=round(path.stat().st_size / 1024, 1), pages=0, blank_pages=0, overflow_words=0, min_font=99.0)
    with pdfplumber.open(path) as pdf:
        res["pages"] = len(pdf.pages)
        for pg in pdf.pages:
            words = pg.extract_words()
            if len(words) < 20 and not pg.images:
                res["blank_pages"] += 1
            res["overflow_words"] += sum(1 for w in words if w["x0"] < LEFT or w["x1"] > RIGHT)
            sizes = [c["size"] for c in pg.chars if c["text"].strip()]
            if sizes:
                res["min_font"] = min(res["min_font"], round(min(sizes), 2))
    res["ok"] = res["pages"] == 2 and res["kb"] >= MIN_KB and res["blank_pages"] == 0 and res["overflow_words"] == 0 and res["min_font"] >= 5.5
    return res


if __name__ == "__main__":
    d = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/tearsheets")
    df = pd.DataFrame([check_tearsheet(p) for p in sorted(d.glob("*_tearsheet.pdf"))])
    df.to_csv("output/tearsheet_qa.csv", index=False)
    print(len(df), "files | all ok:", bool(df.ok.all()), "| failing:", df[~df.ok].file.tolist())
    print(df[["kb", "pages", "blank_pages", "overflow_words", "min_font"]].describe().loc[["min", "max"]])
