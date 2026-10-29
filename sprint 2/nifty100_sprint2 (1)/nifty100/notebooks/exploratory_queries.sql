-- Exploratory queries for nifty100.db (Sprint 1, Day 07). Run with: python -m src.etl.run_queries

-- Q01 Row counts per table
SELECT 'companies' t, COUNT(*) n FROM companies UNION ALL SELECT 'profitandloss', COUNT(*) FROM profitandloss
UNION ALL SELECT 'balancesheet', COUNT(*) FROM balancesheet UNION ALL SELECT 'cashflow', COUNT(*) FROM cashflow
UNION ALL SELECT 'stock_prices', COUNT(*) FROM stock_prices UNION ALL SELECT 'financial_ratios_source', COUNT(*) FROM financial_ratios_source;

-- Q02 Companies per broad sector with average index weight
SELECT broad_sector, COUNT(*) companies, ROUND(SUM(index_weight_pct),2) total_weight_pct
FROM sectors GROUP BY broad_sector ORDER BY companies DESC;

-- Q03 Year coverage per statement (companies with < 5 years)
SELECT c.id, (SELECT COUNT(*) FROM profitandloss WHERE company_id=c.id) pl_years,
       (SELECT COUNT(*) FROM balancesheet WHERE company_id=c.id) bs_years,
       (SELECT COUNT(*) FROM cashflow WHERE company_id=c.id) cf_years
FROM companies c WHERE pl_years < 5 OR bs_years < 5 OR cf_years < 5;

-- Q04 Top 10 companies by latest March-FY sales (Rs Cr)
SELECT p.company_id, c.company_name, p.year, p.sales
FROM profitandloss p JOIN companies c ON c.id = p.company_id
WHERE p.year = '2024-03' ORDER BY p.sales DESC LIMIT 10;

-- Q05 P&L + balance sheet join: return on equity and leverage, FY2024
SELECT p.company_id, ROUND(p.net_profit * 100.0 / (b.equity_capital + b.reserves), 1) roe_pct,
       ROUND(b.borrowings * 1.0 / (b.equity_capital + b.reserves), 2) debt_to_equity
FROM profitandloss p JOIN balancesheet b USING (company_id, year)
WHERE p.year = '2024-03' AND (b.equity_capital + b.reserves) > 0 ORDER BY roe_pct DESC LIMIT 10;

-- Q06 Cash-flow health: profitable companies with negative operating cash flow
SELECT p.company_id, p.year, p.net_profit, f.operating_activity
FROM profitandloss p JOIN cashflow f USING (company_id, year)
WHERE p.net_profit > 0 AND f.operating_activity < 0 ORDER BY p.year DESC LIMIT 20;

-- Q07 Sector median-ish view: average OPM by sector, FY2024
SELECT s.broad_sector, ROUND(AVG(p.opm_percentage),1) avg_opm, COUNT(*) n
FROM profitandloss p JOIN sectors s USING (company_id)
WHERE p.year = '2024-03' AND p.opm_percentage BETWEEN -100 AND 100 GROUP BY s.broad_sector ORDER BY avg_opm DESC;

-- Q08 Peer-group ranking by FY2024 ROE using financial_ratios
SELECT pg.peer_group_name, r.company_id, r.return_on_equity_pct,
       RANK() OVER (PARTITION BY pg.peer_group_name ORDER BY r.return_on_equity_pct DESC) rnk
FROM peer_groups pg JOIN financial_ratios_source r ON r.company_id = pg.company_id
WHERE r.year = '2024-03' ORDER BY pg.peer_group_name, rnk;

-- Q09 Stock price: 2024 calendar-year return per company (Jan open -> Dec close)
SELECT a.company_id, ROUND((z.close_price / a.open_price - 1) * 100, 1) return_2024_pct
FROM stock_prices a JOIN stock_prices z ON z.company_id = a.company_id
WHERE a.date = '2024-01-01' AND z.date = '2024-12-01' ORDER BY return_2024_pct DESC LIMIT 10;

-- Q10 Annual reports available per company (latest year and count)
SELECT company_id, COUNT(*) reports, MAX(year) latest_year, SUM(annual_report IS NULL) missing_links
FROM documents GROUP BY company_id ORDER BY reports DESC LIMIT 15;
