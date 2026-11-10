"""Database-backed authentication using Argon2id and parameterised SQL only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
import secrets
from typing import Callable, Protocol
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSWORD_HASHER = PasswordHasher()  # argon2-cffi defaults use Argon2id.
OWNER_ADMIN_ROLE = "owner_admin"
USER_ROLE = "user"
SAFE_AUDIT_EVENTS = frozenset({
    "account_registered", "login_succeeded", "login_failed", "logout", "session_created",
    "session_revoked", "session_expired", "dashboard_accessed", "filters_applied",
    "upload_validated", "upload_recorded", "persistent_upload_created", "upload_downloaded",
    "persistent_upload_deleted", "report_generated", "report_downloaded", "report_saved",
    "report_deleted", "goal_saved", "goal_deleted", "profile_updated", "password_changed",
    "owner_admin_dashboard_accessed", "owner_admin_assigned",
})
_PROFILE_FIELDS = (
    "id", "email", "full_name", "phone", "account_status", "session_version",
    "created_at", "last_login_at",
)


class Cursor(Protocol):
    def execute(self, query: str, params: tuple = ()) -> None: ...
    def fetchone(self): ...
    def close(self) -> None: ...


class Connection(Protocol):
    def cursor(self, **kwargs) -> Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class AuthenticationError(Exception):
    """A user-safe authentication failure."""


@dataclass(frozen=True)
class UserProfile:
    id: int
    email: str
    full_name: str
    phone: str | None
    account_status: str
    session_version: int
    created_at: object
    last_login_at: object


@dataclass(frozen=True)
class UserSession:
    id: str
    secret: str
    expires_at: datetime


def normalise_email(email: str) -> str:
    return email.strip().casefold()


def _validate_registration(full_name: str, email: str, password: str) -> None:
    if not full_name.strip() or len(full_name.strip()) > 150:
        raise AuthenticationError("Enter a name of up to 150 characters.")
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(normalise_email(email)):
        raise AuthenticationError("Enter a valid email address.")
    if len(password) < 12:
        raise AuthenticationError("Password must contain at least 12 characters.")


class AuthService:
    """All writes use one short transaction and all queries use MySQL placeholders."""

    def __init__(self, connection_factory: Callable[[], Connection]):
        self._connection_factory = connection_factory

    @staticmethod
    def _profile(row) -> UserProfile:
        payload = dict(row)
        return UserProfile(**{field: payload.get(field) for field in _PROFILE_FIELDS})

    def _audit(self, cursor: Cursor, user_id: int | None, event: str, status: str = "success") -> None:
        cursor.execute(
            "INSERT INTO audit_logs (user_id, event_type, status, event_details) VALUES (%s, %s, %s, %s)",
            (user_id, event, status, json.dumps({})),
        )

    def record_activity(self, user_id: int | None, event: str, status: str = "success") -> None:
        """Append a named, metadata-free audit event; never accepts secrets/details."""
        if event not in SAFE_AUDIT_EVENTS or status not in {"success", "failure", "info"}:
            raise ValueError("Unsupported audit event.")
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._audit(cursor, user_id, event, status)
            connection.commit()
        except Exception as error:
            connection.rollback(); logger.exception("Activity audit write failed")
            raise AuthenticationError("Activity tracking is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def record_login_failure(self, email: str) -> None:
        """Record a failed attempt without persisting a password or email address."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE email = %s", (normalise_email(email),))
            row = cursor.fetchone()
            self._audit(cursor, row["id"] if row else None, "login_failed", "failure")
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("Login-failure audit write failed")
        finally:
            cursor.close(); connection.close()

    def get_current_role(self, user_id: int) -> str:
        """Reload role from the database; all unassigned accounts are normal users."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT 1 FROM users u INNER JOIN owner_admin_assignment o ON o.user_id = u.id WHERE u.id = %s AND u.account_status = 'active'",
                (user_id,),
            )
            return OWNER_ADMIN_ROLE if cursor.fetchone() else USER_ROLE
        finally:
            cursor.close(); connection.close()

    def is_owner_admin(self, user_id: int) -> bool:
        return self.get_current_role(user_id) == OWNER_ADMIN_ROLE

    def require_owner_admin(self, user_id: int) -> None:
        """Server-side guard for every future admin service/UI action."""
        if not self.is_owner_admin(user_id):
            raise AuthenticationError("Owner administrator access is required.")

    def _require_owner_on_cursor(self, cursor: Cursor, user_id: int) -> None:
        cursor.execute(
            "SELECT 1 FROM users u INNER JOIN owner_admin_assignment o ON o.user_id = u.id WHERE u.id = %s AND u.account_status = 'active'",
            (user_id,),
        )
        if cursor.fetchone() is None:
            raise AuthenticationError("Owner administrator access is required.")

    def list_owner_accounts(self, actor_user_id: int) -> list[dict]:
        """Owner-only account directory. Password hashes are never selected."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._require_owner_on_cursor(cursor, actor_user_id)
            cursor.execute(
                "SELECT u.id, u.email, u.full_name, u.account_status, u.created_at, u.last_login_at, "
                "CASE WHEN o.user_id IS NULL THEN %s ELSE %s END AS assigned_role "
                "FROM users u LEFT JOIN owner_admin_assignment o ON o.user_id = u.id "
                "ORDER BY u.created_at DESC, u.id DESC",
                (USER_ROLE, OWNER_ADMIN_ROLE),
            )
            return [dict(row) for row in cursor.fetchall()]
        except AuthenticationError:
            raise
        except Exception as error:
            logger.exception("Owner account listing failed")
            raise AuthenticationError("Owner monitoring is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def list_owner_sessions(self, actor_user_id: int) -> list[dict]:
        """Owner-only session inventory. Session secrets and hashes are never selected."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._require_owner_on_cursor(cursor, actor_user_id)
            cursor.execute(
                "SELECT s.id, s.user_id, u.email, s.created_at, s.last_activity_at, s.expires_at, s.revoked_at "
                "FROM user_sessions s INNER JOIN users u ON u.id = s.user_id "
                "ORDER BY s.last_activity_at DESC, s.id DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
        except AuthenticationError:
            raise
        except Exception as error:
            logger.exception("Owner session listing failed")
            raise AuthenticationError("Owner monitoring is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def list_owner_audit_events(self, actor_user_id: int, event_type: str | None = None, limit: int = 200) -> list[dict]:
        """Owner-only audit feed. Event details, IPs, hashes, and secrets are never selected."""
        if event_type is not None and event_type not in SAFE_AUDIT_EVENTS:
            raise AuthenticationError("Unsupported audit event.")
        limit = max(1, min(int(limit), 500))
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._require_owner_on_cursor(cursor, actor_user_id)
            if event_type:
                cursor.execute(
                    "SELECT id, user_id, event_type, status, created_at FROM audit_logs "
                    "WHERE event_type = %s ORDER BY created_at DESC, id DESC LIMIT %s",
                    (event_type, limit),
                )
            else:
                cursor.execute(
                    "SELECT id, user_id, event_type, status, created_at FROM audit_logs "
                    "ORDER BY created_at DESC, id DESC LIMIT %s",
                    (limit,),
                )
            return [dict(row) for row in cursor.fetchall()]
        except AuthenticationError:
            raise
        except Exception as error:
            logger.exception("Owner audit listing failed")
            raise AuthenticationError("Owner monitoring is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def list_owner_event_counts(self, actor_user_id: int) -> list[dict]:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._require_owner_on_cursor(cursor, actor_user_id)
            cursor.execute(
                "SELECT event_type, status, COUNT(*) AS event_count FROM audit_logs "
                "GROUP BY event_type, status ORDER BY event_type, status"
            )
            return [dict(row) for row in cursor.fetchall()]
        except AuthenticationError:
            raise
        except Exception as error:
            logger.exception("Owner audit summary failed")
            raise AuthenticationError("Owner monitoring is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def has_owner_admin(self) -> bool:
        """Check whether an owner administrator has been assigned."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT 1 FROM owner_admin_assignment WHERE singleton = 1")
            return cursor.fetchone() is not None
        except Exception as error:
            logger.exception("Owner status check failed")
            raise AuthenticationError("Owner status is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def get_assigned_owner_admin(self) -> dict | None:
        """Fetch the current owner administrator profile (excluding secrets/hashes)."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT u.id, u.email, u.full_name, u.account_status, o.assigned_at "
                "FROM owner_admin_assignment o INNER JOIN users u ON u.id = o.user_id "
                "WHERE o.singleton = 1"
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as error:
            logger.exception("Owner lookup failed")
            raise AuthenticationError("Owner details are temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def revoke_session_as_owner(self, actor_user_id: int, session_id: str) -> None:
        """Owner-only revocation of any active user session."""
        try:
            UUID(session_id)
        except (ValueError, TypeError) as error:
            raise AuthenticationError("Session is unavailable.") from error
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._require_owner_on_cursor(cursor, actor_user_id)
            cursor.execute("SELECT user_id FROM user_sessions WHERE id = %s AND revoked_at IS NULL", (session_id,))
            session_row = cursor.fetchone()
            if not session_row:
                raise AuthenticationError("Session is unavailable.")
            target_user_id = session_row["user_id"]
            cursor.execute("UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE id = %s AND revoked_at IS NULL", (session_id,))
            self._audit(cursor, target_user_id, "session_revoked", "info")
            connection.commit()
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Owner session revocation failed")
            raise AuthenticationError("Session is unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def assign_initial_owner_admin(self, user_id: int) -> None:
        """Controlled bootstrap only; this method is deliberately not exposed by UI."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE id = %s AND account_status = 'active'", (user_id,))
            if not cursor.fetchone():
                raise AuthenticationError("The selected account is unavailable.")
            # singleton=1 is the database-enforced one-owner guarantee.
            cursor.execute("INSERT INTO owner_admin_assignment (singleton, user_id) VALUES (1, %s)", (user_id,))
            self._audit(cursor, user_id, "owner_admin_assigned")
            connection.commit()
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Owner bootstrap failed")
            raise AuthenticationError("An owner administrator is already assigned or unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def create_user_session(self, user_id: int, lifetime_seconds: int = 8 * 60 * 60) -> UserSession:
        if lifetime_seconds <= 0 or lifetime_seconds > 7 * 24 * 60 * 60:
            raise AuthenticationError("Invalid session lifetime.")
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, session_version FROM users WHERE id = %s AND account_status = 'active'", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise AuthenticationError("Account is unavailable.")
            session = UserSession(str(uuid4()), secrets.token_urlsafe(32), datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds))
            secret_hash = hashlib.sha256(session.secret.encode("utf-8")).hexdigest()
            cursor.execute(
                "INSERT INTO user_sessions (id, user_id, session_secret_hash, session_version, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (session.id, user_id, secret_hash, user["session_version"], session.expires_at.replace(tzinfo=None)),
            )
            self._audit(cursor, user_id, "session_created")
            connection.commit()
            return session
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Session creation failed")
            raise AuthenticationError("Sign-in is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def validate_user_session(self, session_id: str, secret: str) -> UserProfile:
        """Validate a hashed bearer secret plus live account/session-version state."""
        try:
            UUID(session_id)
        except (ValueError, TypeError) as error:
            raise AuthenticationError("Session is unavailable.") from error
        secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT u.id, u.email, u.full_name, u.phone, u.account_status, u.session_version, u.created_at, u.last_login_at, s.expires_at, s.revoked_at, s.session_version AS stored_session_version FROM user_sessions s INNER JOIN users u ON u.id = s.user_id WHERE s.id = %s AND s.session_secret_hash = %s",
                (session_id, secret_hash),
            )
            row = cursor.fetchone()
            if not row or row["revoked_at"] is not None or row["account_status"] != "active" or row["stored_session_version"] != row["session_version"]:
                raise AuthenticationError("Session is unavailable.")
            expires_at = row["expires_at"]
            if isinstance(expires_at, datetime):
                now = datetime.now(timezone.utc) if expires_at.tzinfo is not None else datetime.now(timezone.utc).replace(tzinfo=None)
                is_expired = expires_at <= now
            else:
                is_expired = False
            if is_expired:
                cursor.execute("UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE id = %s AND revoked_at IS NULL", (session_id,))
                self._audit(cursor, row["id"], "session_expired", "info")
                connection.commit()
                raise AuthenticationError("Session has expired. Please sign in again.")
            cursor.execute("UPDATE user_sessions SET last_activity_at = CURRENT_TIMESTAMP WHERE id = %s", (session_id,))
            connection.commit()
            return self._profile(row)
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Session validation failed")
            raise AuthenticationError("Session is unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def revoke_user_session(self, user_id: int, session_id: str) -> None:
        try:
            UUID(session_id)
        except (ValueError, TypeError) as error:
            raise AuthenticationError("Session is unavailable.") from error
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s AND revoked_at IS NULL", (session_id, user_id))
            if not getattr(cursor, "rowcount", 1):
                raise AuthenticationError("Session is unavailable.")
            self._audit(cursor, user_id, "session_revoked", "info")
            connection.commit()
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Session revocation failed")
            raise AuthenticationError("Session is unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def register(self, full_name: str, email: str, phone: str | None, password: str) -> UserProfile:
        _validate_registration(full_name, email, password)
        connection = self._connection_factory()
        cursor = connection.cursor(dictionary=True)
        try:
            normalised = normalise_email(email)
            cursor.execute("SELECT id FROM users WHERE email = %s", (normalised,))
            if cursor.fetchone() is not None:
                raise AuthenticationError("An account with that email already exists.")
            password_hash = PASSWORD_HASHER.hash(password)
            cursor.execute(
                "INSERT INTO users (email, full_name, phone, password_hash) VALUES (%s, %s, %s, %s)",
                (normalised, full_name.strip(), phone.strip() if phone and phone.strip() else None, password_hash),
            )
            cursor.execute("SELECT id, email, full_name, phone, account_status, session_version, created_at, last_login_at FROM users WHERE email = %s", (normalised,))
            row = cursor.fetchone()
            self._audit(cursor, row["id"], "account_registered")
            connection.commit()
            return self._profile(row)
        except AuthenticationError:
            connection.rollback()
            raise
        except Exception as error:
            connection.rollback()
            logger.exception("Registration failed")
            raise AuthenticationError("We could not create the account. Please try again.") from error
        finally:
            cursor.close(); connection.close()

    def login(self, email: str, password: str) -> UserProfile:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, email, full_name, phone, password_hash, account_status, session_version, created_at, last_login_at FROM users WHERE email = %s", (normalise_email(email),))
            row = cursor.fetchone()
            if not row or row["account_status"] != "active":
                raise AuthenticationError("Invalid email or password.")
            try:
                verified = PASSWORD_HASHER.verify(row["password_hash"], password)
            except (VerifyMismatchError, InvalidHashError):
                verified = False
            if not verified:
                raise AuthenticationError("Invalid email or password.")
            cursor.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s", (row["id"],))
            self._audit(cursor, row["id"], "login_succeeded")
            connection.commit()
            row.pop("password_hash", None)
            return self._profile(row)
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Login failed")
            raise AuthenticationError("Sign-in is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def get_profile(self, user_id: int) -> UserProfile:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, email, full_name, phone, account_status, session_version, created_at, last_login_at FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            if not row: raise AuthenticationError("Account is unavailable.")
            return self._profile(row)
        finally:
            cursor.close(); connection.close()

    def update_profile(self, user_id: int, full_name: str, email: str, phone: str | None) -> UserProfile:
        _validate_registration(full_name, email, "x" * 12)
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE email = %s AND id <> %s", (normalise_email(email), user_id))
            if cursor.fetchone(): raise AuthenticationError("An account with that email already exists.")
            cursor.execute("UPDATE users SET full_name = %s, email = %s, phone = %s WHERE id = %s AND account_status = 'active'", (full_name.strip(), normalise_email(email), phone.strip() if phone and phone.strip() else None, user_id))
            if not getattr(cursor, "rowcount", 1): raise AuthenticationError("Account is unavailable.")
            self._audit(cursor, user_id, "profile_updated"); connection.commit()
            return self.get_profile(user_id)
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Profile update failed")
            raise AuthenticationError("We could not update the profile. Please try again.") from error
        finally:
            cursor.close(); connection.close()

    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        _validate_registration("valid", "placeholder@example.com", new_password)
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT password_hash FROM users WHERE id = %s AND account_status = 'active'", (user_id,))
            row = cursor.fetchone()
            try: verified = bool(row) and PASSWORD_HASHER.verify(row["password_hash"], current_password)
            except (VerifyMismatchError, InvalidHashError): verified = False
            if not verified: raise AuthenticationError("Current password is incorrect.")
            # Bumping session_version invalidates all previously issued sessions.
            cursor.execute("UPDATE users SET password_hash = %s, session_version = session_version + 1 WHERE id = %s", (PASSWORD_HASHER.hash(new_password), user_id))
            self._audit(cursor, user_id, "password_changed"); connection.commit()
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Password change failed")
            raise AuthenticationError("We could not change the password. Please try again.") from error
        finally:
            cursor.close(); connection.close()

    def logout(self, user_id: int) -> None:
        """Record a logout using the server-side identity; session clearing is UI-owned."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            self._audit(cursor, user_id, "logout")
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("Logout audit failed")
        finally:
            cursor.close(); connection.close()

    def record_upload(self, user_id: int, filename: str, file_type: str, sha256: str, row_count: int, validation_status: str, upload_status: str = "processed") -> None:
        """Persist metadata only; uploaded bytes are never written to MySQL."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "INSERT INTO upload_history (user_id, original_filename, file_type, file_sha256, row_count, upload_status, validation_status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, filename, file_type, sha256, row_count, upload_status, validation_status),
            )
            self._audit(cursor, user_id, "upload_recorded")
            connection.commit()
        except Exception as error:
            connection.rollback(); logger.exception("Upload metadata write failed")
            raise AuthenticationError("Upload history is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def list_upload_history(self, user_id: int) -> list[dict]:
        """The authenticated identity is mandatory, preventing cross-user reads."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT original_filename, file_type, uploaded_at, row_count, upload_status, validation_status FROM upload_history WHERE user_id = %s ORDER BY uploaded_at DESC, id DESC",
                (user_id,),
            )
            return list(cursor.fetchall())
        except Exception as error:
            logger.exception("Upload history read failed")
            raise AuthenticationError("Upload history is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def create_uploaded_file(self, user_id: int, upload_id: str, filename: str, file_type: str,
                             sha256: str, row_count: int, size_bytes: int, storage_key: str) -> None:
        """Persist only metadata for a file already validated and stored server-side."""
        try:
            UUID(upload_id)
        except (ValueError, TypeError) as error:
            raise AuthenticationError("Uploaded file is unavailable.") from error
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "INSERT INTO uploaded_files (id, user_id, original_filename, file_type, file_sha256, row_count, size_bytes, storage_key) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (upload_id, user_id, filename, file_type, sha256, row_count, size_bytes, storage_key),
            )
            self._audit(cursor, user_id, "persistent_upload_created")
            connection.commit()
        except Exception as error:
            connection.rollback(); logger.exception("Persistent upload metadata write failed")
            raise AuthenticationError("Uploaded file metadata is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def list_uploaded_files(self, user_id: int) -> list[dict]:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, original_filename, file_type, file_sha256, row_count, size_bytes, validation_status, storage_key, created_at FROM uploaded_files WHERE user_id = %s ORDER BY created_at DESC, id DESC",
                (user_id,),
            )
            return list(cursor.fetchall())
        except Exception as error:
            logger.exception("Persistent upload list failed")
            raise AuthenticationError("Uploaded files are temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def get_uploaded_file(self, user_id: int, upload_id: str) -> dict:
        """Fetch one record only when its owner is the authenticated user."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id, original_filename, file_type, file_sha256, row_count, size_bytes, validation_status, storage_key, created_at FROM uploaded_files WHERE id = %s AND user_id = %s",
                (upload_id, user_id),
            )
            record = cursor.fetchone()
            if not record:
                raise AuthenticationError("Uploaded file is unavailable.")
            return dict(record)
        except AuthenticationError:
            raise
        except Exception as error:
            logger.exception("Persistent upload read failed")
            raise AuthenticationError("Uploaded file is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def delete_uploaded_file(self, user_id: int, upload_id: str) -> None:
        """Delete metadata with an owner predicate; caller removes only the returned owned path."""
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("DELETE FROM uploaded_files WHERE id = %s AND user_id = %s", (upload_id, user_id))
            if not getattr(cursor, "rowcount", 1):
                raise AuthenticationError("Uploaded file is unavailable.")
            self._audit(cursor, user_id, "persistent_upload_deleted")
            connection.commit()
        except AuthenticationError:
            connection.rollback(); raise
        except Exception as error:
            connection.rollback(); logger.exception("Persistent upload delete failed")
            raise AuthenticationError("Uploaded file could not be deleted.") from error
        finally:
            cursor.close(); connection.close()

    def list_goals(self, user_id: int) -> list[dict]:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, goal_name, period_start, period_end, target_sales, target_profit, target_category FROM sales_goals WHERE user_id = %s ORDER BY period_start DESC, id DESC", (user_id,))
            return list(cursor.fetchall())
        finally:
            cursor.close(); connection.close()

    def save_goal(self, user_id: int, goal: dict) -> None:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            if goal.get("id"):
                cursor.execute("UPDATE sales_goals SET goal_name=%s, period_start=%s, period_end=%s, target_sales=%s, target_profit=%s, target_category=%s WHERE id=%s AND user_id=%s", (goal["goal_name"], goal["period_start"], goal["period_end"], goal["target_sales"], goal.get("target_profit"), goal.get("target_category"), goal["id"], user_id))
            else:
                cursor.execute("INSERT INTO sales_goals (user_id, goal_name, period_start, period_end, target_sales, target_profit, target_category) VALUES (%s,%s,%s,%s,%s,%s,%s)", (user_id, goal["goal_name"], goal["period_start"], goal["period_end"], goal["target_sales"], goal.get("target_profit"), goal.get("target_category")))
            self._audit(cursor, user_id, "goal_saved"); connection.commit()
        except Exception as error:
            connection.rollback(); raise AuthenticationError("Goal storage is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def delete_goal(self, user_id: int, goal_id: int) -> None:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("DELETE FROM sales_goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
            self._audit(cursor, user_id, "goal_deleted"); connection.commit()
        except Exception as error:
            connection.rollback(); raise AuthenticationError("Goal storage is temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def save_report(self, user_id: int, report_name: str, report_type: str, filter_config: str) -> None:
        if not report_name.strip() or len(report_name.strip()) > 150:
            raise AuthenticationError("Enter a report name of up to 150 characters.")
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("INSERT INTO saved_reports (user_id, report_name, report_type, filter_config) VALUES (%s, %s, %s, %s)", (user_id, report_name.strip(), report_type, filter_config))
            self._audit(cursor, user_id, "report_saved"); connection.commit()
        except Exception as error:
            connection.rollback(); raise AuthenticationError("Report metadata could not be saved.") from error
        finally:
            cursor.close(); connection.close()

    def list_reports(self, user_id: int) -> list[dict]:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, report_name, report_type, filter_config, created_at FROM saved_reports WHERE user_id = %s ORDER BY created_at DESC, id DESC", (user_id,))
            return list(cursor.fetchall())
        finally:
            cursor.close(); connection.close()

    def delete_report(self, user_id: int, report_id: int) -> None:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("DELETE FROM saved_reports WHERE id = %s AND user_id = %s", (report_id, user_id))
            self._audit(cursor, user_id, "report_deleted"); connection.commit()
        except Exception as error:
            connection.rollback(); raise AuthenticationError("Report metadata could not be deleted.") from error
        finally:
            cursor.close(); connection.close()

    def get_preferences(self, user_id: int) -> dict:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT preferences FROM user_preferences WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if not row:
                return {"currency": "INR", "date_format": "DD MMM YYYY", "default_period": "30d", "compact_mode": False}
            preferences = row.get("preferences") if isinstance(row, dict) else None
            if isinstance(preferences, str):
                preferences = json.loads(preferences)
            return dict(preferences) if isinstance(preferences, dict) else {"currency": "INR", "date_format": "DD MMM YYYY", "default_period": "30d", "compact_mode": False}
        except Exception as error:
            logger.exception("Preference read failed")
            raise AuthenticationError("Preferences are temporarily unavailable.") from error
        finally:
            cursor.close(); connection.close()

    def save_preferences(self, user_id: int, preferences: dict) -> None:
        connection = self._connection_factory(); cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "INSERT INTO user_preferences (user_id, preferences) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE preferences = VALUES(preferences)",
                (user_id, json.dumps(preferences, separators=(",", ":"), ensure_ascii=False)),
            )
            connection.commit()
        except Exception as error:
            connection.rollback(); logger.exception("Preference write failed")
            raise AuthenticationError("Preferences could not be saved.") from error
        finally:
            cursor.close(); connection.close()
