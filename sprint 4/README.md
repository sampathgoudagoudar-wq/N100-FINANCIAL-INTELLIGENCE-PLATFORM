# Nifty 100 Financial Intelligence Platform

## Setup
```bash
pip install pandas numpy scipy openpyxl pyyaml matplotlib plotly streamlit requests pytest
```
Raw Excel files are read from `src/data/loader.py::DATA_DIR` (edit this path for your machine).

## Build data and reports
```bash
python run_sprint3.py     # screener_output.xlsx, peer_comparison.xlsx, 92 radar PNGs, peer_percentiles
python run_sprint4.py     # data/nifty100.db (dashboard store), valuation_summary.xlsx, valuation_flags.csv
python -m pytest tests -q # DQ rules, screener, peers, dashboard QA (≈90 s)
```

## Run the dashboard
```bash
streamlit run src/dashboard/app.py      # http://localhost:8501
```
Layout: wide, title "Nifty 100 Analytics", sidebar expanded. Thresholds for the screener live in `config/screener_config.yaml`.

## The 8 screens  (screenshots in `docs/screenshots/`)
| # | Screen | What it does |
|---|---|---|
| 1 | **Home** | 6 KPI tiles (avg ROE, median P/E, median D/E, companies, median revenue CAGR 5y, debt-free count), sector donut, top-5 composite scores. Sidebar year selector 2019–2024 re-computes everything. |
| 2 | **Company Profile** | Search box + autocomplete dropdown, company card, 6 KPI tiles, revenue/net-profit bars, ROE/ROCE dual-axis lines, green ✔ / red ✖ pros & cons. Unknown search → "Ticker not found — please try another". |
| 3 | **Screener** | 10 sidebar sliders, 6 preset buttons that auto-fill them (plus any extra preset rules the sliders can't express), live result table, count label, CSV download. |
| 4 | **Peer Comparison** | 11-group dropdown, Plotly Scatterpolar radar (company vs group average), side-by-side KPI table with the benchmark row highlighted, percentile ranks. |
| 5 | **Trend Analysis** | Up to 3 overlaid metrics (own axis each), 10-year lines with YoY % labels on every point. |
| 6 | **Sector Analysis** | Revenue × ROE bubble chart (size = market cap, colour = sub-sector), median-KPI bars vs Nifty 100, sector summary table. |
| 7 | **Capital Allocation** | Plotly treemap of companies grouped by CFO/CFI/CFF sign pattern; click to drill in, or pick a pattern for the company list. |
| 8 | **Annual Reports** | Report years with BSE PDF links; live HEAD check shows green *Available* / red *Report unavailable* (404). Needs internet access to bseindia.com; otherwise shows grey *Not verified*. |

## Layout
```
config/screener_config.yaml      analyst-editable thresholds, presets, score weights
src/data/        loader.py (cleaning), build_db.py (SQLite)
src/screener/    engine.py (filters + composite score), export.py
src/analytics/   metrics, peer, radar, peer_report, valuation, capital, proscons
src/dashboard/   app.py, pages/01_home.py … 08_reports.py, utils/db.py (cached loaders), utils/screen.py
output/          screener_output.xlsx, peer_comparison.xlsx, valuation_summary.xlsx, valuation_flags.csv
```
