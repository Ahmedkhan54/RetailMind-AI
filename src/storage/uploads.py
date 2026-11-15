"""Validated, user-owned persistent storage for uploaded dashboard datasets.

The storage layer is deliberately split into a backend-independent base class
and thin byte primitives.  Validation, tenant isolation, checksum verification,
and metadata-cleanup semantics therefore cannot drift between the local
filesystem backend and any remote object-store backend.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Callable
from uuid import uuid4

from data_sources import detect_column_mapping, profile_data, read_uploaded_file

logger = logging.getLogger(__name__)


ALLOWED_EXTENSIONS = frozenset({"csv", "xls", "xlsx", "xlsm"})
EXCEL_EXTENSIONS = frozenset({"xls", "xlsx", "xlsm"})
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# Render Free has 0.1 CPU and 512 MB of RAM; a 5 MB workbook already takes far
# longer to parse than the browser timeout allows.  Local development keeps the
# full 25 MB ceiling unless the operator configures a smaller value.
RENDER_MAX_EXCEL_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_EXCEL_BYTES = 25 * 1024 * 1024


def default_max_excel_bytes() -> int:
    """Return the configured Excel/XLSX ceiling for this process.

    ``RETAIL_MAX_EXCEL_UPLOAD_BYTES`` always wins.  Otherwise Render deployments
    default to 5 MB to protect the free instance, while local development keeps
    the historical 25 MB behaviour.
    """
    configured = os.getenv("RETAIL_MAX_EXCEL_UPLOAD_BYTES")
    if configured:
        try:
            value = int(configured)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return RENDER_MAX_EXCEL_BYTES if os.getenv("RENDER") else DEFAULT_MAX_EXCEL_BYTES


def format_byte_limit(value: int) -> str:
    megabytes = value / (1024 * 1024)
    if megabytes >= 1 and float(megabytes).is_integer():
        return f"{int(megabytes)} MB"
    return f"{megabytes:.1f} MB"


class UploadStorageError(ValueError):
    """A safe message for an upload or stored-file access failure."""


class UploadStorageUnavailable(UploadStorageError):
    """The storage backend is temporarily unreachable or misbehaving.

    This subclasses ``UploadStorageError`` so existing callers keep working, but
    API routes map it to HTTP 503 instead of reporting a bad file (422).
    """


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    original_filename: str
    file_type: str
    sha256: str
    row_count: int
    size_bytes: int


@dataclass(frozen=True)
class ValidatedUpload:
    """Metadata from an already-validated upload.

    Passing this to :meth:`BaseUploadStorage.store` prevents the backend from
    parsing a large workbook a second time.  Only callers that have already
    reproduced every ``validate()`` check may supply it.
    """

    extension: str
    row_count: int


class BaseUploadStorage:
    """Shared validation and ownership rules for every storage backend."""

    def __init__(
        self,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        max_excel_bytes: int | None = None,
    ):
        self.max_upload_bytes = max_upload_bytes
        self.max_excel_bytes = default_max_excel_bytes() if max_excel_bytes is None else max_excel_bytes

    # --- Backend primitives -------------------------------------------------
    def _put(self, storage_key: str, content: bytes) -> None:
        raise NotImplementedError

    def _get(self, storage_key: str) -> bytes:
        raise NotImplementedError

    def _delete(self, storage_key: str) -> None:
        raise NotImplementedError

    # --- Shared validation --------------------------------------------------
    @staticmethod
    def _extension(filename: str) -> str:
        if not filename or Path(filename).name != filename:
            raise UploadStorageError("Upload a file with a valid filename.")
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix not in ALLOWED_EXTENSIONS:
            raise UploadStorageError("Upload a CSV, XLS, XLSX, or XLSM file.")
        return suffix

    @staticmethod
    def _user_id(user_id: int) -> int:
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise UploadStorageError("The authenticated account is invalid.")
        return user_id

    def _validated_key(self, user_id: int, storage_key: str) -> PurePosixPath:
        """Reject traversal, absolute keys, and another user's key."""
        self._user_id(user_id)
        key = PurePosixPath(storage_key)
        if key.is_absolute() or len(key.parts) != 2 or key.parts[0] != str(user_id):
            raise UploadStorageError("Uploaded file is unavailable.")
        if any(part in {"", ".", ".."} for part in key.parts):
            raise UploadStorageError("Uploaded file is unavailable.")
        return key

    def _check_content(self, extension: str, content: bytes) -> None:
        if not isinstance(content, bytes) or not content:
            raise UploadStorageError("The uploaded file is empty.")
        if len(content) > self.max_upload_bytes:
            raise UploadStorageError(f"Upload a file smaller than {format_byte_limit(self.max_upload_bytes)}.")
        if extension in EXCEL_EXTENSIONS and len(content) > self.max_excel_bytes:
            raise UploadStorageError(
                f"Excel workbooks are limited to {format_byte_limit(self.max_excel_bytes)} on this server. "
                "Convert the file to CSV to upload the full dataset."
            )

    def validate(self, filename: str, content: bytes, sheet_name: str | None = None) -> tuple[str, int]:
        """Validate type, size, readability, and dashboard-required source fields."""
        extension = self._extension(filename)
        self._check_content(extension, content)
        try:
            frame = read_uploaded_file(content, filename, sheet_name)
            profile = profile_data(frame, detect_column_mapping(frame.columns))
        except (ValueError, OSError, UnicodeError) as error:
            raise UploadStorageError("Could not read the uploaded file. Check that it is valid and readable.") from error
        if profile["errors"]:
            raise UploadStorageError(str(profile["errors"][0]))
        return extension, len(frame)

    # --- Shared lifecycle ---------------------------------------------------
    def store(
        self,
        user_id: int,
        filename: str,
        content: bytes,
        sheet_name: str | None = None,
        validated: ValidatedUpload | None = None,
    ) -> StoredUpload:
        """Store only after validating the exact worksheet selected by the user.

        ``validated`` lets the API share its single parse with storage.  Without
        it, the backend validates first exactly as before.
        """
        if validated is None:
            extension, row_count = self.validate(filename, content, sheet_name)
        else:
            # Even a pre-validated upload must keep the filename safety rule.
            extension = self._extension(filename)
            if extension != validated.extension:
                raise UploadStorageError("Upload a CSV, XLS, XLSX, or XLSM file.")
            self._check_content(extension, content)
            row_count = validated.row_count
        self._user_id(user_id)
        opaque_name = f"{uuid4().hex}.{extension}"
        storage_key = f"{user_id}/{opaque_name}"
        self._validated_key(user_id, storage_key)
        try:
            self._put(storage_key, content)
        except UploadStorageError:
            raise
        except OSError as error:
            raise UploadStorageError("The uploaded file could not be stored.") from error
        return StoredUpload(storage_key, filename, extension, hashlib.sha256(content).hexdigest(), row_count, len(content))

    def read(self, user_id: int, storage_key: str, expected_sha256: str | None = None) -> bytes:
        self._validated_key(user_id, storage_key)
        try:
            content = self._get(storage_key)
        except UploadStorageError:
            raise
        except OSError as error:
            raise UploadStorageError("Uploaded file is unavailable.") from error
        if expected_sha256 and hashlib.sha256(content).hexdigest() != expected_sha256:
            raise UploadStorageError("Uploaded file failed its integrity check and is unavailable.")
        return content

    def delete(self, user_id: int, storage_key: str) -> None:
        self._validated_key(user_id, storage_key)
        try:
            self._delete(storage_key)
        except FileNotFoundError:
            return
        except UploadStorageError:
            raise
        except OSError as error:
            raise UploadStorageError("Uploaded file could not be deleted.") from error

    def store_and_record(self, user_id: int, filename: str, content: bytes,
                         record: Callable[[StoredUpload], None], sheet_name: str | None = None,
                         validated: ValidatedUpload | None = None) -> StoredUpload:
        """Remove only the just-created file when metadata persistence fails.

        Cleanup is best effort: if the storage delete also fails, the original
        metadata error is still raised and the orphan is logged for manual
        reconciliation.  Automated reconciliation is not implemented, so an
        operator can later remove ``<R2_KEY_PREFIX>/<storage_key>`` or
        ``<upload root>/<storage_key>`` using the logged opaque key.
        """
        stored = self.store(user_id, filename, content, sheet_name, validated=validated)
        try:
            record(stored)
        except Exception:
            try:
                self.delete(user_id, stored.storage_key)
            except Exception as cleanup_error:  # noqa: BLE001 - the metadata error must win
                # Only the owner id, opaque key and exception type are logged:
                # never file contents, checksums, credentials, or environment
                # values.
                logger.error(
                    "Persistent-upload cleanup failed user_id=%s storage_key=%s error=%s; "
                    "the object may be orphaned and can be reconciled manually.",
                    user_id,
                    stored.storage_key,
                    type(cleanup_error).__name__,
                )
            raise
        return stored

    def delete_and_forget(self, user_id: int, storage_key: str, forget: Callable[[], None]) -> None:
        """Delete the object, then remove its owner metadata.

        If deletion fails, metadata is kept and the whole call can be retried.
        If ``forget`` fails after a successful delete, retrying is still safe
        because ``delete()`` treats an already-missing object as success.  Until
        that retry succeeds the metadata references a missing object (reads
        report it as unavailable); no other tenant's data is affected.
        """
        self.delete(user_id, storage_key)
        forget()


class UploadStorage(BaseUploadStorage):
    """Filesystem backend: one non-public, numeric user directory per tenant."""

    def __init__(
        self,
        root: str | Path,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        max_excel_bytes: int | None = None,
    ):
        super().__init__(max_upload_bytes, max_excel_bytes)
        self.root = Path(root).expanduser().resolve()

    @classmethod
    def from_environment(cls, project_root: str | Path) -> "UploadStorage":
        configured = os.getenv("RETAIL_UPLOAD_STORAGE_DIR")
        # This location is deliberately outside Streamlit's static/public tree.
        root = Path(configured) if configured else Path(project_root) / "var" / "user_uploads"
        return cls(root)

    def _user_directory(self, user_id: int) -> Path:
        return self.root / str(self._user_id(user_id))

    def _path_for(self, user_id: int, storage_key: str) -> Path:
        """Resolve an opaque DB key and reject traversal or another user's key."""
        key = self._validated_key(user_id, storage_key)
        user_directory = self._user_directory(user_id).resolve()
        candidate = (self.root / Path(*key.parts)).resolve()
        try:
            candidate.relative_to(user_directory)
        except ValueError as error:
            raise UploadStorageError("Uploaded file is unavailable.") from error
        if candidate.parent != user_directory:
            raise UploadStorageError("Uploaded file is unavailable.")
        return candidate

    def _put(self, storage_key: str, content: bytes) -> None:
        user_id = int(storage_key.split("/", 1)[0])
        destination = self._path_for(user_id, storage_key)
        user_directory = destination.parent
        user_directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=user_directory)
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        except OSError as error:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
            raise UploadStorageError("The uploaded file could not be stored.") from error

    def _get(self, storage_key: str) -> bytes:
        user_id = int(storage_key.split("/", 1)[0])
        return self._path_for(user_id, storage_key).read_bytes()

    def _delete(self, storage_key: str) -> None:
        user_id = int(storage_key.split("/", 1)[0])
        self._path_for(user_id, storage_key).unlink()
