"""Unit tests use a fake DB-API connection; no MySQL server is contacted."""
from __future__ import annotations
from datetime import datetime
import pytest
from src.auth.service import AuthService, AuthenticationError, PASSWORD_HASHER


class FakeCursor:
    def __init__(self, state): self.state, self.calls, self.rowcount = state, [], 1
    def execute(self, query, params=()):
        self.calls.append((query, params)); self.last = query
        if query.startswith("UPDATE users SET full_name") and self.state.get("inactive"):
            self.rowcount = 0
    def fetchone(self):
        if "SELECT id FROM users WHERE email = %s AND" in self.last: return None
        if "SELECT id FROM users WHERE email" in self.last: return self.state.get("duplicate")
        if "password_hash, account_status" in self.last:
            return self.state.get("login_row")
        if "SELECT password_hash" in self.last: return self.state.get("password_row")
        if "SELECT id, email, full_name" in self.last:
            return self.state.get("profile_row")
        return self.state.get("new_user")
    def fetchall(self): return self.state.get("history_rows", [])
    def close(self): pass


class FakeConnection:
    def __init__(self, state): self.state, self.committed, self.rolled_back = state, False, False; self.cursor_obj = FakeCursor(state)
    def cursor(self, **kwargs): return self.cursor_obj
    def commit(self): self.committed = True
    def rollback(self): self.rolled_back = True
    def close(self): pass


def user_row(**overrides):
    row = dict(id=7, email="a@example.com", full_name="Ada", phone=None, account_status="active", session_version=1, created_at=datetime.now(), last_login_at=None)
    row.update(overrides); return row


def make_service(state):
    connection = FakeConnection(state)
    return AuthService(lambda: connection), connection


def test_login_updates_last_login_with_parameterised_query():
    row = user_row(password_hash=PASSWORD_HASHER.hash("a secure password"))
    service, connection = make_service({"login_row": row})
    user = service.login("A@EXAMPLE.COM", "a secure password")
    assert user.id == 7 and connection.committed
    assert any("last_login_at" in query and params == (7,) for query, params in connection.cursor_obj.calls)


def test_login_rejects_inactive_and_never_commits():
    row = user_row(account_status="inactive", password_hash=PASSWORD_HASHER.hash("a secure password"))
    service, connection = make_service({"login_row": row})
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        service.login("a@example.com", "a secure password")
    assert connection.rolled_back and not connection.committed


def test_register_blocks_duplicate_email_before_insert():
    service, connection = make_service({"duplicate": {"id": 8}})
    with pytest.raises(AuthenticationError, match="already exists"):
        service.register("Ada", "a@example.com", None, "a secure password")
    assert not any(query.startswith("INSERT INTO users") for query, _ in connection.cursor_obj.calls)


def test_change_password_requires_current_password():
    service, connection = make_service({"password_row": {"password_hash": PASSWORD_HASHER.hash("old password!!")}})
    with pytest.raises(AuthenticationError, match="Current password"):
        service.change_password(7, "wrong password", "new secure password")
    assert connection.rolled_back


def test_password_change_bumps_session_version():
    service, connection = make_service({"password_row": {"password_hash": PASSWORD_HASHER.hash("old password!!")}})
    service.change_password(7, "old password!!", "new secure password")
    assert connection.committed
    assert any("session_version = session_version + 1" in query for query, _ in connection.cursor_obj.calls)


def test_upload_history_is_scoped_to_authenticated_user_id():
    service, connection = make_service({"history_rows": [{"original_filename": "mine.csv"}]})
    assert service.list_upload_history(7) == [{"original_filename": "mine.csv"}]
    query, params = connection.cursor_obj.calls[0]
    assert "WHERE user_id = %s" in query and params == (7,)


def test_upload_metadata_never_contains_file_bytes():
    service, connection = make_service({})
    service.record_upload(7, "sales.csv", "csv", "a" * 64, 10, "valid")
    query, params = connection.cursor_obj.calls[0]
    assert "INSERT INTO upload_history" in query
    assert params == (7, "sales.csv", "csv", "a" * 64, 10, "processed", "valid")


def test_db_config_requires_mysql_password(monkeypatch):
    import src.auth.ui as auth_ui
    monkeypatch.setattr(auth_ui, "ENV_PATH", auth_ui.PROJECT_ROOT / "nonexistent.env")
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    with pytest.raises(AuthenticationError, match="MySQL password is not configured"):
        auth_ui.get_db_config()


def test_db_config_returns_configured_values(monkeypatch):
    import src.auth.ui as auth_ui
    monkeypatch.setattr(auth_ui, "ENV_PATH", auth_ui.PROJECT_ROOT / "nonexistent.env")
    monkeypatch.setenv("MYSQL_PASSWORD", "test_secret_pass")
    monkeypatch.setenv("MYSQL_USER", "test_user")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    config = auth_ui.get_db_config()
    assert config["user"] == "test_user"
    assert config["port"] == 3307
    assert config["password"] == "test_secret_pass"
