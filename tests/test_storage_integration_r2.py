"""Opt-in round-trip test against a real private R2 bucket.

Run only after the backend has a scoped R2 token:

    R2_INTEGRATION=1 RETAIL_UPLOAD_STORAGE_BACKEND=r2 R2_ACCOUNT_ID=... \
    R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET_NAME=... \
    .venv\\Scripts\\python.exe -m pytest tests/test_storage_integration_r2.py

It writes one UUID-named object and deletes it again.  It never touches
production metadata or existing keys, and is skipped by default.
"""

from __future__ import annotations

import os

import pytest

from src.storage.r2 import R2Config, R2UploadStorage
from src.storage.uploads import UploadStorageError

CSV = b"Order_ID,Order_Date,City,Product_Category,Product_Name,Sales\nA,2025-01-01,Delhi,Office,Pen,100\n"


@pytest.mark.skipif(os.getenv("R2_INTEGRATION") != "1", reason="set R2_INTEGRATION=1 with a real bucket to run")
def test_real_bucket_upload_read_restart_and_delete():
    pytest.importorskip("boto3")
    storage = R2UploadStorage(R2Config.from_environment())
    stored = storage.store(7, "sales.csv", CSV)
    try:
        assert stored.storage_key.startswith("7/")
        assert storage.read(7, stored.storage_key, stored.sha256) == CSV
        # A fresh instance models a backend restart with an empty frame cache.
        assert R2UploadStorage(R2Config.from_environment()).read(7, stored.storage_key, stored.sha256) == CSV
    finally:
        storage.delete(7, stored.storage_key)

    with pytest.raises(UploadStorageError):
        storage.read(7, stored.storage_key)
