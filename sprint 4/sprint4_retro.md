# Sprint 4 retrospective — Dashboard & Valuation

## Delivered
- 8-screen Streamlit app (`src/dashboard/app.py`, `pages/01…08`), cached loaders (`utils/db.py`, `@st.cache_data(ttl=600)` on every query)
- `src/analytics/valuation.py`, `output/valuation_summary.xlsx` (92 rows, 10 required columns), `output/valuation_flags.csv` (44 rows: 14 Caution, 30 Discount; 48 Fair)
- `data/nifty100.db` (SQLite) built by `src/data/build_db.py`; README with run steps and screen descriptions; screenshots in `docs/screenshots/`

## Exit criteria
| Criterion | Result |
|---|---|
| All 8 screens load for all 92 tickers | Pass — automated sweep of Profile, Trends, Reports over 92 tickers; Peers over every group × company; Home over 6 years; Sectors over all sectors; 0 exceptions |
| Profile < 3 s | **Mostly** — browser, 5 tickers: 1.7–2.6 s warm; the very first page load after server start took 3.6 s (library/Plotly bundle load). Cached loads of the same company are faster still |
| Screener CSV valid with correct headers | Pass (round-trip test) |
| valuation_summary.xlsx 92 rows, all columns | Pass |
| Team-lead demo / sign-off | Not done (needs a person) |

## UX decisions
- App uses `st.navigation`, so the sidebar shows exactly the 8 screens.
- Screener sliders start at their "no filter" end; a filter applies only once a slider is moved. Presets fill the sliders and keep any rule the 10 sliders cannot express (payout, sales, 3-yr CAGR, FCF-positive, D/E-declining) as visible "extra preset rules"; moving a slider drops them. Counts match the Sprint 3 engine within ±1 (>= vs > on slider boundaries).
- Capital treemap: Plotly treemaps cannot send click events to Streamlit, so click-to-drill works inside the chart and a pattern selector drives the company table.
- Home shows **10** sectors, not 11 — sectors.xlsx contains 10 broad sectors.
- Debt-free = D/E ≤ 0.05 excluding Financials (consistent with the Debt-Free Blue Chip preset).

## Data edge cases found
- ABB cash flow copied from ADANIENSOL (see Sprint 3 note 9) → ABB shows N/A cash-flow metrics, "Unclassified" in the capital map.
- Companies with unusable balance sheets (BEL, HAL, INDIGO, LT, PNB, SBIN, …): ROE/ROCE history is N/A; only latest source ROE/ROCE shown.
- Banks' D/E, ICR and FCF are not meaningful; D/E filters exclude Financials.
- Valuation multiples in market_cap.xlsx are simulated (e.g. TRENT P/E 8.7), so Caution/Discount flags are only as good as that data. Sector medians for 2-company sectors (Communication Services, Real Estate) are weak benchmarks.
- Annual-report links: bseindia.com is not reachable from this build environment, so live 404 detection could not be exercised end-to-end (statuses show "Not verified"); the logic is in place and the 52 empty URLs show "Report unavailable".

## Performance
Cold first load ≈ 3.6 s, subsequent profile loads ≈ 2 s; all DB reads cached for 10 min.
