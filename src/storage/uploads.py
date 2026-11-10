"""Validated, user-owned filesystem storage for uploaded dashboard datasets."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Callable
from uuid import uuid4
import logging

from data_sources import detect_column_mapping, profile_data, read_uploaded_file

logger = logging.getLogger(__name__)


ALLOWED_EXTENSIONS = frozenset({"csv", "xls", "xlsx", "xlsm"})
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UploadStorageError(ValueError):
    """A safe message for an upload or stored-file access failure."""


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    original_filename: str
    file_type: str
    sha256: str
    row_count: int
    size_bytes: int


class UploadStorage:
    """Keep each validated upload below one non-public, numeric user directory."""

    def __init__(self, root: str | Path, max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES):
        self.root = Path(root).expanduser().resolve()
        self.max_upload_bytes = max_upload_bytes

    @classmethod
    def from_environment(cls, project_root: str | Path) -> "UploadStorage":
        configured = os.getenv("RETAIL_UPLOAD_STORAGE_DIR")
        # This location is deliberately outside Streamlit's static/public tree.
        root = Path(configured) if configured else Path(project_root) / "var" / "user_uploads"
        return cls(root)

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

    def _user_directory(self, user_id: int) -> Path:
        return self.root / str(self._user_id(user_id))

    def _path_for(self, user_id: int, storage_key: str) -> Path:
        """Resolve an opaque DB key and reject traversal or another user's key."""
        user_directory = self._user_directory(user_id).resolve()
        key = PurePosixPath(storage_key)
        if key.is_absolute() or len(key.parts) != 2 or key.parts[0] != str(user_id):
            raise UploadStorageError("Uploaded file is unavailable.")
        if any(part in {"", ".", ".."} for part in key.parts):
            raise UploadStorageError("Uploaded file is unavailable.")
        candidate = (self.root / Path(*key.parts)).resolve()
        try:
            candidate.relative_to(user_directory)
        except ValueError as error:
            raise UploadStorageError("Uploaded file is unavailable.") from error
        if candidate.parent != user_directory:
            raise UploadStorageError("Uploaded file is unavailable.")
        return candidate

    def validate(self, filename: str, content: bytes, sheet_name: str | None = None) -> tuple[str, int]:
        """Validate type, size, readability, and dashboard-required source fields."""
        extension = self._extension(filename)
        if not isinstance(content, bytes) or not content:
            raise UploadStorageError("The uploaded file is empty.")
        if len(content) > self.max_upload_bytes:
            raise UploadStorageError("Upload a file smaller than 25 MB.")
        try:
            frame = read_uploaded_file(content, filename, sheet_name)
            profile = profile_data(frame, detect_column_mapping(frame.columns))
        except (ValueError, OSError, UnicodeError) as error:
            raise UploadStorageError("Could not read the uploaded file. Check that it is valid and readable.") from error
        if profile["errors"]:
            raise UploadStorageError(str(profile["errors"][0]))
        return extension, len(frame)

    def store(self, user_id: int, filename: str, content: bytes, sheet_name: str | None = None) -> StoredUpload:
        """Store only after validating the exact worksheet selected by the user."""
        extension, row_count = self.validate(filename, content, sheet_name)
        user_directory = self._user_directory(user_id)
        user_directory.mkdir(parents=True, exist_ok=True)
        opaque_name = f"{uuid4().hex}.{extension}"
        storage_key = f"{user_id}/{opaque_name}"
        destination = self._path_for(user_id, storage_key)
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
        return StoredUpload(storage_key, filename, extension, hashlib.sha256(content).hexdigest(), row_count, len(content))

    def read(self, user_id: int, storage_key: str, expected_sha256: str | None = None) -> bytes:
        path = self._path_for(user_id, storage_key)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise UploadStorageError("Uploaded file is unavailable.") from error
        if expected_sha256 and hashlib.sha256(content).hexdigest() != expected_sha256:
            raise UploadStorageError("Uploaded file failed its integrity check and is unavailable.")
        return content

    def delete(self, user_id: int, storage_key: str) -> None:
        path = self._path_for(user_id, storage_key)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError as error:
            raise UploadStorageError("Uploaded file could not be deleted.") from error

    def store_and_record(self, user_id: int, filename: str, content: bytes,
                         record: Callable[[StoredUpload], None], sheet_name: str | None = None) -> StoredUpload:
        """Remove only the just-created file when metadata persistence fails."""
        stored = self.store(user_id, filename, content, sheet_name)
        try:
            record(stored)
        except Exception:
            try:
                self.delete(user_id, stored.storage_key)
            except UploadStorageError:
                # The opaque key permits an administrator to reconcile an orphan
                # without logging file contents, checksums, credentials, or paths.
                logger.error("Persistent-upload cleanup failed user_id=%s storage_key=%s", user_id, stored.storage_key)
            raise
        return stored

    def delete_and_forget(self, user_id: int, storage_key: str, forget: Callable[[], None]) -> None:
        """Keep owner metadata when file deletion fails; a later retry is safe."""
        self.delete(user_id, storage_key)
        # If this fails, the DB record remains and retrying is safe because delete()
        # treats an already-missing file as a successful cleanup.
        forget()
