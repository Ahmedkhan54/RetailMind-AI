-- Phase 1 single-owner administration and session migration rollback for MySQL 8.0.
-- Review-only: do NOT execute without explicit approval.
-- Deliberately does not reference or modify `sales`.
USE retail_sales_db;

DROP TABLE IF EXISTS user_sessions;
DROP TABLE IF EXISTS owner_admin_assignment;
