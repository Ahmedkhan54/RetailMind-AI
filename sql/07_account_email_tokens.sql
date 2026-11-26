-- Additive migration for password reset and email-verification tokens.
-- Review and run once in the target MySQL database before deploying these endpoints.
USE retail_sales_db;

ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP NULL DEFAULT NULL AFTER last_login_at;

CREATE TABLE account_action_tokens (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    token_hash CHAR(64) NOT NULL,
    purpose ENUM('password_reset', 'email_verification') NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_account_action_tokens_hash (token_hash),
    KEY idx_account_action_tokens_user_purpose (user_id, purpose, created_at),
    KEY idx_account_action_tokens_lookup (token_hash, purpose, expires_at, used_at),
    CONSTRAINT fk_account_action_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
