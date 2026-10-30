# Sprint 3 retrospective — Screener & Peer Engine

## Delivered
- `src/screener/engine.py`, `config/screener_config.yaml` — 15 filterable metrics, 6 presets, composite score (universe + sector-relative)
- `src/analytics/peer.py` — PERCENT_RANK for 10 metrics × 11 groups → `peer_percentiles` (560 rows, `data/nifty100.db`)
- `src/analytics/radar.py` — 92 PNGs (56 peer radars, 36 standalone composite-vs-Nifty-100 charts)
- `output/screener_output.xlsx` (6 sheets), `output/peer_comparison.xlsx` (11 sheets)
- `src/dq/rules.py` + `tests/` — 14 DQ rule unit tests, 36 passed / 1 expected-fail

## Preset counts
quality_compounder 17 · value_pick **2** · growth_accelerator 9 · dividend_champion 30 · debt_free_blue_chip 12 · turnaround_watch 25

## Issues / decisions needing sign-off
1. **Value Pick returns 2 (< 5).** P/E<20 and P/B<3 jointly match only M&M and MOTHERSON; market_cap.xlsx multiples are simulated and uncorrelated with fundamentals. Even P/E<30, P/B<5 gives 4. Thresholds left as specified.
2. **Debt-Free Blue Chip**: spec `D/E = 0` matched 0 companies (only LICI, SBILIFE, JIOFIN have zero borrowings; all Financials, excluded by the D/E rule). Config uses D/E <= 0.05 → 12 companies.
3. **D/E on Financials**: "skip" implemented as *exclude from results* (`de_financials_policy: exclude`; `exempt` is one config line away).
4. **Balance-sheet unit anomalies** — BEL, HAL, INDIGO, LT, PNB (+HDFCLIFE, HEROMOTOCO, HINDALCO, ICICIGI, ICICIPRULI, NESTLEIND flagged by the same rule): ROE/ROCE computed from P&L÷BS gave 100–4,700 %. ROE/ROCE for these come from companies.xlsx, asset turnover is blank. SBIN has no balance sheet at all.
5. `financial_ratios.xlsx` was **not** used: it contains duplicate rows and values like OPM 47,971 %. KPIs are recomputed from the cleaned raw statements (formulas from the project doc §13).
6. Leverage score uses the doc's D/E and ICR bands (§25.1) rather than P10/P90 winsorisation; all other metrics are winsorised. D/E and ICR are "not applicable" for Financials; remaining weights are renormalised.
7. Non-12-month periods (HCLTECH/SHREECEM 9m, AMBUJACEM 15m), TTM and Sep-2024 interim balance sheets are dropped; 8 orphan tickers (WIPRO, VEDL, …) rejected.
8. The 14 DQ tests = DQ-01…12, 14, 16. DQ-13 (needs HTTP) and DQ-15 (info counter) excluded.
9. **Cash-flow data defect (found in Sprint 4):** ABB's cash-flow rows are a verbatim copy of ADANIENSOL's (CFO 6,038 Cr vs ABB revenue 5,849 Cr). The loader now drops a duplicated series from the ticker where it is least plausible; ABB has no cash-flow data. Turnaround Watch moved 26 -> 25 as a result.
