USE retail_sales_db;

-- Customer RFM segmentation, MySQL 8+; bind/report an as_of_date in production.
WITH customer_base AS (
  SELECT customer_id, MAX(order_date) AS last_order_date,
         COUNT(DISTINCT order_id) AS frequency, SUM(sales) AS monetary
  FROM sales GROUP BY customer_id
), customer_rfm AS (
  SELECT customer_id,
         DATEDIFF((SELECT MAX(last_order_date) FROM customer_base) + INTERVAL 1 DAY, last_order_date) AS recency_days,
         frequency, monetary
  FROM customer_base
), scored AS (
  SELECT *, NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
         NTILE(5) OVER (ORDER BY frequency) AS f_score,
         NTILE(5) OVER (ORDER BY monetary) AS m_score
  FROM customer_rfm
)
SELECT customer_id, recency_days, frequency, ROUND(monetary, 2) AS monetary,
       CASE WHEN (r_score + f_score + m_score) / 3 >= 4 THEN 'Champions'
            WHEN (r_score + f_score + m_score) / 3 >= 3 THEN 'Loyal'
            WHEN (r_score + f_score + m_score) / 3 >= 2 THEN 'Potential'
            ELSE 'At Risk' END AS segment
FROM scored ORDER BY monetary DESC;
