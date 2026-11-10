-- Additive persistent-upload migration. Review and execute manually on MySQL 8.0 only.
-- It does not reference or modify the historical `sales` table.
USE retail_sales_db;

CREATE TABLE IF NOT EXISTS uploaded_files (
    id CHAR(36) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_type ENUM('csv', 'xls', 'xlsx', 'xlsm') NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    row_count INT UNSIGNED NOT NULL,
    size_bytes INT UNSIGNED NOT NULL,
    validation_status ENUM('pending', 'valid', 'invalid') NOT NULL DEFAULT 'valid',
    storage_key VARCHAR(512) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_uploaded_files_storage_key (storage_key),
    KEY idx_uploaded_files_user_created (user_id, created_at, id),
    KEY idx_uploaded_files_user_sha256 (user_id, file_sha256),
    CONSTRAINT fk_uploaded_files_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
