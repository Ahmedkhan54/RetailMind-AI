CREATE DATABASE IF NOT EXISTS retail_sales_db;
USE retail_sales_db;

CREATE TABLE IF NOT EXISTS sales (
    order_id VARCHAR(20) PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_id INT NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    city VARCHAR(80) NOT NULL,
    region VARCHAR(30) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    discount_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
    sales DECIMAL(14,2) NOT NULL,
    profit DECIMAL(14,2) NOT NULL,
    payment_method VARCHAR(40) NOT NULL,
    CHECK (quantity > 0),
    CHECK (unit_price >= 0),
    CHECK (discount_pct >= 0 AND discount_pct <= 1)
);
