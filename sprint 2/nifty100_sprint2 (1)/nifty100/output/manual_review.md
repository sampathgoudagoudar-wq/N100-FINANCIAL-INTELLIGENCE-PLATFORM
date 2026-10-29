# Day 06 manual review (seed=7)

Companies: HINDALCO, BOSCHLTD, IRCTC, TATAMOTORS, AMBUJACEM

## HINDALCO - Hindalco Industries Ltd

| table | db years | first | last | raw rows | value check |
|---|---|---|---|---|---|
| profitandloss | 12 | 2013-03 | 2024-03 | 12 | years match; 0 value mismatches |
| balancesheet | 13 | 2013-03 | 2024-09 | 13 | years match; 0 value mismatches |
| cashflow | 12 | 2013-03 | 2024-03 | 12 | years match; 0 value mismatches |

stock_prices rows: 60 (expected 60)

## BOSCHLTD - Bosch Ltd

| table | db years | first | last | raw rows | value check |
|---|---|---|---|---|---|
| profitandloss | 12 | 2012-12 | 2024-03 | 12 | years match; 0 value mismatches |
| balancesheet | 13 | 2012-12 | 2024-09 | 13 | years match; 0 value mismatches |
| cashflow | 12 | 2012-12 | 2024-03 | 12 | years match; 0 value mismatches |

stock_prices rows: 60 (expected 60)

## IRCTC - Indian Railway Catering & Tourism Corporation Ltd

| table | db years | first | last | raw rows | value check |
|---|---|---|---|---|---|
| profitandloss | 10 | 2015-03 | 2024-03 | 10 | years match; 0 value mismatches |
| balancesheet | 11 | 2015-03 | 2024-09 | 11 | years match; 0 value mismatches |
| cashflow | 10 | 2015-03 | 2024-03 | 10 | years match; 0 value mismatches |

stock_prices rows: 60 (expected 60)

## TATAMOTORS - Tata Motors Ltd

| table | db years | first | last | raw rows | value check |
|---|---|---|---|---|---|
| profitandloss | 12 | 2013-03 | 2024-03 | 12 | years match; 0 value mismatches |
| balancesheet | 13 | 2013-03 | 2024-09 | 13 | years match; 0 value mismatches |
| cashflow | 12 | 2013-03 | 2024-03 | 12 | years match; 0 value mismatches |

stock_prices rows: 60 (expected 60)

## AMBUJACEM - Ambuja Cements Ltd

| table | db years | first | last | raw rows | value check |
|---|---|---|---|---|---|
| profitandloss | 12 | 2012-12 | 2024-03 | 12 | years match; 0 value mismatches |
| balancesheet | 13 | 2012-12 | 2024-09 | 13 | years match; 0 value mismatches |
| cashflow | 12 | 2012-12 | 2024-03 | 12 | years match; 0 value mismatches |

stock_prices rows: 60 (expected 60)

## Companies with fewer than 5 years in any statement

| id     |   pl |   bs |   cf |
|:-------|-----:|-----:|-----:|
| JIOFIN |    2 |    3 |    2 |
| SBIN   |   12 |    0 |   12 |

## Findings for analyst follow-up (source data, not loader bugs)

1. **Loader bug fixed:** 7 cash-flow rows were keyed `AGTL` (typo of `ATGL`); remapped via `TICKER_ALIASES`.
2. **SBIN has no balance-sheet rows and ATGL/SBIN have no financial_ratios rows in the source files.**
3. **Out-of-universe tickers:** ULTRACEMCO, UNIONBANK, UNITDSPR, VBL, VEDL, WIPRO, ZOMATO, ZYDUSLIFE appear in time-series files but not in companies.xlsx (92); their rows are excluded (DQ-03).
4. **Implausible balance-sheet scale** for BEL, HAL, INDIGO and LT (sales/total_assets > 20x in 39 rows; e.g. BEL FY24 total_assets=161 Cr vs sales=20,268 Cr), so ROE is in the thousands of %. Balance and OPM rules cannot catch this.
5. **83 balance-sheet rows are labelled Sep 2024** (one per company) with no matching P&L/CF period; kept as `2024-09` but look like interim snapshots.
6. **Bank OPM:** `opm_percentage` holds non-percentage values for banks (e.g. AXISBANK 1353), driving most DQ-05 flags.
7. TVSMOTOR has no face/book value or ROCE in companies.xlsx; INDIGO and TVSMOTOR have null ROE.

**Result: 0 problems across the 5 sampled companies.**