# Nifty 100 Financial Intelligence Platform - Sprint 5 (Days 29-35)

Run everything: `PYTHONPATH=. python3 run_sprint5.py` (or `make report`), tests: `make test`.
Requires pandas, openpyxl, reportlab, matplotlib, pdfplumber, pypdf.

## Layout
- `src/etl/clean.py` - loader (header=1), ticker/year normalisation, orphan rejection, de-duplication, DQ log
- `src/analytics/ratios.py` - KPI panel, CAGR with edge-case flags, 8-pattern capital allocation
- `src/analytics/cashflow_kpis.py` - Day 31-32 cash-flow intelligence
- `src/nlp/parser.py`, `src/nlp/pros_cons_generator.py` - Day 29-30
- `src/reports/tearsheet.py`, `sector_report.py`, `portfolio_report.py`, `qa.py` - Day 33-35
- `output/` CSV/XLSX deliverables, `reports/` PDFs

## Results
| Deliverable | Result |
|---|---|
| analysis_parsed.csv | 52 numeric entries parsed; 28 logged to parse_failures.csv (16 orphan WIPRO rows, 12 TTM/Last Year labels) |
| cross_validation.csv | 23 of 24 sales/profit CAGRs agree with the Ratio Engine within 1.4 pp; **INFY 3-yr sales growth (text 5% vs computed 15.2%) flagged for manual review** |
| pros_cons_generated.csv | 451 rows, all 92 companies have >=1 pro and >=1 con, all confidence >60 (387 rule-based, 64 sector-relative fallbacks) |
| cashflow_intelligence.xlsx | 92 rows, all required columns + notes, plus distribution / changes / distress sheets |
| distress_alerts.csv | 13 companies (9 are financial lenders - flagged as structural in the `context` column) |
| pattern_changes.csv | 413 year-over-year pattern transitions |
| tearsheets | 91 PDFs (92 minus JIOFIN, only 2 years of data -> output/skipped_tearsheets.csv); all 2 pages, 166-230 KB, automated QA clean |
| sector reports | 10 PDFs (see deviation 1) |
| portfolio summary | 92 pages, alphabetical |

## Deviations from the sprint plan (please review)
1. **10 sector PDFs, not 11.** sectors.xlsx contains only 10 distinct `broad_sector` values (the spec's 11th, "Conglomerates", is mapped inside Industrials).
2. **Pro Rule 11 contradiction.** Heading says "Revenue CAGR > PAT CAGR" but its text says revenue grows *slower* than profit. I implemented the text's meaning (PAT CAGR exceeds revenue CAGR by >=2 pp); otherwise the sentence would be false.
3. **Pro Rule 3 (D/E = 0)** fired for no company: only 3 companies report zero borrowings in the latest year and none qualifies after the financial-sector carve-out. Pro Rule 7 (ICR>10 or debt-free) covers the strong-balance-sheet cases.
4. **Financials carve-out.** Leverage, ICR, OPM, ROCE and FCF rules are not applied to banks/NBFCs/insurers (their balance sheets and cash flows are structurally different; source OPM is also corrupt for banks, e.g. -57,587%). Tearsheets/sector reports show ROA/EPS CAGR instead.
5. **Pro Rule 8 uses simulated data** (market_cap.xlsx dividend yield) so 15 points of confidence are deducted.
6. **Confidence scoring**: 65 + 30 x signal strength, minus penalties (<5 yrs history -10, simulated source -15); include only if >60.
7. **Fallback observations** (rule ids `P-REL/C-REL/P-YOY/C-YOY/P-BEST/C-BEST`) are factual sector-relative or year-over-year statements, used only when no rule fires for a side, to satisfy the "at least 1 pro and 1 con" gate. Evidence is in `pros_cons_evidence.csv`.
8. **Capital allocation labels**: the spec lists two patterns for (+,-,-). I use the 8 sign combinations: Reinvestor (+,-,-), Aggressive Expander (+,-,+), Shareholder Returns (+,+,-), Cash Accumulator (+,+,+), Distress Signal (-,-,+), Distress - Asset Liquidation (-,+,+), Cash Burn - Divestment Funded (-,+,-), Cash Drain (-,-,-).
9. Sprint 1-2 artefacts (SQLite DB, financial_ratios, capital_allocation.csv) were not supplied, so a minimal ETL + ratio engine was rebuilt from the raw files.

## Source-data issues found and handled (output/validation_failures.csv)
- 8 tickers in P&L/BS/CF are not in companies.xlsx (VEDL, UNIONBANK, UNITDSPR, VBL, ULTRACEMCO, ZOMATO, WIPRO, ZYDUSLIFE): rejected as orphans.
- 87 duplicate balance-sheet rows, 12 P&L duplicates, and 34 cash-flow duplicate keys with **conflicting values** (e.g. ABB's second block is ~10x the scale of its P&L); lowest-id row kept, others logged.
- TTM rows excluded from annual series; Sep-2024 half-year balance sheets excluded; 3 non-12-month period labels kept with a warning.
- ATGL has no cash-flow statement; SBIN has no balance sheet; JIOFIN has 2 annual years.
- Data is used as supplied; market_cap and stock_prices are simulated and only used for the Pro 8 dividend-yield rule.
