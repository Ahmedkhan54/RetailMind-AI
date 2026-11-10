-- Phase 1 single-owner administration and session migration for MySQL 8.0.
-- Additive only: this file does not reference or modify `sales`.
-- Do not execute until migration 04 has been reviewed and applied completely.
USE retail_sales_db;

-- Exactly one row is possible because singleton is the primary key. Every
-- account not referenced here is implicitly a normal `user`; signup cannot
-- select a role and this migration intentionally does not seed an owner.
CREATE TABLE IF NOT EXISTS owner_admin_assignment (
    singleton TINYINT UNSIGNED NOT NULL DEFAULT 1,
    user_id BIGINT UNSIGNED NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (singleton),
    UNIQUE KEY uq_owner_admin_user (user_id),
    CONSTRAINT ck_owner_admin_singleton CHECK (singleton = 1),
    CONSTRAINT fk_owner_admin_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS user_sessions (
    id CHAR(36) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    session_secret_hash CHAR(64) NOT NULL,
    session_version INT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_user_sessions_secret_hash (session_secret_hash),
    KEY idx_user_sessions_user_active (user_id, revoked_at, expires_at),
    KEY idx_user_sessions_expiry (expires_at),
    CONSTRAINT fk_user_sessions_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Manual operator steps after this file is reviewed and applied (do not auto-seed):
-- 1. Confirm migrations 04 and 05 already exist; do not rerun them.
-- 2. Confirm `sales` was not referenced by this file.
-- 3. Create the owner account through the normal registration path (role is always `user`).
-- 4. Assign that existing `users.id` exactly once:
--    INSERT INTO owner_admin_assignment (singleton, user_id) VALUES (1, <existing-user-id>);
-- 5. Public signup must remain role-free. Do not grant owner access from the UI.
