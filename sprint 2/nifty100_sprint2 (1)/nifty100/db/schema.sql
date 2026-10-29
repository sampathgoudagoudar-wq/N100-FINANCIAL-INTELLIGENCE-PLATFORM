-- Nifty 100 Financial Intelligence Platform: SQLite schema (Sprint 1)
-- One table per source file (7 core + 5 supplementary = 12 tables).
-- Fiscal-year labels are stored as 'YYYY-MM' (see src/etl/normaliser.py).
PRAGMA foreign_keys = ON;

CREATE TABLE companies (
    id              TEXT PRIMARY KEY CHECK (length(id) BETWEEN 2 AND 12 AND id = upper(trim(id))),
    company_logo    TEXT,
    company_name    TEXT NOT NULL,
    chart_link      TEXT,
    about_company   TEXT,
    website         TEXT,
    nse_profile     TEXT,
    bse_profile     TEXT,
    face_value      REAL,
    book_value      REAL,
    roce_percentage REAL,
    roe_percentage  REAL
);

CREATE TABLE profitandloss (
    source_id         INTEGER,
    company_id        TEXT NOT NULL REFERENCES companies(id),
    year              TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    sales             REAL NOT NULL,
    expenses          REAL NOT NULL,
    operating_profit  REAL,
    opm_percentage    REAL,
    other_income      REAL,
    interest          REAL,
    depreciation      REAL,
    profit_before_tax REAL,
    tax_percentage    REAL,
    net_profit        REAL,
    eps               REAL,
    dividend_payout   REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE balancesheet (
    source_id         INTEGER,
    company_id        TEXT NOT NULL REFERENCES companies(id),
    year              TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    equity_capital    REAL NOT NULL,
    reserves          REAL,
    borrowings        REAL,
    other_liabilities REAL,
    total_liabilities REAL NOT NULL,
    fixed_assets      REAL,
    cwip              REAL,
    investments       REAL,
    other_asset       REAL,
    total_assets      REAL NOT NULL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE cashflow (
    source_id          INTEGER,
    company_id         TEXT NOT NULL REFERENCES companies(id),
    year               TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    operating_activity REAL,
    investing_activity REAL,
    financing_activity REAL,
    net_cash_flow      REAL,
    PRIMARY KEY (company_id, year)
);

-- One row per company per period. Raw text is kept next to the parsed numbers.
CREATE TABLE analysis (
    id                            INTEGER PRIMARY KEY,
    company_id                    TEXT NOT NULL REFERENCES companies(id),
    period                        TEXT,          -- 10Y / 5Y / 3Y / TTM
    compounded_sales_growth       TEXT,
    compounded_profit_growth      TEXT,
    stock_price_cagr              TEXT,
    roe                           TEXT,
    compounded_sales_growth_pct   REAL,
    compounded_profit_growth_pct  REAL,
    stock_price_cagr_pct          REAL,
    roe_pct                       REAL
);

CREATE TABLE documents (
    source_id     INTEGER,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    year          INTEGER NOT NULL,
    annual_report TEXT,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE prosandcons (
    id         INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    pros       TEXT,
    cons       TEXT
);

CREATE TABLE sectors (
    source_id           INTEGER,
    company_id          TEXT PRIMARY KEY REFERENCES companies(id),
    broad_sector        TEXT NOT NULL,
    sub_sector          TEXT,
    index_weight_pct    REAL,
    market_cap_category TEXT
);

CREATE TABLE stock_prices (
    source_id      INTEGER,
    company_id     TEXT NOT NULL REFERENCES companies(id),
    date           TEXT NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    open_price     REAL,
    high_price     REAL,
    low_price      REAL,
    close_price    REAL,
    volume         INTEGER,
    adjusted_close REAL,
    PRIMARY KEY (company_id, date)
);

CREATE TABLE market_cap (
    source_id              INTEGER,
    company_id             TEXT NOT NULL REFERENCES companies(id),
    year                   INTEGER NOT NULL,
    market_cap_crore       REAL,
    enterprise_value_crore REAL,
    pe_ratio               REAL,
    pb_ratio               REAL,
    ev_ebitda              REAL,
    dividend_yield_pct     REAL,
    PRIMARY KEY (company_id, year)
);

-- Supplied (pre-computed/simulated) ratios; kept for cross-checks. The Sprint 2 engine
-- builds the authoritative financial_ratios table (db/schema_ratios.sql).
CREATE TABLE financial_ratios_source (
    source_id                 INTEGER,
    company_id                TEXT NOT NULL REFERENCES companies(id),
    year                      TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    net_profit_margin_pct     REAL,
    operating_profit_margin_pct REAL,
    return_on_equity_pct      REAL,
    debt_to_equity            REAL,
    interest_coverage         REAL,
    asset_turnover            REAL,
    free_cash_flow_cr         REAL,
    capex_cr                  REAL,
    earnings_per_share        REAL,
    book_value_per_share      REAL,
    dividend_payout_ratio_pct REAL,
    total_debt_cr             REAL,
    cash_from_operations_cr   REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE peer_groups (
    source_id       INTEGER,
    peer_group_name TEXT NOT NULL,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    is_benchmark    INTEGER NOT NULL DEFAULT 0 CHECK (is_benchmark IN (0, 1)),
    PRIMARY KEY (peer_group_name, company_id)
);

CREATE INDEX idx_analysis_company     ON analysis(company_id);
CREATE INDEX idx_prosandcons_company  ON prosandcons(company_id);
CREATE INDEX idx_peer_groups_company  ON peer_groups(company_id);
CREATE INDEX idx_stock_prices_date    ON stock_prices(date);
