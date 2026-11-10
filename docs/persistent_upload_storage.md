# Persistent user upload storage

`uploaded_files` is an additive MySQL 8.0 table created by `sql/05_persistent_user_uploads.sql`. It stores an opaque
upload ID, authenticated owner ID, filename/type/checksum/row-count metadata, and an opaque relative storage key. It
does not store file contents, passwords, credentials, or tokens.

Configure `RETAIL_UPLOAD_STORAGE_DIR` to a server-only directory outside the repository, static web roots, and
temporary directories. The service writes validated files as `<user-id>/<uuid>.<extension>` and validates both the
database owner predicate and resolved filesystem path before every open, download, or delete.

## Manual deployment and recovery

1. Back up `retail_sales_db` and take a filesystem snapshot of the configured upload root.
2. Verify the server is MySQL 8.0. Before migration 04, inspect the six required tables: `users`, `upload_history`,
   `sales_goals`, `audit_logs`, `saved_reports`, and `user_preferences`. Record whether they are all absent, all
   present with the reviewed definition, or partially/inconsistently present. Do not rerun migration 04 when any are
   present; stop and prepare a schema-specific repair plan after an approved schema inspection.
3. Apply `sql/05_persistent_user_uploads.sql` manually after the authentication tables exist.
4. Verify only the new `uploaded_files` table, keys, and foreign key. Do not run `load_to_mysql.py` or any command
   that changes `sales`.
5. There is intentionally no automatic filesystem rollback. To retire this feature, first back up retained files,
   disable writes, remove database records only after confirming their ownership and retention status, and remove only
   matching opaque files from the configured upload root. Never include `sales` in the operation.

## Deployment configuration

Set `RETAIL_UPLOAD_STORAGE_DIR` to a durable, access-controlled filesystem directory outside public/static paths.
The Docker Compose configuration mounts the named `retail_user_uploads` volume at `/var/lib/retail-user-uploads`; it
survives ordinary container recreation and `docker compose down` (but not `docker compose down --volumes`). Back up
that volume separately from MySQL. For production, use a managed persistent volume or host mount with access limited
to the dashboard service account.
