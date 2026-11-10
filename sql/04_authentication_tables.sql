-- Phase 2 review-only migration. Do NOT execute until explicitly approved.
-- This migration is additive: it does not modify `sales` or its historical records.
USE retail_sales_db;

CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(32) NULL,
    password_hash VARCHAR(255) NOT NULL,
    account_status ENUM('active', 'inactive') NOT NULL DEFAULT 'active',
    session_version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email),
    KEY idx_users_account_status (account_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE upload_history (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    row_count INT UNSIGNED NULL,
    upload_status ENUM('received', 'processed', 'failed') NOT NULL DEFAULT 'received',
    validation_status ENUM('pending', 'valid', 'invalid') NOT NULL DEFAULT 'pending',
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_upload_history_user_uploaded (user_id, uploaded_at),
    KEY idx_upload_history_sha256 (file_sha256),
    CONSTRAINT fk_upload_history_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE sales_goals (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    goal_name VARCHAR(150) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    target_sales DECIMAL(14,2) NOT NULL,
    target_profit DECIMAL(14,2) NULL,
    target_category VARCHAR(100) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sales_goals_user_name_period (user_id, goal_name, period_start, period_end),
    KEY idx_sales_goals_user_period (user_id, period_start, period_end),
    CONSTRAINT ck_sales_goals_period CHECK (period_end >= period_start),
    CONSTRAINT ck_sales_goals_target_sales CHECK (target_sales >= 0),
    CONSTRAINT ck_sales_goals_target_profit CHECK (target_profit IS NULL OR target_profit >= 0),
    CONSTRAINT fk_sales_goals_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE audit_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    event_type VARCHAR(64) NOT NULL,
    status ENUM('success', 'failure', 'info') NOT NULL DEFAULT 'info',
    event_details JSON NULL,
    ip_address VARBINARY(16) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_audit_logs_user_created (user_id, created_at),
    KEY idx_audit_logs_event_created (event_type, created_at),
    CONSTRAINT fk_audit_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE saved_reports (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    report_name VARCHAR(150) NOT NULL,
    report_type VARCHAR(64) NOT NULL,
    filter_config JSON NOT NULL COMMENT 'Dashboard filter snapshot only: date_range, categories, cities, products, regions, customers, sales_reps, payment_methods, order_ids, numeric_ranges.',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_saved_reports_user_name (user_id, report_name),
    KEY idx_saved_reports_user_type (user_id, report_type),
    KEY idx_saved_reports_user_updated (user_id, updated_at),
    CONSTRAINT fk_saved_reports_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE user_preferences (
    user_id BIGINT UNSIGNED NOT NULL,
    preferences JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_user_preferences_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
