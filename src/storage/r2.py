"""Cloudflare R2 (S3-compatible) storage backend for uploaded datasets.

The bucket is private and only the backend holds credentials.  Browsers never
receive presigned URLs or R2 configuration; reads stay server-side exactly as
they do for the filesystem backend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import logging
import os
import time
from typing import Any, Callable

from .uploads import (
    BaseUploadStorage,
    DEFAULT_MAX_UPLOAD_BYTES,
    UploadStorageError,
    UploadStorageUnavailable,
    default_max_excel_bytes,
)

logger = logging.getLogger(__name__)


REQUIRED_R2_VARIABLES = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
DEFAULT_KEY_PREFIX = "uploads"
DEFAULT_REGION = "auto"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 0.25

MISSING_CODES = frozenset({"NoSuchKey", "NotFound", "404"})
RETRYABLE_CODES = frozenset({
    "500", "502", "503", "504",
    "InternalError", "ServiceUnavailable", "SlowDown", "Throttling",
    "RequestTimeout", "RequestTimeoutException", "TooManyRequests",
})
RETRYABLE_EXCEPTION_NAMES = frozenset({
    "ConnectionError", "ConnectionClosedError", "ConnectTimeoutError",
    "EndpointConnectionError", "ReadTimeoutError", "TimeoutError",
})


class StorageConfigurationError(RuntimeError):
    """Storage configuration is enabled but incomplete or invalid."""


@dataclass(frozen=True)
class R2Config:
    access_key_id: str
    secret_access_key: str = field(repr=False)
    bucket: str
    endpoint_url: str
    region: str = DEFAULT_REGION
    key_prefix: str = DEFAULT_KEY_PREFIX

    @classmethod
    def from_environment(cls) -> "R2Config":
        """Read R2 settings and fail fast, naming variables but never values."""
        missing = [
            name for name in REQUIRED_R2_VARIABLES if not (os.getenv(name) or "").strip()
        ]
        endpoint = (os.getenv("R2_ENDPOINT_URL") or "").strip().rstrip("/")
        account_id = (os.getenv("R2_ACCOUNT_ID") or "").strip()
        if not endpoint:
            if account_id:
                endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
            else:
                missing.append("R2_ACCOUNT_ID (or R2_ENDPOINT_URL)")
        if missing:
            raise StorageConfigurationError(
                "Cloudflare R2 storage is enabled but configuration is incomplete: "
                + ", ".join(missing)
                + ". Set these variables on the backend only; never use NEXT_PUBLIC_."
            )
        if not endpoint.startswith("https://"):
            raise StorageConfigurationError("R2_ENDPOINT_URL must start with https://.")
        prefix = (os.getenv("R2_KEY_PREFIX") or DEFAULT_KEY_PREFIX).strip().strip("/")
        if not prefix:
            prefix = DEFAULT_KEY_PREFIX
        if any(part in {"", ".", ".."} for part in prefix.split("/")):
            raise StorageConfigurationError("R2_KEY_PREFIX must be a safe object-key prefix.")
        return cls(
            access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
            secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
            bucket=os.environ["R2_BUCKET_NAME"].strip(),
            endpoint_url=endpoint,
            region=(os.getenv("R2_REGION") or DEFAULT_REGION).strip() or DEFAULT_REGION,
            key_prefix=prefix,
        )

    def object_key(self, storage_key: str) -> str:
        """Map the unchanged TiDB ``storage_key`` to a backend-only prefix."""
        return f"{self.key_prefix}/{storage_key}"

    def cache_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.endpoint_url,
            self.bucket,
            self.key_prefix,
            self.region,
            self.access_key_id,
            # A one-way fingerprint distinguishes rotated secrets without ever
            # placing the raw secret in the cache key (or its repr/log output).
            hashlib.sha256(self.secret_access_key.encode("utf-8")).hexdigest(),
        )


def _create_client(config: R2Config):
    """Create the boto3 client lazily so the filesystem backend needs no SDK."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as error:  # pragma: no cover - dependency is declared in api-requirements.txt
        raise StorageConfigurationError(
            "The boto3 package is required when RETAIL_UPLOAD_STORAGE_BACKEND=r2. "
            "Install it from api-requirements.txt."
        ) from error

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name=config.region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            # Retries are implemented here so they stay bounded and testable with
            # an arbitrary client; botocore's own retry loop is disabled.
            retries={"max_attempts": 1, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _error_code(error: Exception) -> str:
    response: Any = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status:
            return str(status)
    code = getattr(error, "code", None)
    return str(code) if code else ""


def _is_retryable(error: Exception) -> bool:
    code = _error_code(error)
    if code in MISSING_CODES:
        return False
    if code in RETRYABLE_CODES:
        return True
    if type(error).__name__ in RETRYABLE_EXCEPTION_NAMES:
        return True
    return isinstance(error, (ConnectionError, TimeoutError))


def _translate_error(error: Exception) -> UploadStorageError:
    if isinstance(error, UploadStorageError):
        return error
    if _error_code(error) in MISSING_CODES:
        return UploadStorageError("Uploaded file is unavailable.")
    return UploadStorageUnavailable("Uploaded file storage is temporarily unavailable. Please retry.")


def _is_missing_object_error(error: UploadStorageError) -> bool:
    """True only when the underlying backend failure confirmed the key is gone.

    ``_with_retries`` re-raises translated errors with the original client error
    as ``__cause__``; every other failure must stay visible to the caller.
    """
    cause = error.__cause__
    return isinstance(cause, Exception) and _error_code(cause) in MISSING_CODES


class R2UploadStorage(BaseUploadStorage):
    """Private R2 bucket using the shared validation and ownership contract."""

    def __init__(
        self,
        config: R2Config,
        client: Any | None = None,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        max_excel_bytes: int | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ):
        super().__init__(max_upload_bytes, default_max_excel_bytes() if max_excel_bytes is None else max_excel_bytes)
        self.config = config
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay = max(0.0, float(retry_delay))
        self._client = client if client is not None else _create_client(config)

    def _with_retries(self, action: Callable[[], Any]) -> Any:
        last_error: UploadStorageError | None = None
        last_code = "unknown"
        for attempt in range(1, self.max_attempts + 1):
            try:
                return action()
            except UploadStorageError:
                raise
            except Exception as error:  # noqa: BLE001 - translated immediately
                mapped = _translate_error(error)
                # Missing objects and permanent authorization failures are never retried.
                if not isinstance(mapped, UploadStorageUnavailable) or not _is_retryable(error):
                    raise mapped from error
                last_error = mapped
                last_code = _error_code(error) or type(error).__name__
                if attempt < self.max_attempts and self.retry_delay:
                    time.sleep(self.retry_delay * (2 ** (attempt - 1)))
        logger.warning("R2 storage request failed after %s attempt(s) code=%s", self.max_attempts, last_code)
        raise last_error or UploadStorageUnavailable("Uploaded file storage is temporarily unavailable. Please retry.")

    def _put(self, storage_key: str, content: bytes) -> None:
        digest = hashlib.sha256(content).hexdigest()
        self._with_retries(lambda: self._client.put_object(
            Bucket=self.config.bucket,
            Key=self.config.object_key(storage_key),
            Body=content,
            ContentType="application/octet-stream",
            Metadata={"sha256": digest},
        ))

    def _get(self, storage_key: str) -> bytes:
        def fetch() -> bytes:
            response = self._client.get_object(
                Bucket=self.config.bucket,
                Key=self.config.object_key(storage_key),
            )
            body = response["Body"]
            try:
                return body.read()
            finally:
                # Always release the streaming body, even when the read fails, so
                # a retried read cannot leak a connection or an open socket.
                close = getattr(body, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as error:  # noqa: BLE001 - never mask the read outcome
                        logger.debug(
                            "R2 response body close failed error=%s", type(error).__name__
                        )

        return self._with_retries(fetch)

    def _delete(self, storage_key: str) -> None:
        """Delete an object, treating only a confirmed missing key as success.

        R2 reports an already-absent key as either a 204 response or
        ``NoSuchKey``/``NotFound``/404, which keeps repeated deletes
        idempotent.  Every other failure - ``AccessDenied``, invalid
        credentials, or an unreachable endpoint - propagates so callers keep the
        database metadata instead of silently discarding the only reference to
        a still-existing object.
        """
        try:
            self._with_retries(lambda: self._client.delete_object(
                Bucket=self.config.bucket,
                Key=self.config.object_key(storage_key),
            ))
        except UploadStorageError as error:
            if _is_missing_object_error(error):
                return
            raise
