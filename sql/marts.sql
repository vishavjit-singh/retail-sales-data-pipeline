-- Reporting marts built as views on top of the star schema.

DROP VIEW IF EXISTS mart_daily_revenue;
CREATE VIEW mart_daily_revenue AS
SELECT d.date,
       d.is_weekend,
       COUNT(*)                                             AS orders,
       SUM(CASE WHEN f.status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,
       ROUND(SUM(f.revenue_inr), 2)                         AS revenue_inr
FROM fact_sales f
JOIN dim_date d USING (date_key)
GROUP BY d.date, d.is_weekend
ORDER BY d.date;

DROP VIEW IF EXISTS mart_category_revenue;
CREATE VIEW mart_category_revenue AS
SELECT p.category,
       COUNT(*)                     AS orders,
       SUM(f.quantity)              AS units,
       ROUND(SUM(f.revenue_inr), 2) AS revenue_inr,
       ROUND(AVG(CASE WHEN f.status = 'returned' THEN 1.0 ELSE 0 END), 4) AS return_rate
FROM fact_sales f
JOIN dim_product p USING (product_id)
GROUP BY p.category
ORDER BY revenue_inr DESC;

DROP VIEW IF EXISTS mart_channel_month;
CREATE VIEW mart_channel_month AS
SELECT d.year, d.month, d.month_name, f.channel,
       ROUND(SUM(f.revenue_inr), 2) AS revenue_inr
FROM fact_sales f
JOIN dim_date d USING (date_key)
GROUP BY d.year, d.month, d.month_name, f.channel
ORDER BY d.year, d.month, f.channel;

DROP VIEW IF EXISTS mart_top_customers;
CREATE VIEW mart_top_customers AS
SELECT c.customer_id, c.full_name, c.city, c.segment,
       COUNT(*)                     AS orders,
       ROUND(SUM(f.revenue_inr), 2) AS lifetime_revenue_inr
FROM fact_sales f
JOIN dim_customer c USING (customer_id)
GROUP BY c.customer_id, c.full_name, c.city, c.segment
ORDER BY lifetime_revenue_inr DESC
LIMIT 20;
