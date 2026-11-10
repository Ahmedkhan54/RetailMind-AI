-- Rollback for Phase 2 tables only. Do NOT execute without approval.
-- This deliberately does not reference or alter `sales`.
USE retail_sales_db;
DROP TABLE IF EXISTS user_preferences;
DROP TABLE IF EXISTS saved_reports;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS sales_goals;
DROP TABLE IF EXISTS upload_history;
DROP TABLE IF EXISTS users;
