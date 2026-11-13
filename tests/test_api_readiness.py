from __future__ import annotations

import json

import api as retailmind_api


class StubCursor:
    def __init__(self, *, row: tuple[int, ...] | None = (1,), error: Exception | None = None) -> None:
        self.row = row
        self.error = error
        self.closed = False

    def execute(self, statement: str) -> None:
        assert statement == "SELECT 1"
        if self.error is not None:
            raise self.error

    def fetchone(self) -> tuple[int, ...] | None:
        return self.row

    def close(self) -> None:
        self.closed = True


class StubConnection:
    def __init__(self, cursor: StubCursor) -> None:
        self.stub_cursor = cursor
        self.closed = False

    def cursor(self) -> StubCursor:
        return self.stub_cursor

    def close(self) -> None:
        self.closed = True


def test_ready_route_is_registered() -> None:
    paths = {getattr(route, "path", "") for route in retailmind_api.app.routes}
    assert "/api/ready" in paths


def test_readiness_returns_200_when_database_query_succeeds(monkeypatch) -> None:
    cursor = StubCursor()
    connection = StubConnection(cursor)
    monkeypatch.setattr(retailmind_api, "database_connection", lambda: connection)

    response = retailmind_api.readiness()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload == {
        "status": "ready",
        "service": "retailmind-python",
        "database": "reachable",
        "datasets": len(retailmind_api.DATASETS),
    }
    assert response.headers["cache-control"] == "no-store"
    assert cursor.closed is True
    assert connection.closed is True


def test_readiness_returns_503_without_leaking_connection_error(monkeypatch) -> None:
    def unavailable() -> None:
        raise RuntimeError("host=private-db.internal password=do-not-leak")

    monkeypatch.setattr(retailmind_api, "database_connection", unavailable)

    response = retailmind_api.readiness()
    body = response.body.decode()

    assert response.status_code == 503
    assert json.loads(body) == {
        "status": "unavailable",
        "service": "retailmind-python",
        "database": "unreachable",
        "message": "Database readiness check failed.",
    }
    assert "private-db.internal" not in body
    assert "do-not-leak" not in body
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "5"


def test_readiness_closes_connection_when_query_fails(monkeypatch) -> None:
    cursor = StubCursor(error=RuntimeError("query failed"))
    connection = StubConnection(cursor)
    monkeypatch.setattr(retailmind_api, "database_connection", lambda: connection)

    response = retailmind_api.readiness()

    assert response.status_code == 503
    assert cursor.closed is True
    assert connection.closed is True
