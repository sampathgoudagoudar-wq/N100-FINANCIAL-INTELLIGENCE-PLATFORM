# Sprint 2 notes: formula decisions and edge-case resolutions

## Decisions made where the spec was silent or inconsistent
1. **Table layout.** The supplied `financial_ratios.xlsx` is kept as `financial_ratios_source` (cross-checks only). `financial_ratios` is rebuilt by the engine for every (company, year) present in P&L, balance sheet or cash flow = 1,155 rows. 82 are 2024-09 balance-sheet-only rows (only BS ratios populated).
2. **KPI count.** Day 08-11 define ~40 computed columns (profitability, leverage, cash-flow, per-share, 9 CAGRs + 9 flags, composite). The "50+ KPIs" goal is not reached by the listed tasks alone.
3. **EBIT** = operating_profit - depreciation (project doc 5.2). The source ROCE better matches PBT + interest (includes other income); logged as FORMULA DISCREPANCY, not changed.
4. **Capital-allocation labels.** The spec uses (+,-,-) twice and omits (-,+,-). (+,-,-) is "Shareholder Returns" when CFO/PAT > 1.0 else "Reinvestor"; (-,+,-) is labelled "Asset Sales Fund Outflows" (my label). A zero/missing sign gives "Undetermined". With the 1.0 threshold most (+,-,-) years become Shareholder Returns; raise it if that is too broad.
5. **CFO quality**: average CFO/PAT over the latest 5 fiscal years, years with PAT <= 0 excluded, at least 3 valid years required.
6. **CAGR windows** are rolling: end = the row's year, start = same year-end month n years earlier. A missing start year is INSUFFICIENT. Start > 0 and end = 0 gives -100% (flag OK).
7. **Composite quality score** is provisional: equal-weight blend of ROE, margin, leverage and cash quality (Financials: ROE + net margin). Sprint 3 health score supersedes it.
8. **Financials carve-out**: 23 companies in the data (spec says 19). High-leverage flag suppressed; ROCE also stored relative to the sector median.
9. **BS_SCALE_SUSPECT** (sales / total_assets > 6x): BEL, HAL, INDIGO, LT. Ratios are computed but flagged; excluded from the screener preview.

## Day 14 checks
- Spot-check (TCS, RELIANCE, ITC; recomputed from raw Excel): max difference 0.000000 pp.
- Screener preview ROE > 15% and D/E < 1 (latest FY, suspect rows excluded): 34 companies.
