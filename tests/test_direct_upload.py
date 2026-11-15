"""Tests for the direct-to-backend upload path (Netlify 6 MB bypass).

The direct route is authenticated by a short-lived, single-use, user-bound
ticket instead of the session cookie, so these tests focus on ticket semantics,
least-privilege CORS, size enforcement, and tenant isolation.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
import pytest
from starlette.datastructures import UploadFile
from starlette.responses import Response

import api as retailmind_api
from src.auth.service import UserProfile

CSV = b"Order_ID,Order_Date,City,Region,Product,Category,Sales,Profit\nA,2025-01-01,Delhi,North,Pen,Office,100,20\n"


def make_user(user_id: int) -> UserProfile:
    return UserProfile(
        id=user_id,
        email=f"user{user_id}@example.test",
        full_name=f"User {user_id}",
        phone=None,
        account_status="active",
        session_version=1,
        created_at=datetime(2025, 1, 1),
        last_login_at=None,
    )


class StubAuthService:
    def __init__(self) -> None:
        self.created: list[tuple[int, str]] = []

    def create_uploaded_file(self, user_id: int, upload_id: str, *_args) -> None:
        self.created.append((user_id, upload_id))

    def record_upload(self, *_args) -> None:
        return None

    def delete_uploaded_file(self, *_args) -> None:
        return None


@pytest.fixture
def upload_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RETAIL_UPLOAD_STORAGE_DIR", str(tmp_path))
    stub = StubAuthService()
    monkeypatch.setattr(retailmind_api, "auth_service", lambda: stub)
    retailmind_api.UPLOAD_TICKETS.clear()
    yield stub
    retailmind_api.UPLOAD_TICKETS.clear()


def direct_upload(user_id: int, filename: str = "sales.csv", content: bytes = CSV):
    token, _ttl = retailmind_api.issue_upload_ticket(user_id)
    upload = UploadFile(filename=filename, file=BytesIO(content))
    return asyncio.run(retailmind_api.upload_dataset_direct(upload, f"Bearer {token}"))


def test_ticket_is_single_use(upload_env):
    token, ttl = retailmind_api.issue_upload_ticket(7)
    assert ttl == retailmind_api.UPLOAD_TICKET_TTL_SECONDS
    assert retailmind_api.consume_upload_ticket(f"Bearer {token}") == 7
    with pytest.raises(HTTPException) as error:
        retailmind_api.consume_upload_ticket(f"Bearer {token}")
    assert error.value.status_code == 401
    assert "already been used" in error.value.detail


def test_ticket_requires_a_bearer_value(upload_env):
    for header in (None, "", "Basic abc", "Bearer "):
        with pytest.raises(HTTPException) as error:
            retailmind_api.consume_upload_ticket(header)
        assert error.value.status_code == 401


def test_ticket_expires(upload_env, monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr(retailmind_api.time, "time", lambda: clock["now"])
    token, ttl = retailmind_api.issue_upload_ticket(7)
    clock["now"] += ttl + 1
    with pytest.raises(HTTPException) as error:
        retailmind_api.consume_upload_ticket(f"Bearer {token}")
    assert error.value.status_code == 401
    assert "expired" in error.value.detail


def test_ticket_token_is_not_stored_in_plaintext(upload_env):
    token, _ttl = retailmind_api.issue_upload_ticket(7)
    assert token not in retailmind_api.UPLOAD_TICKETS


def test_upload_origins_never_include_a_wildcard(monkeypatch):
    monkeypatch.setenv("RETAILMIND_UPLOAD_ORIGINS", "*, https://app.example.test/, https://app.example.test")
    assert retailmind_api.upload_origins() == {"https://app.example.test"}


def test_upload_origins_fall_back_to_public_origin(monkeypatch):
    monkeypatch.delenv("RETAILMIND_UPLOAD_ORIGINS", raising=False)
    monkeypatch.setenv("RETAILMIND_PUBLIC_ORIGIN", "https://retailmind.example.test")
    assert retailmind_api.upload_origins() == {"https://retailmind.example.test"}


def test_direct_upload_enforces_the_shared_size_limit(upload_env, monkeypatch):
    monkeypatch.setattr(retailmind_api, "MAX_UPLOAD_BYTES", 64)
    with pytest.raises(HTTPException) as error:
        direct_upload(7, content=b"a" * 65)
    assert error.value.status_code == 413


def test_direct_upload_rejects_unsupported_types(upload_env):
    with pytest.raises(HTTPException) as error:
        direct_upload(7, filename="notes.txt")
    assert error.value.status_code == 415


def test_direct_upload_returns_dataset_and_saves_owner(upload_env):
    result = direct_upload(7)
    dataset_id = result["dataset_id"]
    try:
        assert result["storage"] == "persistent"
        assert result["row_count"] == 1
        record = retailmind_api.DATASETS[dataset_id]
        assert record.owner_id == 7
        assert upload_env.created[0] == (7, dataset_id)
        # Another tenant cannot open the dataset built by the direct route.
        with pytest.raises(HTTPException) as error:
            retailmind_api.get_dataset(dataset_id, 8)
        assert error.value.status_code == 404
        assert retailmind_api.get_dataset(dataset_id, 7) is record
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


class DummyApp:
    def __init__(self) -> None:
        self.called = 0

    async def __call__(self, scope, receive, send):
        self.called += 1
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}"})


def run_middleware(scope, app):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(retailmind_api.UploadCORSMiddleware(app)(scope, receive, send))
    return sent


def scope(method: str, path: str, headers: list[tuple[bytes, bytes]]):
    return {"type": "http", "method": method, "path": path, "headers": headers}


def test_preflight_allows_only_the_configured_origin(monkeypatch):
    monkeypatch.setenv("RETAILMIND_UPLOAD_ORIGINS", "https://app.example.test")
    app = DummyApp()

    allowed = run_middleware(
        scope(
            "OPTIONS",
            "/api/upload/direct",
            [
                (b"origin", b"https://app.example.test"),
                (b"access-control-request-method", b"POST"),
            ],
        ),
        app,
    )
    assert allowed[0]["status"] == 204
    assert (b"access-control-allow-origin", b"https://app.example.test") in allowed[0]["headers"]

    denied = run_middleware(
        scope(
            "OPTIONS",
            "/api/upload/direct",
            [
                (b"origin", b"https://evil.example"),
                (b"access-control-request-method", b"POST"),
            ],
        ),
        app,
    )
    assert denied[0]["status"] == 400
    assert not any(name == b"access-control-allow-origin" for name, _ in denied[0]["headers"])


def test_cors_headers_apply_only_to_upload_routes(monkeypatch):
    monkeypatch.setenv("RETAILMIND_UPLOAD_ORIGINS", "https://app.example.test")
    app = DummyApp()

    passthrough = run_middleware(
        scope("GET", "/api/datasets", [(b"origin", b"https://app.example.test")]),
        app,
    )
    assert app.called == 1
    assert not any(name == b"access-control-allow-origin" for name, _ in passthrough[0]["headers"])


def test_direct_response_gets_cors_header_for_allowed_origin(upload_env, monkeypatch):
    monkeypatch.setenv("RETAILMIND_UPLOAD_ORIGINS", "https://app.example.test")
    app = DummyApp()
    sent = run_middleware(
        scope("POST", "/api/upload/direct", [(b"origin", b"https://app.example.test")]),
        app,
    )
    assert app.called == 1
    assert (b"access-control-allow-origin", b"https://app.example.test") in sent[0]["headers"]


def test_concurrent_ticket_consumption_succeeds_exactly_once(upload_env):
    token, _ttl = retailmind_api.issue_upload_ticket(7)
    header = f"Bearer {token}"

    def consume() -> tuple[str, int]:
        try:
            return "ok", retailmind_api.consume_upload_ticket(header)
        except HTTPException as error:
            return "error", error.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: consume(), range(8)))

    assert [result for result in results if result[0] == "ok"] == [("ok", 7)]
    assert all(status == 401 for kind, status in results if kind == "error")


def test_ticket_response_is_never_cached(upload_env):
    response = Response()

    payload = retailmind_api.create_upload_ticket(response, user=make_user(7))

    assert payload["token"]
    assert payload["expires_in"] == retailmind_api.UPLOAD_TICKET_TTL_SECONDS
    assert response.headers["cache-control"] == "private, no-store"


def test_cors_middleware_ignores_lookalike_prefix_routes(monkeypatch):
    monkeypatch.setenv("RETAILMIND_UPLOAD_ORIGINS", "https://app.example.test")
    app = DummyApp()

    sent = run_middleware(
        scope("POST", "/api/uploads-extra", [(b"origin", b"https://app.example.test")]),
        app,
    )

    assert app.called == 1
    assert not any(name == b"access-control-allow-origin" for name, _ in sent[0]["headers"])


@pytest.mark.parametrize("path", ["/api/upload", "/api/upload/ticket", "/api/upload/direct"])
def test_cors_middleware_covers_exactly_the_upload_routes(monkeypatch, path: str):
    monkeypatch.setenv("RETAILMIND_UPLOAD_ORIGINS", "https://app.example.test")
    app = DummyApp()

    sent = run_middleware(
        scope(
            "OPTIONS",
            path,
            [
                (b"origin", b"https://app.example.test"),
                (b"access-control-request-method", b"POST"),
            ],
        ),
        app,
    )

    assert sent[0]["status"] == 204
    assert app.called == 0
    assert (b"access-control-allow-origin", b"https://app.example.test") in sent[0]["headers"]
