# Owner Administrator and Hashed Sessions

This feature implements a strict single-owner control plane and database-backed session management for the Retail Sales Profitability application.

> [!NOTE]
> This control plane is designed for single-operator administrative oversight. It is additive to the schema and does not touch or reference the historical `sales` table. Automated coverage is mocked and isolated from live database instances.

---

## Architectural Principles

1. **Database-Enforced Singleton Owner**:
   - The table `owner_admin_assignment` defines `singleton TINYINT UNSIGNED NOT NULL DEFAULT 1 PRIMARY KEY` with `CONSTRAINT ck_owner_admin_singleton CHECK (singleton = 1)`.
   - This database-level invariant guarantees that at most **one** row can exist across the entire table.
   - Any attempt to assign a second owner fails with a Primary Key duplicate entry error (`1062`) or Check constraint violation (`3819`).
   - Foreign key constraint `CONSTRAINT fk_owner_admin_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT` ensures only active, valid user records can be assigned, and the owner user record cannot be deleted while assigned.
   - All accounts not referenced in `owner_admin_assignment` are implicitly standard users (`USER_ROLE = "user"`).

2. **Role-Free Public Registration**:
   - `AuthService.register()` accepts only `full_name`, `email`, `phone`, and `password`. It takes no role argument and assigns no privileges.
   - The UI registration form contains no role picker. All signups create ordinary user accounts with `account_status = 'active'` and default `session_version = 1`.

3. **Server-Side Authorization**:
   - Role evaluation is re-queried against MySQL on every privileged request (`_require_owner_on_cursor`), ensuring that privilege changes take immediate effect.
   - Client-side session state or form parameters can never grant or elevate administrative access.
   - Owner monitoring endpoints (`list_owner_accounts`, `list_owner_sessions`, `list_owner_audit_events`, `list_owner_event_counts`, `revoke_session_as_owner`) exclude all sensitive attributes: password hashes, session bearer secrets, session secret hashes, IP addresses, and event details are never returned.

4. **Hashed Server-Side Sessions**:
   - The `user_sessions` table persists bearer secrets only as SHA-256 digests (`session_secret_hash CHAR(64) UNIQUE`).
   - The plaintext bearer token is generated using `secrets.token_urlsafe(32)` and returned to the application/browser context; it is never stored in the database.
   - Each session tracks `created_at`, sliding `last_activity_at`, `expires_at`, and `revoked_at`.
   - Session validation verifies that `account_status = 'active'`, `revoked_at IS NULL`, `expires_at > NOW()`, and `stored_session_version == user.session_version`.
   - Password changes increment `users.session_version`, instantaneously invalidating all active sessions issued prior to the change.

5. **Sanitized Audit Trail**:
   - Named audit events (`SAFE_AUDIT_EVENTS`) log lifecycle events: registrations, successful/failed logins, logouts, session creation, revocation, expiry, profile updates, password changes, owner assignments, and dashboard access.
   - Audit entries record `user_id`, `event_type`, `status`, and empty JSON details (`{}`). Passwords, emails on failure, session tokens, and sales records are never written to audit logs.

---

## First-Owner Bootstrap Procedure

Owner assignment is intentionally excluded from the public UI. Follow this step-by-step procedure to bootstrap the initial owner administrator in a controlled environment.

### Step 1: Pre-requisites & Verification
1. Ensure a full backup of `retail_sales_db` exists.
2. Confirm migrations `04_authentication_tables.sql` and `05_persistent_user_uploads.sql` have already been reviewed and applied.
3. Confirm MySQL version is 8.0.16 or higher (required for enforced CHECK constraints).
4. Review `sql/06_owner_admin_and_sessions.sql`. Verify that the migration is purely additive and does not reference or alter `sales`.

### Step 2: Apply Migration 06
Apply the schema migration during an authorized change window:
```sql
USE retail_sales_db;
-- Source sql/06_owner_admin_and_sessions.sql
```
Verify the tables were created:
```sql
SHOW TABLES LIKE '%owner%';
SHOW TABLES LIKE 'user_sessions';
```

### Step 3: Register the Initial Owner Account
Create the administrator account through the standard public registration path (UI or service). For example, register `admin@example.com` with a strong password (minimum 12 characters).
At this point, the account exists in `users` as a standard user (`assigned_role = 'user'`).

### Step 4: Identify the Target User ID
Look up the `id` of the newly created account:
```sql
SELECT id, email, full_name, account_status, created_at
FROM users
WHERE email = 'admin@example.com';
```
Note the returned integer `id` (e.g. `1`).

### Step 5: Assign Owner Status (Singleton Assignment)

#### Option A: Direct SQL Assignment (Recommended for Operators)
Execute the single assignment statement:
```sql
INSERT INTO owner_admin_assignment (singleton, user_id)
VALUES (1, 1);
```
Optionally, record the audit log entry:
```sql
INSERT INTO audit_logs (user_id, event_type, status, event_details)
VALUES (1, 'owner_admin_assigned', 'success', '{}');
```

#### Option B: Programmatic Service Bootstrap (Script / CLI)
In an isolated administrative maintenance script:
```python
from src.auth.service import AuthService
from src.auth.ui import _connection

service = AuthService(_connection)
service.assign_initial_owner_admin(user_id=1)
```
This method automatically verifies active user status, executes the singleton insert, writes the `owner_admin_assigned` audit event, and commits transactionally.

### Step 6: Verify the Singleton Invariant
Verify that the assignment is active:
```sql
SELECT o.singleton, o.user_id, u.email, u.full_name, o.assigned_at
FROM owner_admin_assignment o
JOIN users u ON u.id = o.user_id;
```

**Verify uniqueness enforcement (Constraint Test):**
1. Attempting to assign another user with `singleton = 1` must fail:
   ```sql
   INSERT INTO owner_admin_assignment (singleton, user_id) VALUES (1, 2);
   -- Expected error: ERROR 1062 (23000): Duplicate entry '1' for key 'owner_admin_assignment.PRIMARY'
   ```
2. Attempting to bypass the singleton with any other value must fail:
   ```sql
   INSERT INTO owner_admin_assignment (singleton, user_id) VALUES (2, 2);
   -- Expected error: ERROR 3819 (HY000): Check constraint 'ck_owner_admin_singleton' is violated.
   ```

### Step 7: Verify Normal Registrations
Register a second user account (e.g. `staff@example.com`).
Verify that the second account is not in `owner_admin_assignment` and that its role evaluates to `user`:
```sql
SELECT u.id, u.email,
       CASE WHEN o.user_id IS NULL THEN 'user' ELSE 'owner_admin' END AS assigned_role
FROM users u
LEFT JOIN owner_admin_assignment o ON o.user_id = u.id
WHERE u.email = 'staff@example.com';
```

### Step 8: Verify Application Access
1. Sign in as `admin@example.com`.
2. Verify that the **Owner monitoring** expander appears in the dashboard sidebar.
3. Verify that registrations, active sessions, and audit events render properly.
4. Sign in as `staff@example.com`.
5. Verify that the Owner monitoring expander is not rendered, and attempting direct service calls raises `AuthenticationError("Owner administrator access is required.")`.

---

## Rollback Plan

If migration 06 must be undone before dependencies are created:
1. Review `sql/06_owner_admin_and_sessions_rollback.sql`.
2. The rollback script executes:
   ```sql
   USE retail_sales_db;
   DROP TABLE IF EXISTS user_sessions;
   DROP TABLE IF EXISTS owner_admin_assignment;
   ```
3. Never execute the rollback script against a database containing active production sessions without taking an offline snapshot first.
4. The historical `sales` table remains untouched regardless of rollback execution.

---

## Security Considerations & Limitations

- **Session Secrets in Memory**: Streamlit server state retains the plaintext bearer secret in memory for the duration of the web session.
- **Hashing Algorithm**: Session tokens use SHA-256 hashing. Passwords use Argon2id via `argon2-cffi`.
- **Rate Limiting**: Rate limiting and brute-force lockouts must be provided by a reverse proxy or WAF (e.g. Nginx, Cloudflare) in production deployments.
- **Audit Storage**: Audit logs are written to the database `audit_logs` table. For compliance, production environments should mirror logs to a secure, immutable log aggregator / SIEM.
