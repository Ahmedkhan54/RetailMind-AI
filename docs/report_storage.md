# Report metadata and file storage

`saved_reports` stores report metadata and a JSON snapshot of dashboard filters. It does not store report files, paths, URLs, object-store credentials, or file contents.

Secure PDF/Excel generation and storage are not implemented in Phase 2. A future implementation must keep generated files in an access-controlled storage service, encrypt data in transit and at rest, use opaque object keys, verify `user_id` ownership before issuing a short-lived download URL, and define retention/deletion rules. Until then, the application must not claim that saved report files can be re-downloaded.

Every future user-scoped query must take the authenticated server-side user ID, include it in its `WHERE` clause (for example, `WHERE id = %s AND user_id = %s`), and never accept a user ID from a browser widget, URL, or uploaded configuration.
