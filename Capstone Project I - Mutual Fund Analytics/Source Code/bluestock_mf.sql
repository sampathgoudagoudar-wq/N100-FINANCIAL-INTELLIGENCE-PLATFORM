CREATE DATABASE IF NOT EXISTS bluestock_mf;
USE bluestock_mf;

CREATE TABLE stg_nav_history (
    amfi_code   INT,
    nav_date    VARCHAR(20),
    nav         VARCHAR(20)
);
CREATE TABLE stg_investor_transactions (
    investor_id         VARCHAR(20),
    transaction_date    VARCHAR(20),
    amfi_code           INT,
    transaction_type    VARCHAR(30),
    amount_inr          VARCHAR(20),
    state               VARCHAR(50),
    city                VARCHAR(50),
    city_tier           VARCHAR(10),
    age_group           VARCHAR(10),
    gender              VARCHAR(10),
    annual_income_lakh  VARCHAR(20),
    payment_mode        VARCHAR(30),
    kyc_status          VARCHAR(20)
);
CREATE TABLE stg_scheme_performance (
    amfi_code           INT,
    scheme_name         VARCHAR(150),
    fund_house          VARCHAR(100),
    category            VARCHAR(50),
    plan                VARCHAR(20),
    return_1yr_pct      VARCHAR(20),
    return_3yr_pct      VARCHAR(20),
    return_5yr_pct      VARCHAR(20),
    benchmark_3yr_pct   VARCHAR(20),
    alpha               VARCHAR(20),
    beta                VARCHAR(20),
    sharpe_ratio        VARCHAR(20),
    sortino_ratio       VARCHAR(20),
    std_dev_ann_pct     VARCHAR(20),
    max_drawdown_pct    VARCHAR(20),
    aum_crore           VARCHAR(20),
    expense_ratio_pct   VARCHAR(20),
    morningstar_rating  VARCHAR(10),
    risk_grade          VARCHAR(30)
);
LOAD DATA LOCAL INFILE '/path/to/nav_history.csv'
INTO TABLE stg_nav_history
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(amfi_code, nav_date, nav);

LOAD DATA LOCAL INFILE '/path/to/investor_transactions.csv'
INTO TABLE stg_investor_transactions
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(investor_id, transaction_date, amfi_code, transaction_type, amount_inr, state, city,
 city_tier, age_group, gender, annual_income_lakh, payment_mode, kyc_status);

LOAD DATA LOCAL INFILE '/path/to/scheme_performance.csv'
INTO TABLE stg_scheme_performance
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(amfi_code, scheme_name, fund_house, category, plan, return_1yr_pct, return_3yr_pct,
 return_5yr_pct, benchmark_3yr_pct, alpha, beta, sharpe_ratio, sortino_ratio,
 std_dev_ann_pct, max_drawdown_pct, aum_crore, expense_ratio_pct, morningstar_rating,
 risk_grade);
 SELECT COUNT(*) FROM stg_nav_history;             
SELECT COUNT(*) FROM stg_investor_transactions;  
SELECT COUNT(*) FROM stg_scheme_performance;      
CREATE TABLE nav_history_clean (
    amfi_code           INT NOT NULL,
    nav_date            DATE NOT NULL,
    nav                 DECIMAL(12,4) NOT NULL,
    is_forward_filled  SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (amfi_code, nav_date)
);
INSERT INTO nav_history_clean (amfi_code, nav_date, nav, is_forward_filled)
SELECT
    amfi_code,
    STR_TO_DATE(nav_date, '%Y-%m-%d') AS nav_date,
    CAST(nav AS DECIMAL(12,4)) AS nav,
    0
FROM stg_nav_history
WHERE nav_date REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'  
  AND nav REGEXP '^[0-9]+(\\.[0-9]+)?$'                 
  AND CAST(nav AS DECIMAL(12,4)) > 0;    

  CREATE TABLE stg_nav_history_deduped AS
SELECT amfi_code, nav_date, nav
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY amfi_code, nav_date
               ORDER BY nav DESC  
           ) AS rn
    FROM stg_nav_history
) t
WHERE rn = 1;

CREATE TABLE calendar_dates (cal_date DATE PRIMARY KEY);

INSERT INTO calendar_dates (cal_date)
WITH RECURSIVE seq AS (
    SELECT DATE('2022-01-01') AS cal_date
    UNION ALL
    SELECT cal_date + INTERVAL 1 DAY FROM seq WHERE cal_date < '2026-12-31'
)
SELECT cal_date FROM seq;

CREATE TABLE nav_grid AS
SELECT f.amfi_code, c.cal_date
FROM (SELECT DISTINCT amfi_code, MIN(nav_date) AS min_d, MAX(nav_date) AS max_d
      FROM nav_history_clean GROUP BY amfi_code) f
JOIN calendar_dates c ON c.cal_date BETWEEN f.min_d AND f.max_d;

CREATE TABLE nav_history_filled AS
WITH joined AS (
    SELECT g.amfi_code, g.cal_date,
           n.nav AS actual_nav,
           IF(n.nav IS NOT NULL, 1, 0) AS has_value
    FROM nav_grid g
    LEFT JOIN nav_history_clean n
           ON n.amfi_code = g.amfi_code AND n.nav_date = g.cal_date
),
grouped AS (
    SELECT *,
           SUM(has_value) OVER (
               PARTITION BY amfi_code ORDER BY cal_date
           ) AS grp
    FROM joined
)
SELECT amfi_code, cal_date AS nav_date,
       MAX(actual_nav) OVER (PARTITION BY amfi_code, grp) AS nav,
       IF(has_value = 1, 0, 1) AS is_forward_filled
FROM grouped;

TRUNCATE TABLE nav_history_clean;
INSERT INTO nav_history_clean (amfi_code, nav_date, nav, is_forward_filled)
SELECT amfi_code, nav_date, nav, is_forward_filled FROM nav_history_filled;

SELECT COUNT(*) FROM nav_history_clean WHERE nav <= 0;                          
SELECT amfi_code, nav_date, COUNT(*) FROM nav_history_clean
GROUP BY amfi_code, nav_date HAVING COUNT(*) > 1;                           
SELECT amfi_code, COUNT(*) FROM nav_history_clean GROUP BY amfi_code;   

CREATE TABLE investor_transactions_clean (
    transaction_id       INT AUTO_INCREMENT PRIMARY KEY,
    investor_id          VARCHAR(20) NOT NULL,
    transaction_date     DATE NOT NULL,
    amfi_code            INT NOT NULL,
    transaction_type     VARCHAR(20) NOT NULL,
    amount_inr           DECIMAL(14,2) NOT NULL,
    state                VARCHAR(50),
    city                 VARCHAR(50),
    city_tier            VARCHAR(10),
    age_group            VARCHAR(10),
    gender               VARCHAR(10),
    annual_income_lakh   DECIMAL(10,2),
    payment_mode         VARCHAR(30),
    kyc_status           VARCHAR(20)
);

INSERT INTO investor_transactions_clean
    (investor_id, transaction_date, amfi_code, transaction_type, amount_inr,
     state, city, city_tier, age_group, gender, annual_income_lakh, payment_mode, kyc_status)
SELECT
    TRIM(investor_id),
    STR_TO_DATE(TRIM(transaction_date), '%Y-%m-%d'),
    amfi_code,
    CASE UPPER(TRIM(transaction_type))
        WHEN 'SIP'         THEN 'SIP'
        WHEN 'LUMPSUM'     THEN 'Lumpsum'
        WHEN 'LUMP SUM'    THEN 'Lumpsum'
        WHEN 'REDEMPTION'  THEN 'Redemption'
        WHEN 'REDEEM'      THEN 'Redemption'
        ELSE NULL
    END,
    CAST(amount_inr AS DECIMAL(14,2)),
    TRIM(state), TRIM(city), UPPER(TRIM(city_tier)), TRIM(age_group), TRIM(gender),
    CAST(annual_income_lakh AS DECIMAL(10,2)),
    TRIM(payment_mode),
  
    CASE UPPER(TRIM(kyc_status))
        WHEN 'VERIFIED' THEN 'Verified'
        WHEN 'PENDING'  THEN 'Pending'
        WHEN 'REJECTED' THEN 'Rejected'
        ELSE NULL
    END
FROM stg_investor_transactions
WHERE transaction_date REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'     
  AND amount_inr REGEXP '^[0-9]+(\\.[0-9]+)?$'
  AND CAST(amount_inr AS DECIMAL(14,2)) > 0;                     

DELETE FROM investor_transactions_clean
WHERE transaction_type IS NULL OR kyc_status IS NULL;

CREATE TABLE IF NOT EXISTS investor_transactions_clean (
    investor_id          VARCHAR(50),
    transaction_date     DATE,
    amfi_code            INT,
    transaction_type     VARCHAR(20),
    amount_inr           DECIMAL(14,2),
    state                VARCHAR(100),
    city                 VARCHAR(100),
    city_tier            VARCHAR(10),
    age_group            VARCHAR(20),
    gender               VARCHAR(20),
    annual_income_lakh   DECIMAL(10,2),
    payment_mode         VARCHAR(50),
    kyc_status           VARCHAR(20)
);

INSERT INTO investor_transactions_clean (
    investor_id, transaction_date, amfi_code, transaction_type, amount_inr,
    state, city, city_tier, age_group, gender, annual_income_lakh, payment_mode, kyc_status
)
SELECT 
    TRIM(investor_id),
    TO_DATE(TRIM(transaction_date), 'YYYY-MM-DD'),
    amfi_code,
    CASE UPPER(TRIM(transaction_type))
        WHEN 'SIP' THEN 'SIP'
        WHEN 'LUMPSUM' THEN 'Lumpsum'
        WHEN 'LUMP SUM' THEN 'Lumpsum'
        WHEN 'REDEMPTION' THEN 'Redemption'
        WHEN 'REDEEM' THEN 'Redemption'
        ELSE NULL
    END,
    CAST(amount_inr AS DECIMAL(14,2)),
    TRIM(state),
    TRIM(city),
    UPPER(TRIM(city_tier)),
    TRIM(age_group),
    TRIM(gender),
    CAST(annual_income_lakh AS DECIMAL(10,2)),
    TRIM(payment_mode),
    INITCAP(TRIM(kyc_status))
FROM stg_investor_transactions
WHERE transaction_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  AND amount_inr ~ '^[0-9]+(\.[0-9]+)?$'
  AND CAST(amount_inr AS DECIMAL(14,2)) > 0;

  CREATE TABLE scheme_performance_clean (
    amfi_code           INT PRIMARY KEY,
    scheme_name         VARCHAR(150) NOT NULL,
    fund_house          VARCHAR(100) NOT NULL,
    category            VARCHAR(50) NOT NULL,
    plan                VARCHAR(20) NOT NULL,
    return_1yr_pct      DECIMAL(8,2),
    return_3yr_pct      DECIMAL(8,2),
    return_5yr_pct      DECIMAL(8,2),
    benchmark_3yr_pct   DECIMAL(8,2),
    alpha               DECIMAL(8,2),
    beta                DECIMAL(8,2),
    sharpe_ratio        DECIMAL(8,2),
    sortino_ratio       DECIMAL(8,2),
    std_dev_ann_pct     DECIMAL(8,2),
    max_drawdown_pct    DECIMAL(8,2),
    aum_crore           DECIMAL(14,2),
    expense_ratio_pct   DECIMAL(6,3),
    morningstar_rating  SMALLINT,
    risk_grade          VARCHAR(30),
    expense_ratio_flag  VARCHAR(20),
    anomaly_flags       VARCHAR(255) DEFAULT ''
);

INSERT INTO scheme_performance_clean
    (amfi_code, scheme_name, fund_house, category, plan, return_1yr_pct, return_3yr_pct,
     return_5yr_pct, benchmark_3yr_pct, alpha, beta, sharpe_ratio, sortino_ratio,
     std_dev_ann_pct, max_drawdown_pct, aum_crore, expense_ratio_pct, morningstar_rating,
     risk_grade)
SELECT
    amfi_code, TRIM(scheme_name), TRIM(fund_house), TRIM(category), TRIM(plan),
    CAST(return_1yr_pct AS DECIMAL(8,2)), CAST(return_3yr_pct AS DECIMAL(8,2)),
    CAST(return_5yr_pct AS DECIMAL(8,2)), CAST(benchmark_3yr_pct AS DECIMAL(8,2)),
    CAST(alpha AS DECIMAL(8,2)), CAST(beta AS DECIMAL(8,2)),
    CAST(sharpe_ratio AS DECIMAL(8,2)), CAST(sortino_ratio AS DECIMAL(8,2)),
    CAST(std_dev_ann_pct AS DECIMAL(8,2)), CAST(max_drawdown_pct AS DECIMAL(8,2)),
    CAST(aum_crore AS DECIMAL(14,2)), CAST(expense_ratio_pct AS DECIMAL(6,3)),
    CAST(morningstar_rating AS UNSIGNED), TRIM(risk_grade)
FROM stg_scheme_performance
WHERE return_1yr_pct     REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND return_3yr_pct     REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND return_5yr_pct     REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND benchmark_3yr_pct  REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND alpha              REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND beta               REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND sharpe_ratio       REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND sortino_ratio      REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND std_dev_ann_pct    REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND max_drawdown_pct   REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
  AND aum_crore          REGEXP '^[0-9]+(\\.[0-9]+)?$'
  AND expense_ratio_pct  REGEXP '^[0-9]+(\\.[0-9]+)?$';

UPDATE scheme_performance_clean
SET expense_ratio_flag = CASE 
    WHEN expense_ratio_pct BETWEEN 0.1 AND 2.5 THEN 'OK'
    ELSE 'OUT_OF_RANGE'
END;

SELECT amfi_code, scheme_name, expense_ratio_pct
FROM scheme_performance_clean
WHERE expense_ratio_flag = 'OUT_OF_RANGE';

UPDATE scheme_performance_clean
SET anomaly_flags = TRIM(BOTH ';' FROM CONCAT_WS(';',
    IF(max_drawdown_pct > 0, 'positive_max_drawdown', NULL),
    IF(beta < 0, 'negative_beta', NULL),
    IF(std_dev_ann_pct < 0, 'negative_std_dev', NULL),
    IF(return_1yr_pct < -100 OR return_1yr_pct > 200, 'return_1yr_out_of_plausible_range', NULL),
    IF(morningstar_rating NOT IN (1,2,3,4,5), 'invalid_morningstar_rating', NULL)
));

WITH stats AS (
    SELECT category, AVG(sharpe_ratio) AS mean_sr, STDDEV_POP(sharpe_ratio) AS sd_sr
    FROM scheme_performance_clean
    GROUP BY category
)
UPDATE scheme_performance_clean p
JOIN stats s ON s.category = p.category
SET p.anomaly_flags = TRIM(BOTH ';' FROM CONCAT_WS(';', NULLIF(p.anomaly_flags,''), 'sharpe_statistical_outlier'))
WHERE s.sd_sr > 0
  AND ABS((p.sharpe_ratio - s.mean_sr) / s.sd_sr) > 3;

  SELECT anomaly_flags, COUNT(*) FROM scheme_performance_clean
WHERE anomaly_flags <> '' GROUP BY anomaly_flags;

CREATE TABLE dim_fund (
    amfi_code           INT PRIMARY KEY,
    scheme_name         VARCHAR(150) NOT NULL,
    fund_house          VARCHAR(100) NOT NULL,
    category            VARCHAR(50) NOT NULL,
    plan                VARCHAR(20) NOT NULL,
    morningstar_rating  TINYINT,
    risk_grade          VARCHAR(30)
) ENGINE=InnoDB;

CREATE TABLE dim_date (
    date_key      DATE PRIMARY KEY,
    year          INT NOT NULL,
    quarter       TINYINT NOT NULL,
    month         TINYINT NOT NULL,
    month_name    VARCHAR(15) NOT NULL,
    day           TINYINT NOT NULL,
    day_of_week   VARCHAR(15) NOT NULL,
    is_weekend    TINYINT(1) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE fact_nav (
    nav_id             INT AUTO_INCREMENT PRIMARY KEY,
    amfi_code          INT NOT NULL,
    date_key           DATE NOT NULL,
    nav                DECIMAL(12,4) NOT NULL CHECK (nav > 0),
    is_forward_filled  TINYINT(1) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_fund_date (amfi_code, date_key),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date_key)  REFERENCES dim_date(date_key)
) ENGINE=InnoDB;

CREATE TABLE fact_transactions (
    transaction_id       INT PRIMARY KEY,
    investor_id          VARCHAR(20) NOT NULL,
    date_key             DATE NOT NULL,
    amfi_code            INT NOT NULL,
    transaction_type     VARCHAR(20) NOT NULL,
    amount_inr           DECIMAL(14,2) NOT NULL CHECK (amount_inr > 0),
    state                VARCHAR(50),
    city                 VARCHAR(50),
    city_tier            VARCHAR(10),
    age_group            VARCHAR(10),
    gender               VARCHAR(10),
    annual_income_lakh   DECIMAL(10,2),
    payment_mode         VARCHAR(30),
    kyc_status           VARCHAR(20),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date_key)  REFERENCES dim_date(date_key)
) ENGINE=InnoDB;

CREATE TABLE fact_performance (
    performance_id        INT AUTO_INCREMENT PRIMARY KEY,
    amfi_code             INT NOT NULL UNIQUE,
    return_1yr_pct        DECIMAL(8,2),
    return_3yr_pct        DECIMAL(8,2),
    return_5yr_pct        DECIMAL(8,2),
    benchmark_3yr_pct     DECIMAL(8,2),
    alpha                 DECIMAL(8,2),
    beta                  DECIMAL(8,2),
    sharpe_ratio          DECIMAL(8,2),
    sortino_ratio         DECIMAL(8,2),
    std_dev_ann_pct       DECIMAL(8,2),
    max_drawdown_pct      DECIMAL(8,2),
    expense_ratio_pct     DECIMAL(6,3) CHECK (expense_ratio_pct BETWEEN 0.1 AND 2.5),
    expense_ratio_flag    VARCHAR(20),
    anomaly_flags         VARCHAR(255),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code)
) ENGINE=InnoDB;

CREATE TABLE fact_aum (
    aum_id        INT AUTO_INCREMENT PRIMARY KEY,
    amfi_code     INT NOT NULL,
    snapshot_date DATE,
    aum_crore     DECIMAL(14,2) NOT NULL CHECK (aum_crore >= 0),
    UNIQUE KEY uq_fund_snapshot (amfi_code, snapshot_date),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code)
) ENGINE=InnoDB;

CREATE INDEX idx_fact_nav_date  ON fact_nav(date_key);
CREATE INDEX idx_fact_tx_date   ON fact_transactions(date_key);
CREATE INDEX idx_fact_tx_state  ON fact_transactions(state);

DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_date AS
WITH date_range AS (
    SELECT 
        LEAST(
            (SELECT MIN(nav_date) FROM nav_history_clean), 
            (SELECT MIN(transaction_date) FROM investor_transactions_clean)
        ) AS min_date,
        GREATEST(
            (SELECT MAX(nav_date) FROM nav_history_clean), 
            (SELECT MAX(transaction_date) FROM investor_transactions_clean)
        ) AS max_date
),
generated_dates AS (
    SELECT generate_series(min_date, max_date, INTERVAL '1 day')::DATE AS cal_date
    FROM date_range
)
SELECT 
    cal_date AS date_key,
    EXTRACT(YEAR FROM cal_date)::INT AS year,
    EXTRACT(QUARTER FROM cal_date)::INT AS quarter,
    EXTRACT(MONTH FROM cal_date)::INT AS month,
    TRIM(TO_CHAR(cal_date, 'Month')) AS month_name,
    EXTRACT(DAY FROM cal_date)::INT AS day,
    TRIM(TO_CHAR(cal_date, 'Day')) AS day_of_week,
    (EXTRACT(ISODOW FROM cal_date) IN (6, 7)) AS is_weekend
FROM generated_dates;

ALTER TABLE dim_date ADD PRIMARY KEY (date_key);


DROP TABLE IF EXISTS fact_aum;
DROP TABLE IF EXISTS fact_performance;
DROP TABLE IF EXISTS fact_transactions;
DROP TABLE IF EXISTS fact_nav;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_fund;

CREATE TABLE dim_fund AS
SELECT 
    amfi_code, 
    scheme_name, 
    fund_house, 
    category, 
    plan, 
    morningstar_rating, 
    risk_grade
FROM scheme_performance_clean;

ALTER TABLE dim_fund ADD PRIMARY KEY (amfi_code);

CREATE TABLE fact_transactions AS
SELECT * 
FROM investor_transactions_clean;

CREATE TABLE fact_nav AS
SELECT 
    amfi_code, 
    nav_date AS date_key, 
    nav, 
    is_forward_filled 
FROM nav_history_clean;

CREATE TABLE fact_performance AS
SELECT 
    amfi_code, 
    return_1yr_pct, 
    return_3yr_pct, 
    return_5yr_pct, 
    benchmark_3yr_pct, 
    alpha, 
    beta, 
    sharpe_ratio, 
    sortino_ratio, 
    std_dev_ann_pct, 
    max_drawdown_pct, 
    expense_ratio_pct, 
    expense_ratio_flag, 
    anomaly_flags
FROM scheme_performance_clean;

CREATE TABLE fact_aum AS
SELECT 
    p.amfi_code, 
    latest.snapshot_date, 
    p.aum_crore
FROM scheme_performance_clean p
JOIN (
    SELECT amfi_code, MAX(nav_date) AS snapshot_date
    FROM nav_history_clean
    GROUP BY amfi_code
) latest ON latest.amfi_code = p.amfi_code;

DROP TABLE IF EXISTS fact_aum CASCADE;
DROP TABLE IF EXISTS fact_performance CASCADE;
DROP TABLE IF EXISTS fact_transactions CASCADE;
DROP TABLE IF EXISTS fact_nav CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;
DROP TABLE IF EXISTS dim_fund CASCADE;

CREATE TABLE dim_fund AS
SELECT amfi_code, scheme_name, fund_house, category, plan, morningstar_rating, risk_grade
FROM scheme_performance_clean;
ALTER TABLE dim_fund ADD PRIMARY KEY (amfi_code);

CREATE TABLE fact_nav AS
SELECT amfi_code, nav_date::DATE AS date_key, nav, is_forward_filled 
FROM nav_history_clean;

CREATE TABLE fact_transactions AS
SELECT 
    ROW_NUMBER() OVER () AS transaction_id,
    investor_id, 
    transaction_date::DATE AS date_key, 
    amfi_code, 
    transaction_type, 
    amount_inr, 
    state, 
    city, 
    city_tier, 
    age_group, 
    gender, 
    annual_income_lakh, 
    payment_mode, 
    kyc_status
FROM investor_transactions_clean;

CREATE TABLE fact_performance AS
SELECT amfi_code, return_1yr_pct, return_3yr_pct, return_5yr_pct, benchmark_3yr_pct, alpha, beta, sharpe_ratio, sortino_ratio, std_dev_ann_pct, max_drawdown_pct, expense_ratio_pct, expense_ratio_flag, anomaly_flags
FROM scheme_performance_clean;

CREATE TABLE fact_aum AS
SELECT p.amfi_code, latest.snapshot_date, p.aum_crore
FROM scheme_performance_clean p
JOIN (
    SELECT amfi_code, MAX(nav_date::DATE) AS snapshot_date
    FROM nav_history_clean
    GROUP BY amfi_code
) latest ON latest.amfi_code = p.amfi_code;

CREATE TABLE dim_date AS
WITH date_bounds AS (
    SELECT 
        LEAST(
            (SELECT MIN(date_key) FROM fact_nav), 
            (SELECT MIN(date_key) FROM fact_transactions)
        ) AS min_d,
        GREATEST(
            (SELECT MAX(date_key) FROM fact_nav), 
            (SELECT MAX(date_key) FROM fact_transactions)
        ) AS max_d
),
series AS (
    SELECT generate_series(min_d, max_d, INTERVAL '1 day')::DATE AS cal_date
    FROM date_bounds
)
SELECT 
    cal_date AS date_key,
    EXTRACT(YEAR FROM cal_date)::INT AS year,
    EXTRACT(QUARTER FROM cal_date)::INT AS quarter,
    EXTRACT(MONTH FROM cal_date)::INT AS month,
    TRIM(TO_CHAR(cal_date, 'Month')) AS month_name,
    EXTRACT(DAY FROM cal_date)::INT AS day,
    TRIM(TO_CHAR(cal_date, 'Day')) AS day_of_week,
    (EXTRACT(ISODOW FROM cal_date) IN (6, 7)) AS is_weekend
FROM series;

ALTER TABLE dim_date ADD PRIMARY KEY (date_key);

git init                                   
git add .
git commit -m "Day 2: Cleaned data + SQLite DB loaded"

DROP TABLE IF EXISTS stg_nav_history;
DROP TABLE IF EXISTS stg_investor_transactions;
DROP TABLE IF EXISTS stg_scheme_performance;
DROP TABLE IF EXISTS nav_history_filled;
DROP TABLE IF EXISTS nav_grid;
DROP TABLE IF EXISTS calendar_dates;