from __future__ import annotations

import pytest

from src.auth.service import AuthService, AuthenticationError


class Cursor:
    def __init__(self, records):
        self.records, self.calls, self.rowcount = records, [], 1
        self.last_params = ()

    def execute(self, query, params=()):
        self.calls.append((query, params)); self.query, self.last_params = query, params
        if query.startswith("DELETE"):
            self.rowcount = int((params[0], params[1]) in self.records)

    def fetchone(self):
        if "WHERE id = %s AND user_id = %s" in self.query:
            return self.records.get((self.last_params[0], self.last_params[1]))
        return None

    def fetchall(self):
        if "FROM uploaded_files" in self.query:
            return [record for (upload_id, user_id), record in self.records.items() if user_id == self.last_params[0]]
        return []

    def close(self): pass


class Connection:
    def __init__(self, records):
        self.cursor_obj, self.committed, self.rolled_back = Cursor(records), False, False

    def cursor(self, **kwargs): return self.cursor_obj
    def commit(self): self.committed = True
    def rollback(self): self.rolled_back = True
    def close(self): pass


def make_service(records):
    connection = Connection(records)
    return AuthService(lambda: connection), connection


def record(upload_id="11111111-1111-1111-1111-111111111111"):
    return {"id": upload_id, "original_filename": "sales.csv", "file_type": "csv", "file_sha256": "a" * 64,
            "row_count": 1, "size_bytes": 100, "validation_status": "valid", "storage_key": "7/opaque.csv"}


def test_persistent_upload_queries_always_bind_the_authenticated_owner():
    upload_id = "11111111-1111-1111-1111-111111111111"
    service, connection = make_service({(upload_id, 7): record(upload_id)})

    assert service.get_uploaded_file(7, upload_id)["storage_key"] == "7/opaque.csv"
    service.list_uploaded_files(7)
    service.delete_uploaded_file(7, upload_id)

    owner_queries = [params for query, params in connection.cursor_obj.calls if "uploaded_files" in query]
    assert (upload_id, 7) in owner_queries
    assert (7,) in owner_queries


def test_another_user_cannot_open_or_delete_an_upload():
    upload_id = "11111111-1111-1111-1111-111111111111"
    service, connection = make_service({(upload_id, 7): record(upload_id)})

    with pytest.raises(AuthenticationError, match="unavailable"):
        service.get_uploaded_file(8, upload_id)
    with pytest.raises(AuthenticationError, match="unavailable"):
        service.delete_uploaded_file(8, upload_id)
    assert connection.rolled_back


def test_create_upload_rejects_non_uuid_identifiers_before_database_access():
    service, connection = make_service({})
    with pytest.raises(AuthenticationError):
        service.create_uploaded_file(7, "not-a-uuid", "sales.csv", "csv", "a" * 64, 1, 10, "7/opaque.csv")
    assert not connection.cursor_obj.calls
