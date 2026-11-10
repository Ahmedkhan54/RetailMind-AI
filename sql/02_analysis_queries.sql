USE retail_sales_db;

-- 1. Overall KPIs
WITH order_totals AS (
    SELECT order_id, SUM(sales) AS order_sales
    FROM sales
    GROUP BY order_id
)
SELECT (SELECT COUNT(*) FROM order_totals) AS total_orders,
       ROUND((SELECT SUM(order_sales) FROM order_totals), 2) AS total_sales,
       ROUND(SUM(profit), 2) AS total_profit,
       ROUND((SELECT AVG(order_sales) FROM order_totals), 2) AS average_order_sales
FROM sales;

-- 2. Sales and profit by category
SELECT category, ROUND(SUM(sales), 2) AS total_sales,
       ROUND(SUM(profit), 2) AS total_profit
FROM sales
GROUP BY category
ORDER BY total_profit DESC;

-- 3. Best-performing cities
SELECT city, ROUND(SUM(sales), 2) AS total_sales,
       ROUND(SUM(profit), 2) AS total_profit
FROM sales
GROUP BY city
ORDER BY total_sales DESC;

-- 4. Top 10 products by revenue
SELECT product_name, SUM(quantity) AS units_sold,
       ROUND(SUM(sales), 2) AS total_sales
FROM sales
GROUP BY product_name
ORDER BY total_sales DESC
LIMIT 10;

-- 5. Monthly sales and profit
SELECT DATE_FORMAT(order_date, '%Y-%m') AS sales_month,
       ROUND(SUM(sales), 2) AS total_sales,
       ROUND(SUM(profit), 2) AS total_profit
FROM sales
GROUP BY DATE_FORMAT(order_date, '%Y-%m')
ORDER BY sales_month;

-- 6. Categories with profit above 100,000
SELECT category, ROUND(SUM(profit), 2) AS total_profit
FROM sales
GROUP BY category
HAVING SUM(profit) > 100000
ORDER BY total_profit DESC;

-- 7. Orders with negative profit
SELECT order_id, order_date, product_name, city, sales, profit
FROM sales
WHERE profit < 0
ORDER BY profit ASC;

-- 8. Payment method usage
SELECT payment_method, COUNT(DISTINCT order_id) AS order_count,
       ROUND(SUM(sales), 2) AS total_sales
FROM sales
GROUP BY payment_method
ORDER BY order_count DESC;

-- 9. Rank products within each category (MySQL 8+)
WITH product_totals AS (
    SELECT category, product_name, SUM(sales) AS total_sales
    FROM sales
    GROUP BY category, product_name
),
ranked_products AS (
    SELECT category, product_name, total_sales,
           DENSE_RANK() OVER (PARTITION BY category ORDER BY total_sales DESC) AS product_rank
    FROM product_totals
)
SELECT category, product_name, ROUND(total_sales, 2) AS total_sales, product_rank
FROM ranked_products
WHERE product_rank <= 3
ORDER BY category, product_rank;

-- 10. Month-over-month change (MySQL 8+)
WITH monthly_sales AS (
    SELECT DATE_FORMAT(order_date, '%Y-%m') AS sales_month,
           SUM(sales) AS total_sales
    FROM sales
    GROUP BY DATE_FORMAT(order_date, '%Y-%m')
),
monthly_comparison AS (
    SELECT sales_month, total_sales,
           LAG(total_sales) OVER (ORDER BY sales_month) AS previous_month_sales
    FROM monthly_sales
)
SELECT sales_month,
       ROUND(total_sales, 2) AS total_sales,
       ROUND(previous_month_sales, 2) AS previous_month_sales,
       ROUND(total_sales - previous_month_sales, 2) AS sales_change
FROM monthly_comparison
ORDER BY sales_month;

-- 11. Check data quality
SELECT COUNT(*) AS row_count, COUNT(DISTINCT order_id) AS unique_order_ids,
       SUM(order_id IS NULL) AS missing_order_ids
FROM sales;
