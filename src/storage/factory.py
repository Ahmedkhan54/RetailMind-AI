"""Select the upload storage backend from environment configuration.

The filesystem backend stays the default.  Enabling R2 never falls back to the
ephemeral disk: incomplete configuration raises at startup so a deployment fails
loudly instead of silently losing user uploads.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from .r2 import R2Config, R2UploadStorage, StorageConfigurationError
from .uploads import UploadStorage

BACKEND_ENV = "RETAIL_UPLOAD_STORAGE_BACKEND"
FILESYSTEM_BACKEND = "filesystem"
R2_BACKEND = "r2"
SUPPORTED_BACKENDS = frozenset({FILESYSTEM_BACKEND, R2_BACKEND})

_CACHE: dict[tuple[str, str, str, str, str, str], R2UploadStorage] = {}
_CACHE_LOCK = Lock()


def storage_backend() -> str:
    configured = ((os.getenv(BACKEND_ENV) or "").strip().lower() or FILESYSTEM_BACKEND)
    if configured not in SUPPORTED_BACKENDS:
        raise StorageConfigurationError(
            f"{BACKEND_ENV} must be one of: {', '.join(sorted(SUPPORTED_BACKENDS))}. "
            f"Received an unsupported value."
        )
    return configured


def validate_storage_configuration(project_root: str | Path | None = None) -> str:
    """Return the active backend, raising on invalid or incomplete config.

    Called once at application startup.  Only variable names appear in errors.
    """
    backend = storage_backend()
    if backend == R2_BACKEND:
        R2Config.from_environment()
    return backend


def storage_from_environment(project_root: str | Path) -> UploadStorage | R2UploadStorage:
    """Build the configured backend without ever falling back to disk in R2 mode."""
    backend = storage_backend()
    if backend == FILESYSTEM_BACKEND:
        return UploadStorage.from_environment(project_root)
    config = R2Config.from_environment()
    cache_key = config.cache_key()
    with _CACHE_LOCK:
        storage = _CACHE.get(cache_key)
        if storage is None:
            storage = R2UploadStorage(config)
            _CACHE[cache_key] = storage
        return storage


def reset_storage_cache() -> None:
    """Clear cached R2 clients (tests and deliberate credential rotation)."""
    with _CACHE_LOCK:
        _CACHE.clear()
