-- Sprint 2: authoritative KPI table, rebuilt by src/analytics/engine.py
DROP TABLE IF EXISTS financial_ratios;
CREATE TABLE financial_ratios (
    company_id                  TEXT NOT NULL REFERENCES companies(id),
    year                        TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    -- profitability
    net_profit_margin_pct       REAL,
    operating_profit_margin_pct REAL,   -- computed: operating_profit / sales x 100
    opm_source_pct              REAL,   -- opm_percentage as supplied
    opm_mismatch_flag           INTEGER,
    return_on_equity_pct        REAL,
    roce_pct                    REAL,
    roce_vs_sector_median_pp    REAL,   -- Financials only: ROCE minus sector median for the year
    return_on_assets_pct        REAL,
    -- leverage / efficiency
    debt_to_equity              REAL,
    high_leverage_flag          INTEGER,
    interest_coverage           REAL,
    icr_label                   TEXT,
    icr_warning_flag            INTEGER,
    net_debt_cr                 REAL,
    asset_turnover              REAL,
    total_debt_cr               REAL,
    -- cash flow
    free_cash_flow_cr           REAL,
    capex_cr                    REAL,
    cash_from_operations_cr     REAL,
    cfo_quality_score           REAL,
    cfo_quality_label           TEXT,
    capex_intensity_pct         REAL,
    capex_intensity_label       TEXT,
    fcf_conversion_pct          REAL,
    capital_allocation_pattern  TEXT,
    -- per share / payout
    earnings_per_share          REAL,
    book_value_per_share        REAL,
    dividend_payout_ratio_pct   REAL,
    -- growth (CAGR % and flag per window)
    revenue_cagr_3yr REAL, revenue_cagr_3yr_flag TEXT,
    revenue_cagr_5yr REAL, revenue_cagr_5yr_flag TEXT,
    revenue_cagr_10yr REAL, revenue_cagr_10yr_flag TEXT,
    pat_cagr_3yr REAL, pat_cagr_3yr_flag TEXT,
    pat_cagr_5yr REAL, pat_cagr_5yr_flag TEXT,
    pat_cagr_10yr REAL, pat_cagr_10yr_flag TEXT,
    eps_cagr_3yr REAL, eps_cagr_3yr_flag TEXT,
    eps_cagr_5yr REAL, eps_cagr_5yr_flag TEXT,
    eps_cagr_10yr REAL, eps_cagr_10yr_flag TEXT,
    -- composite and data-quality
    composite_quality_score     REAL,   -- 0-100, provisional weighting (see engine.py)
    data_quality_flag           TEXT,
    PRIMARY KEY (company_id, year)
);
CREATE INDEX idx_fr_year ON financial_ratios(year);
