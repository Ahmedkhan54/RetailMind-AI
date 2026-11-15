"""Upload size-limit and single-parse regression tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import api as retailmind_api
from src.auth.service import UserProfile
from src.storage.uploads import (
    UploadStorage,
    UploadStorageError,
    UploadStorageUnavailable,
    default_max_excel_bytes,
)

CSV_HEADER = b"Order_ID,Order_Date,City,Region,Product,Category,Sales,Profit\n"
CSV = CSV_HEADER + b"A,2025-01-01,Delhi,North,Pen,Office,100,20\n"
ROW = b"A,2025-01-01,Delhi,North,Pen,Office,100,20\n"


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


def test_excel_upload_over_the_configured_limit_returns_actionable_413(upload_env, monkeypatch):
    monkeypatch.setattr(retailmind_api, "MAX_EXCEL_UPLOAD_BYTES", 8)

    with pytest.raises(HTTPException) as error:
        direct_upload(7, filename="workbook.xlsx", content=b"x" * 9)

    assert error.value.status_code == 413
    assert "Excel workbooks are limited to" in error.value.detail
    assert "CSV" in error.value.detail


def test_csv_of_the_same_size_is_not_weakened_by_the_excel_limit(upload_env, monkeypatch):
    monkeypatch.setattr(retailmind_api, "MAX_EXCEL_UPLOAD_BYTES", 8)

    result = direct_upload(7, content=CSV)

    try:
        assert result["row_count"] == 1
        assert result["storage"] == "persistent"
    finally:
        retailmind_api.DATASETS.pop(result["dataset_id"], None)


def test_upload_path_does_not_reparse_the_file_inside_storage(upload_env, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("storage reparsed the upload instead of using the validated frame")

    monkeypatch.setattr(UploadStorage, "validate", fail_if_called)

    result = direct_upload(7)
    try:
        assert result["row_count"] == 1
    finally:
        retailmind_api.DATASETS.pop(result["dataset_id"], None)


@pytest.mark.parametrize("megabytes", [1, 5])
def test_csv_uploads_at_one_and_five_megabytes_are_accepted(upload_env, megabytes: int):
    rows = (megabytes * 1024 * 1024) // len(ROW)
    content = CSV_HEADER + ROW * rows

    result = direct_upload(7, content=content)
    try:
        assert result["row_count"] == rows
        assert result["filename"] == "sales.csv"
    finally:
        retailmind_api.DATASETS.pop(result["dataset_id"], None)


def test_render_defaults_excel_limit_to_five_megabytes(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("RETAIL_MAX_EXCEL_UPLOAD_BYTES", raising=False)

    assert default_max_excel_bytes() == 5 * 1024 * 1024


def test_local_default_keeps_the_full_excel_limit(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RETAIL_MAX_EXCEL_UPLOAD_BYTES", raising=False)

    assert default_max_excel_bytes() == 25 * 1024 * 1024


@pytest.mark.parametrize("value", ["not-a-number", "0", "-5"])
def test_invalid_excel_limit_falls_back_to_the_platform_default(monkeypatch, value: str):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("RETAIL_MAX_EXCEL_UPLOAD_BYTES", value)

    assert default_max_excel_bytes() == 25 * 1024 * 1024


def test_excel_limit_can_be_overridden(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("RETAIL_MAX_EXCEL_UPLOAD_BYTES", "1048576")

    assert default_max_excel_bytes() == 1024 * 1024


def test_filesystem_storage_enforces_the_excel_limit_too(tmp_path, monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RETAIL_MAX_EXCEL_UPLOAD_BYTES", raising=False)
    storage = UploadStorage(tmp_path, max_excel_bytes=8)

    with pytest.raises(UploadStorageError, match="Convert the file to CSV"):
        storage.store(7, "workbook.xlsx", b"x" * 9)


class StoredRecordAuth(StubAuthService):
    def get_uploaded_file(self, user_id: int, dataset_id: str) -> dict[str, object]:
        return {
            "storage_key": f"{user_id}/opaque.csv",
            "file_sha256": "0" * 64,
            "original_filename": "sales.csv",
            "created_at": None,
        }


class ReadOutageStorage:
    def read(self, *_args, **_kwargs):
        raise UploadStorageUnavailable("Uploaded file storage is temporarily unavailable. Please retry.")


class ReadMissingStorage:
    def read(self, *_args, **_kwargs):
        raise UploadStorageError("Uploaded file is unavailable.")


class StoreOutageStorage:
    def store_and_record(self, *_args, **_kwargs):
        raise UploadStorageUnavailable("Uploaded file storage is temporarily unavailable. Please retry.")


class DeleteOutageStorage:
    def delete_and_forget(self, *_args, **_kwargs):
        raise UploadStorageUnavailable("Uploaded file storage is temporarily unavailable. Please retry.")


def test_dataset_read_maps_transient_storage_failure_to_503(monkeypatch):
    monkeypatch.setattr(retailmind_api, "auth_service", lambda: StoredRecordAuth())
    monkeypatch.setattr(retailmind_api, "storage_from_environment", lambda _root: ReadOutageStorage())

    with pytest.raises(HTTPException) as error:
        retailmind_api.get_dataset(str(uuid4()), 7)

    assert error.value.status_code == 503


def test_dataset_read_keeps_missing_objects_at_422(monkeypatch):
    monkeypatch.setattr(retailmind_api, "auth_service", lambda: StoredRecordAuth())
    monkeypatch.setattr(retailmind_api, "storage_from_environment", lambda _root: ReadMissingStorage())

    with pytest.raises(HTTPException) as error:
        retailmind_api.get_dataset(str(uuid4()), 7)

    assert error.value.status_code == 422


def test_upload_maps_transient_storage_failure_to_503(upload_env, monkeypatch):
    monkeypatch.setattr(retailmind_api, "storage_from_environment", lambda _root: StoreOutageStorage())

    with pytest.raises(HTTPException) as error:
        direct_upload(7)

    assert error.value.status_code == 503


def test_delete_maps_transient_storage_failure_to_503(monkeypatch):
    monkeypatch.setattr(retailmind_api, "auth_service", lambda: StoredRecordAuth())
    monkeypatch.setattr(retailmind_api, "storage_from_environment", lambda _root: DeleteOutageStorage())

    with pytest.raises(HTTPException) as error:
        retailmind_api.delete_dataset(str(uuid4()), make_user(7))

    assert error.value.status_code == 503
