"""Mocked tests for owner assignment, hashed sessions, authorization, and audit logging.

These tests use an in-memory fake DB-API connection. They do not connect to MySQL,
run SQL files, or touch the `sales` table.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from inspect import signature
from pathlib import Path
import hashlib
import json

import pytest

from src.auth.service import (
    OWNER_ADMIN_ROLE,
    USER_ROLE,
    AuthService,
    AuthenticationError,
    PASSWORD_HASHER,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class QueueCursor:
    def __init__(self, state):
        self.state = state
        self.calls = []
        self.rowcount = 1

    def execute(self, query, params=()):
        if self.state.get("fail_on") and self.state["fail_on"] in query:
            raise RuntimeError("constraint violated")
        self.calls.append((query, params))
        self.last = query

    def fetchone(self):
        queue = self.state.setdefault("fetchone", [])
        return queue.pop(0) if queue else None

    def fetchall(self):
        queue = self.state.setdefault("fetchall", [])
        return queue.pop(0) if queue else []

    def close(self):
        pass


class QueueConnection:
    def __init__(self, state):
        self.state = state
        self.cursor_obj = QueueCursor(state)
        self.committed = False
        self.rolled_back = False

    def cursor(self, **kwargs):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def make_service(state=None):
    state = state or {}
    connection = QueueConnection(state)
    return AuthService(lambda: connection), connection


def user_row(**overrides):
    row = dict(
        id=7, email="ada@example.com", full_name="Ada", phone=None,
        account_status="active", session_version=1,
        created_at=datetime.now(), last_login_at=None,
    )
    row.update(overrides)
    return row


def test_register_signature_has_no_role_and_inserts_only_user_fields():
    assert "role" not in signature(AuthService.register).parameters
    service, connection = make_service({"fetchone": [None, user_row()]})
    profile = service.register("Ada", "Ada@Example.com", None, "a secure password")
    insert = next(query for query, _ in connection.cursor_obj.calls if query.startswith("INSERT INTO users"))
    assert "role" not in insert.lower()
    assert profile.email == "ada@example.com"
    audit = next(params for query, params in connection.cursor_obj.calls if "INSERT INTO audit_logs" in query)
    assert audit[1] == "account_registered"
    assert json.loads(audit[3]) == {}


def test_unassigned_accounts_are_normal_users():
    service, _connection = make_service({"fetchone": [None]})
    assert service.get_current_role(7) == USER_ROLE
    assert service.is_owner_admin(7) is False
    with pytest.raises(AuthenticationError, match="Owner administrator"):
        service.require_owner_admin(7)


def test_assigned_active_account_is_owner_admin():
    service, _connection = make_service({"fetchone": [{"ok": 1}, {"ok": 1}]})
    assert service.get_current_role(7) == OWNER_ADMIN_ROLE
    service.require_owner_admin(7)


def test_assign_initial_owner_uses_singleton_row():
    service, connection = make_service({"fetchone": [{"id": 7}]})
    service.assign_initial_owner_admin(7)
    insert = next(params for query, params in connection.cursor_obj.calls if "INSERT INTO owner_admin_assignment" in query)
    assert insert == (7,)
    assert any("VALUES (1, %s)" in query for query, _ in connection.cursor_obj.calls)
    assert connection.committed


def test_second_owner_assignment_is_rejected():
    service, connection = make_service({"fetchone": [{"id": 8}], "fail_on": "INSERT INTO owner_admin_assignment"})
    with pytest.raises(AuthenticationError, match="already assigned"):
        service.assign_initial_owner_admin(8)
    assert connection.rolled_back and not connection.committed


def test_owner_monitoring_denied_for_normal_user():
    service, connection = make_service({"fetchone": [None]})
    with pytest.raises(AuthenticationError, match="Owner administrator"):
        service.list_owner_accounts(7)
    with pytest.raises(AuthenticationError, match="Owner administrator"):
        service.list_owner_sessions(7)
    with pytest.raises(AuthenticationError, match="Owner administrator"):
        service.list_owner_audit_events(7)
    with pytest.raises(AuthenticationError, match="Owner administrator"):
        service.list_owner_event_counts(7)
    assert not any("FROM audit_logs" in query and "GROUP BY" in query for query, _ in connection.cursor_obj.calls)


def test_owner_monitoring_queries_omit_secrets_and_hashes():
    accounts = [{"id": 7, "email": "ada@example.com", "full_name": "Ada", "account_status": "active",
                 "created_at": "now", "last_login_at": None, "assigned_role": OWNER_ADMIN_ROLE}]
    sessions = [{"id": "11111111-1111-1111-1111-111111111111", "user_id": 7, "email": "ada@example.com",
                 "created_at": "now", "last_activity_at": "now", "expires_at": "later", "revoked_at": None}]
    events = [{"id": 1, "user_id": 7, "event_type": "login_succeeded", "status": "success", "created_at": "now"}]
    counts = [{"event_type": "login_succeeded", "status": "success", "event_count": 1}]
    service, connection = make_service({
        "fetchone": [{"ok": 1}, {"ok": 1}, {"ok": 1}, {"ok": 1}],
        "fetchall": [accounts, sessions, events, counts],
    })
    assert service.list_owner_accounts(7) == accounts
    assert service.list_owner_sessions(7) == sessions
    assert service.list_owner_audit_events(7, "login_succeeded") == events
    assert service.list_owner_event_counts(7) == counts
    combined = " ".join(query for query, _ in connection.cursor_obj.calls)
    assert "password_hash" not in combined
    assert "session_secret" not in combined
    assert "event_details" not in combined
    assert "ip_address" not in combined


def test_session_secret_is_hashed_before_storage():
    service, connection = make_service({"fetchone": [{"id": 7, "session_version": 1}]})
    session = service.create_user_session(7)
    insert = next((query, params) for query, params in connection.cursor_obj.calls if "INSERT INTO user_sessions" in query)
    query, params = insert
    secret_hash = hashlib.sha256(session.secret.encode("utf-8")).hexdigest()
    assert params == (session.id, 7, secret_hash, 1, session.expires_at.replace(tzinfo=None))
    assert session.secret not in params
    assert "session_secret_hash" in query
    assert connection.committed


def test_validate_user_session_accepts_matching_hash_and_ignores_join_columns():
    secret = "unit-test-session-secret"
    row = user_row()
    row.update({
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        "revoked_at": None,
        "stored_session_version": 1,
        "session_secret_hash": "should-not-be-copied",
    })
    service, connection = make_service({"fetchone": [row]})
    profile = service.validate_user_session("11111111-1111-1111-1111-111111111111", secret)
    assert profile.id == 7 and profile.email == "ada@example.com"
    query, params = connection.cursor_obj.calls[0]
    assert params[1] == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert secret not in params
    assert "session_secret_hash" in query


def test_expired_session_is_revoked_and_rejected():
    row = user_row()
    row.update({
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
        "revoked_at": None,
        "stored_session_version": 1,
    })
    service, connection = make_service({"fetchone": [row]})
    with pytest.raises(AuthenticationError, match="expired"):
        service.validate_user_session("11111111-1111-1111-1111-111111111111", "expired-secret")
    assert any("session_expired" in str(params) for _, params in connection.cursor_obj.calls)
    assert connection.committed


def test_revoked_or_version_mismatch_sessions_are_rejected():
    row = user_row(session_version=2)
    row.update({
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        "revoked_at": None,
        "stored_session_version": 1,
    })
    service, _connection = make_service({"fetchone": [row]})
    with pytest.raises(AuthenticationError, match="unavailable"):
        service.validate_user_session("11111111-1111-1111-1111-111111111111", "stale-secret")


def test_record_activity_rejects_unknown_events_and_stores_empty_details():
    service, connection = make_service()
    with pytest.raises(ValueError, match="Unsupported audit event"):
        service.record_activity(7, "custom_event_with_secret")
    service.record_activity(7, "login_succeeded")
    params = connection.cursor_obj.calls[0][1]
    assert params == (7, "login_succeeded", "success", json.dumps({}))


def test_login_failure_audit_does_not_persist_email_or_password():
    service, connection = make_service({"fetchone": [{"id": 7}]})
    service.record_login_failure("Ada@Example.com")
    select_params = connection.cursor_obj.calls[0][1]
    audit_params = connection.cursor_obj.calls[1][1]
    assert select_params == ("ada@example.com",)
    assert audit_params == (7, "login_failed", "failure", json.dumps({}))
    assert "Ada@Example.com" not in str(audit_params)


def test_public_ui_does_not_expose_owner_bootstrap_or_role_picker():
    ui_source = (PROJECT_ROOT / "src" / "auth" / "ui.py").read_text(encoding="utf-8")
    assert "assign_initial_owner_admin" not in ui_source
    assert "register_role" not in ui_source
    assert "Role selection is not available." in ui_source


def test_owner_sql_is_additive_and_does_not_touch_sales():
    sql = (PROJECT_ROOT / "sql" / "06_owner_admin_and_sessions.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS owner_admin_assignment" in sql
    assert "CREATE TABLE IF NOT EXISTS user_sessions" in sql
    assert "session_secret_hash" in sql
    assert "ALTER TABLE sales" not in sql
    assert "UPDATE sales" not in sql
    assert "DELETE FROM sales" not in sql
    assert "FROM sales" not in sql


def test_login_does_not_store_password_hash_on_profile():
    row = user_row(password_hash=PASSWORD_HASHER.hash("a secure password"))
    service, connection = make_service({"fetchone": [row]})
    profile = service.login("ada@example.com", "a secure password")
    assert profile.id == 7
    assert not hasattr(profile, "password_hash")
    assert any(len(params) > 1 and params[1] == "login_succeeded" for _, params in connection.cursor_obj.calls)


def test_assign_owner_fails_when_user_not_found_or_inactive():
    service, connection = make_service({"fetchone": [None]})
    with pytest.raises(AuthenticationError, match="selected account is unavailable"):
        service.assign_initial_owner_admin(999)
    assert not any("INSERT INTO owner_admin_assignment" in query for query, _ in connection.cursor_obj.calls)


def test_has_owner_admin_and_get_assigned_owner_admin():
    # When no owner assigned
    service_empty, _ = make_service({"fetchone": [None, None]})
    assert service_empty.has_owner_admin() is False
    assert service_empty.get_assigned_owner_admin() is None

    # When owner is assigned
    owner_record = {"id": 7, "email": "admin@example.com", "full_name": "Admin", "account_status": "active", "assigned_at": datetime.now()}
    service_assigned, connection = make_service({"fetchone": [{"ok": 1}, owner_record]})
    assert service_assigned.has_owner_admin() is True
    details = service_assigned.get_assigned_owner_admin()
    assert details == owner_record
    assert "password_hash" not in str(details)
    assert "secret" not in str(details)


def test_migration_06_database_level_singleton_constraints():
    sql = (PROJECT_ROOT / "sql" / "06_owner_admin_and_sessions.sql").read_text(encoding="utf-8")
    assert "singleton TINYINT UNSIGNED NOT NULL DEFAULT 1" in sql
    assert "PRIMARY KEY (singleton)" in sql
    assert "CONSTRAINT ck_owner_admin_singleton CHECK (singleton = 1)" in sql
    assert "UNIQUE KEY uq_owner_admin_user (user_id)" in sql
    assert "CONSTRAINT fk_owner_admin_user FOREIGN KEY (user_id)" in sql
    assert "REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT" in sql
    assert "ENGINE=InnoDB" in sql
    assert "COLLATE=utf8mb4_0900_ai_ci" in sql
    assert "session_secret_hash CHAR(64) NOT NULL" in sql
    assert "UNIQUE KEY uq_user_sessions_secret_hash (session_secret_hash)" in sql


def test_registered_user_is_never_owner_by_default():
    service, connection = make_service({"fetchone": [None, user_row(email="user@example.com"), None, None]})
    profile = service.register("Regular User", "user@example.com", None, "secure_password_123")
    assert profile.email == "user@example.com"
    # Unassigned role check
    role = service.get_current_role(profile.id)
    assert role == USER_ROLE
    assert service.is_owner_admin(profile.id) is False
    with pytest.raises(AuthenticationError, match="Owner administrator access is required"):
        service.require_owner_admin(profile.id)


def test_inactive_owner_is_denied_owner_access():
    # If the user is referenced in owner_admin_assignment, but account_status != 'active',
    # the join with account_status = 'active' returns None.
    service, _ = make_service({"fetchone": [None]})
    assert service.get_current_role(7) == USER_ROLE
    assert service.is_owner_admin(7) is False
    with pytest.raises(AuthenticationError, match="Owner administrator"):
        service.require_owner_admin(7)


def test_session_lifetime_validation_rejects_non_positive_or_excessive():
    service, _ = make_service()
    with pytest.raises(AuthenticationError, match="Invalid session lifetime"):
        service.create_user_session(7, lifetime_seconds=0)
    with pytest.raises(AuthenticationError, match="Invalid session lifetime"):
        service.create_user_session(7, lifetime_seconds=-3600)
    with pytest.raises(AuthenticationError, match="Invalid session lifetime"):
        service.create_user_session(7, lifetime_seconds=8 * 24 * 60 * 60)


def test_session_active_updates_last_activity_and_commits():
    secret = "session-valid-secret"
    row = user_row()
    row.update({
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2),
        "revoked_at": None,
        "stored_session_version": 1,
    })
    service, connection = make_service({"fetchone": [row]})
    profile = service.validate_user_session("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", secret)
    assert profile.id == 7
    activity_query = next(query for query, _ in connection.cursor_obj.calls if "UPDATE user_sessions SET last_activity_at" in query)
    assert "last_activity_at = CURRENT_TIMESTAMP" in activity_query
    assert connection.committed


def test_timezone_aware_and_naive_expiry_datetimes():
    secret = "tz-test-secret"
    # Timezone-aware active session
    row_aware = user_row()
    row_aware.update({
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "revoked_at": None,
        "stored_session_version": 1,
    })
    service, _ = make_service({"fetchone": [row_aware]})
    profile = service.validate_user_session("11111111-2222-3333-4444-555555555555", secret)
    assert profile.id == 7

    # Timezone-aware expired session
    row_aware_expired = user_row()
    row_aware_expired.update({
        "expires_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        "revoked_at": None,
        "stored_session_version": 1,
    })
    service_exp, connection_exp = make_service({"fetchone": [row_aware_expired]})
    with pytest.raises(AuthenticationError, match="expired"):
        service_exp.validate_user_session("11111111-2222-3333-4444-555555555555", secret)
    assert any("session_expired" in str(params) for _, params in connection_exp.cursor_obj.calls)


def test_revoke_user_session_marks_revoked_and_logs_audit():
    service, connection = make_service()
    service.revoke_user_session(7, "33333333-3333-3333-3333-333333333333")
    update_call = next((query, params) for query, params in connection.cursor_obj.calls if "UPDATE user_sessions SET revoked_at" in query)
    assert update_call[1] == ("33333333-3333-3333-3333-333333333333", 7)
    audit_call = next((query, params) for query, params in connection.cursor_obj.calls if "INSERT INTO audit_logs" in query)
    assert audit_call[1][0] == 7
    assert audit_call[1][1] == "session_revoked"
    assert connection.committed


def test_revoke_user_session_rejects_invalid_uuid():
    service, _ = make_service()
    with pytest.raises(AuthenticationError, match="Session is unavailable"):
        service.revoke_user_session(7, "not-a-valid-uuid")


def test_revoke_session_as_owner_succeeds_for_owner():
    service, connection = make_service({
        "fetchone": [{"ok": 1}, {"user_id": 12}],
    })
    service.revoke_session_as_owner(actor_user_id=7, session_id="44444444-4444-4444-4444-444444444444")
    assert any("UPDATE user_sessions SET revoked_at" in query for query, _ in connection.cursor_obj.calls)
    audit_call = next(params for query, params in connection.cursor_obj.calls if "INSERT INTO audit_logs" in query)
    assert audit_call[0] == 12
    assert audit_call[1] == "session_revoked"
    assert connection.committed


def test_revoke_session_as_owner_denied_for_normal_user():
    service, connection = make_service({"fetchone": [None]})
    with pytest.raises(AuthenticationError, match="Owner administrator access is required"):
        service.revoke_session_as_owner(actor_user_id=99, session_id="44444444-4444-4444-4444-444444444444")
    assert not any("UPDATE user_sessions" in query for query, _ in connection.cursor_obj.calls)
    assert connection.rolled_back


def test_rollback_sql_is_additive_and_does_not_touch_sales():
    sql = (PROJECT_ROOT / "sql" / "06_owner_admin_and_sessions_rollback.sql").read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS user_sessions" in sql
    assert "DROP TABLE IF EXISTS owner_admin_assignment" in sql
    assert "ALTER TABLE sales" not in sql
    assert "UPDATE sales" not in sql
    assert "DELETE FROM sales" not in sql
    assert "FROM sales" not in sql

