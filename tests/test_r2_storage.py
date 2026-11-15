"""Unit tests for the private Cloudflare R2 storage backend.

A fake S3 client keeps these tests network-free while exercising the real
validation, tenant isolation, checksum, retry, and cleanup code paths.
"""

from __future__ import annotations

import hashlib
import logging
from uuid import uuid4

import pytest

from src.storage.r2 import R2Config, R2UploadStorage
from src.storage.uploads import UploadStorageError, UploadStorageUnavailable

CSV = b"Order_ID,Order_Date,City,Product_Category,Product_Name,Sales\nA,2025-01-01,Delhi,Office,Pen,100\n"


class FakeBody:
    def __init__(self, data: bytes):
        self._data = data
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


class FakeBodyError(FakeBody):
    def __init__(self, error: Exception):
        super().__init__(b"")
        self._error = error

    def read(self) -> bytes:
        raise self._error


class FakeClientError(Exception):
    def __init__(self, code: str, status: int | None = None):
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status or (404 if code in {"NoSuchKey", "404"} else 500)},
        }


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes | FakeBody] = {}
        self.calls: list[tuple[str, dict]] = []
        self.failures: dict[str, list[Exception]] = {}
        self.bodies: list[FakeBody] = []

    def _fail_if_configured(self, operation: str) -> None:
        queue = self.failures.get(operation)
        if queue:
            raise queue.pop(0)

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self._fail_if_configured("put_object")
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        self._fail_if_configured("get_object")
        if kwargs["Key"] not in self.objects:
            raise FakeClientError("NoSuchKey")
        value = self.objects[kwargs["Key"]]
        body = value if isinstance(value, FakeBody) else FakeBody(value)
        self.bodies.append(body)
        return {"Body": body}

    def delete_object(self, **kwargs):
        self.calls.append(("delete_object", kwargs))
        self._fail_if_configured("delete_object")
        if kwargs["Key"] not in self.objects:
            raise FakeClientError("NoSuchKey")
        del self.objects[kwargs["Key"]]
        return {}

    def calls_for(self, operation: str) -> list[dict]:
        return [payload for name, payload in self.calls if name == operation]


def make_config(prefix: str = "uploads") -> R2Config:
    return R2Config(
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
        bucket="retailmind-test",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        region="auto",
        key_prefix=prefix,
    )


def test_cache_key_is_stable_for_the_same_configuration():
    assert make_config().cache_key() == make_config().cache_key()


def test_cache_key_changes_when_only_the_secret_changes():
    original = make_config()
    rotated = R2Config(
        access_key_id=original.access_key_id,
        secret_access_key="rotated-secret-key",
        bucket=original.bucket,
        endpoint_url=original.endpoint_url,
        region=original.region,
        key_prefix=original.key_prefix,
    )

    assert original.cache_key() != rotated.cache_key()


def test_cache_key_never_contains_the_raw_secret():
    config = make_config()
    cache_key = config.cache_key()
    rendered = repr(cache_key)

    assert config.secret_access_key not in rendered
    assert all(config.secret_access_key not in part for part in cache_key)
    assert len(cache_key) == 6


@pytest.fixture
def client() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture
def storage(client: FakeS3Client) -> R2UploadStorage:
    return R2UploadStorage(make_config(), client=client, retry_delay=0)


def test_upload_read_delete_round_trip_uses_prefixed_key_and_checksum_metadata(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV, validated=None)
    object_key = f"uploads/{stored.storage_key}"

    assert stored.storage_key.startswith("7/")
    assert object_key in client.objects
    assert client.objects[object_key] == CSV
    put = client.calls_for("put_object")[0]
    assert put["Metadata"]["sha256"] == hashlib.sha256(CSV).hexdigest()
    assert storage.read(7, stored.storage_key, stored.sha256) == CSV

    storage.delete(7, stored.storage_key)
    assert object_key not in client.objects


def test_configurable_prefix_keeps_database_storage_key_unchanged(storage: R2UploadStorage, client: FakeS3Client):
    custom = R2UploadStorage(make_config(prefix="tenant-data"), client=client, retry_delay=0)
    stored = custom.store(7, "sales.csv", CSV)
    assert stored.storage_key.startswith("7/")
    assert f"tenant-data/{stored.storage_key}" in client.objects


def test_missing_object_remains_a_validation_style_error(storage: R2UploadStorage, client: FakeS3Client):
    stored = storage.store(7, "sales.csv", CSV)
    del client.objects[f"uploads/{stored.storage_key}"]

    with pytest.raises(UploadStorageError) as error:
        storage.read(7, stored.storage_key)
    assert "unavailable" in str(error.value)
    assert not isinstance(error.value, UploadStorageUnavailable)


def test_transient_failure_is_retried_then_succeeds(storage: R2UploadStorage, client: FakeS3Client):
    client.failures["put_object"] = [FakeClientError("500"), FakeClientError("503")]

    stored = storage.store(7, "sales.csv", CSV)

    assert stored.storage_key.startswith("7/")
    assert len(client.calls_for("put_object")) == 3
    assert f"uploads/{stored.storage_key}" in client.objects


def test_retries_are_bounded_and_translate_to_unavailable(storage: R2UploadStorage, client: FakeS3Client):
    client.failures["put_object"] = [FakeClientError("503") for _ in range(5)]

    with pytest.raises(UploadStorageUnavailable):
        storage.store(7, "sales.csv", CSV)

    assert len(client.calls_for("put_object")) == 3
    assert client.objects == {}


def test_permanent_authorization_failure_is_not_retried(storage: R2UploadStorage, client: FakeS3Client):
    client.failures["put_object"] = [FakeClientError("AccessDenied", 403)]

    with pytest.raises(UploadStorageUnavailable):
        storage.store(7, "sales.csv", CSV)

    assert len(client.calls_for("put_object")) == 1


def test_body_read_timeout_is_retried_and_becomes_unavailable(storage: R2UploadStorage, client: FakeS3Client):
    stored = storage.store(7, "sales.csv", CSV)
    client.objects[f"uploads/{stored.storage_key}"] = FakeBodyError(TimeoutError("read timed out"))

    with pytest.raises(UploadStorageUnavailable):
        storage.read(7, stored.storage_key)

    assert len(client.calls_for("get_object")) == 3


def test_checksum_mismatch_blocks_a_tampered_object(storage: R2UploadStorage, client: FakeS3Client):
    stored = storage.store(7, "sales.csv", CSV)
    client.objects[f"uploads/{stored.storage_key}"] = CSV + b"tampered"

    with pytest.raises(UploadStorageError, match="integrity"):
        storage.read(7, stored.storage_key, stored.sha256)


def test_cross_user_and_traversal_reads_are_rejected_before_any_network_call(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    calls_before = len(client.calls)

    with pytest.raises(UploadStorageError):
        storage.read(8, stored.storage_key)
    with pytest.raises(UploadStorageError):
        storage.read(7, "7/../8/secret.csv")

    assert len(client.calls) == calls_before


def test_metadata_failure_removes_only_the_new_object(storage: R2UploadStorage, client: FakeS3Client):
    def fail(_stored) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        storage.store_and_record(7, "sales.csv", CSV, fail)

    assert client.objects == {}


def test_delete_failure_keeps_metadata_callback_unrun_and_allows_retry(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    forgotten: list[bool] = []
    client.failures["delete_object"] = [FakeClientError("500") for _ in range(3)]

    with pytest.raises(UploadStorageUnavailable):
        storage.delete_and_forget(7, stored.storage_key, lambda: forgotten.append(True))

    assert forgotten == []
    assert f"uploads/{stored.storage_key}" in client.objects

    storage.delete_and_forget(7, stored.storage_key, lambda: forgotten.append(True))
    assert forgotten == [True]
    assert client.objects == {}


def test_deleting_an_already_missing_object_is_success(storage: R2UploadStorage, client: FakeS3Client):
    storage.delete(7, f"7/{uuid4().hex}.csv")
    assert len(client.calls_for("delete_object")) == 1


@pytest.mark.parametrize("code", ["NoSuchKey", "NotFound", "404"])
def test_confirmed_missing_delete_codes_are_idempotent(
    storage: R2UploadStorage, client: FakeS3Client, code: str
):
    client.failures["delete_object"] = [FakeClientError(code, 404)]

    storage.delete(7, f"7/{uuid4().hex}.csv")

    assert len(client.calls_for("delete_object")) == 1


def test_delete_access_denied_propagates_and_keeps_the_object(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    client.failures["delete_object"] = [FakeClientError("AccessDenied", 403)]

    with pytest.raises(UploadStorageUnavailable):
        storage.delete(7, stored.storage_key)

    assert len(client.calls_for("delete_object")) == 1
    assert f"uploads/{stored.storage_key}" in client.objects


def test_delete_permanent_credential_failure_is_not_retried(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    client.failures["delete_object"] = [FakeClientError("InvalidAccessKeyId", 403)]

    with pytest.raises(UploadStorageUnavailable):
        storage.delete(7, stored.storage_key)

    assert len(client.calls_for("delete_object")) == 1
    assert f"uploads/{stored.storage_key}" in client.objects


def test_temporary_delete_failure_is_retried_then_succeeds(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    client.failures["delete_object"] = [FakeClientError("503"), FakeClientError("SlowDown")]

    storage.delete(7, stored.storage_key)

    assert len(client.calls_for("delete_object")) == 3
    assert f"uploads/{stored.storage_key}" not in client.objects


def test_successful_read_closes_the_response_body(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)

    assert storage.read(7, stored.storage_key) == CSV

    assert client.bodies
    assert all(body.closed for body in client.bodies)


def test_failed_read_still_closes_the_response_body(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    failing = FakeBodyError(OSError("stream broke"))
    client.objects[f"uploads/{stored.storage_key}"] = failing

    with pytest.raises(UploadStorageUnavailable):
        storage.read(7, stored.storage_key)

    assert failing.closed is True


def test_timeout_retry_closes_every_attempt_body(
    storage: R2UploadStorage, client: FakeS3Client
):
    stored = storage.store(7, "sales.csv", CSV)
    failing = FakeBodyError(TimeoutError("read timed out"))
    client.objects[f"uploads/{stored.storage_key}"] = failing

    with pytest.raises(UploadStorageUnavailable):
        storage.read(7, stored.storage_key)

    assert len(client.calls_for("get_object")) == 3
    assert failing.closed is True


def test_cleanup_failure_is_logged_and_the_metadata_error_wins(
    storage: R2UploadStorage, client: FakeS3Client, caplog
):
    client.failures["delete_object"] = [FakeClientError("503") for _ in range(5)]

    def fail(_stored) -> None:
        raise RuntimeError("database unavailable")

    with caplog.at_level(logging.ERROR, logger="src.storage.uploads"):
        with pytest.raises(RuntimeError, match="database unavailable"):
            storage.store_and_record(7, "sales.csv", CSV, fail)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Persistent-upload cleanup failed" in message for message in messages)
    # The opaque key is logged for manual reconciliation, never the file bytes
    # or the storage credentials.
    assert "7/" in caplog.text
    assert CSV.decode() not in caplog.text
    assert "test-secret-key" not in caplog.text


def test_unexpected_cleanup_error_does_not_mask_the_metadata_error(
    storage: R2UploadStorage, client: FakeS3Client, monkeypatch, caplog
):
    def explode(*_args, **_kwargs) -> None:
        raise RuntimeError("cleanup exploded")

    monkeypatch.setattr(storage, "delete", explode)

    def fail(_stored) -> None:
        raise RuntimeError("database unavailable")

    with caplog.at_level(logging.ERROR, logger="src.storage.uploads"):
        with pytest.raises(RuntimeError, match="database unavailable"):
            storage.store_and_record(7, "sales.csv", CSV, fail)

    assert "cleanup exploded" not in caplog.text


def test_invalid_upload_is_rejected_before_the_backend_is_called(storage: R2UploadStorage, client: FakeS3Client):
    with pytest.raises(UploadStorageError, match="sales"):
        storage.store(7, "missing.csv", b"City\nDelhi\n")
    assert client.calls_for("put_object") == []


def test_excel_limit_is_enforced_by_the_shared_storage_layer(client: FakeS3Client):
    limited = R2UploadStorage(make_config(), client=client, retry_delay=0, max_excel_bytes=8)
    with pytest.raises(UploadStorageError, match="Convert the file to CSV"):
        limited.store(7, "workbook.xlsx", b"x" * 9)
    assert client.objects == {}
