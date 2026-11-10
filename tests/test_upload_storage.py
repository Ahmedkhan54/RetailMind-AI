from __future__ import annotations

from pathlib import Path
from io import BytesIO

import pandas as pd
import pytest

from src.storage.uploads import UploadStorage, UploadStorageError


CSV = b"Order_ID,Order_Date,City,Product_Category,Product_Name,Sales\nA,2025-01-01,Delhi,Office,Pen,100\n"


def test_upload_persists_across_storage_instances_and_uses_opaque_names(tmp_path: Path):
    storage = UploadStorage(tmp_path)
    first = storage.store(7, "sales.csv", CSV)
    second = storage.store(7, "sales.csv", CSV)

    assert first.storage_key != second.storage_key
    assert storage.read(7, first.storage_key) == CSV
    # A fresh instance models a later login/application process.
    assert UploadStorage(tmp_path).read(7, first.storage_key) == CSV
    assert first.storage_key.startswith("7/")
    assert Path(first.storage_key).name != "sales.csv"


def test_storage_rejects_invalid_content_and_client_path_tricks(tmp_path: Path):
    storage = UploadStorage(tmp_path)
    with pytest.raises(UploadStorageError, match="sales"):
        storage.store(7, "missing.csv", b"City\nDelhi\n")
    with pytest.raises(UploadStorageError):
        storage.store(7, "../sales.csv", CSV)
    with pytest.raises(UploadStorageError):
        storage.store(7, "sales.exe", CSV)


def test_user_directory_and_reads_are_strictly_owner_scoped(tmp_path: Path):
    storage = UploadStorage(tmp_path)
    stored = storage.store(7, "sales.csv", CSV)
    assert storage.read(7, stored.storage_key) == CSV
    with pytest.raises(UploadStorageError):
        storage.read(8, stored.storage_key)
    with pytest.raises(UploadStorageError):
        storage.read(7, "7/../8/secret.csv")


def test_delete_only_removes_the_authenticated_users_file(tmp_path: Path):
    storage = UploadStorage(tmp_path)
    owner = storage.store(7, "sales.csv", CSV)
    other = storage.store(8, "sales.csv", CSV)
    storage.delete(7, owner.storage_key)
    with pytest.raises(UploadStorageError):
        storage.read(7, owner.storage_key)
    assert storage.read(8, other.storage_key) == CSV


def test_selected_excel_worksheet_is_validated_instead_of_the_first_sheet(tmp_path: Path):
    workbook = BytesIO()
    with pd.ExcelWriter(workbook) as writer:
        pd.DataFrame({"Notes": ["not dashboard data"]}).to_excel(writer, sheet_name="Cover", index=False)
        pd.DataFrame({"Sales": [100], "City": ["Delhi"]}).to_excel(writer, sheet_name="Sales data", index=False)
    storage = UploadStorage(tmp_path)

    stored = storage.store(7, "workbook.xlsx", workbook.getvalue(), sheet_name="Sales data")
    assert stored.row_count == 1
    with pytest.raises(UploadStorageError):
        storage.store(7, "workbook.xlsx", workbook.getvalue(), sheet_name="Cover")


@pytest.mark.parametrize("sheet_name", ["Missing", "../not-a-worksheet"])
def test_missing_or_invalid_excel_worksheet_is_rejected(tmp_path: Path, sheet_name: str):
    workbook = BytesIO()
    pd.DataFrame({"Sales": [100]}).to_excel(workbook, index=False)
    with pytest.raises(UploadStorageError, match="Could not read"):
        UploadStorage(tmp_path).store(7, "workbook.xlsx", workbook.getvalue(), sheet_name=sheet_name)


def test_checksum_mismatch_blocks_reading_a_modified_file(tmp_path: Path):
    storage = UploadStorage(tmp_path)
    stored = storage.store(7, "sales.csv", CSV)
    path = tmp_path / stored.storage_key
    path.write_bytes(CSV + b"tampered")
    with pytest.raises(UploadStorageError, match="integrity"):
        storage.read(7, stored.storage_key, stored.sha256)


def test_metadata_failure_removes_only_the_newly_written_file(tmp_path: Path):
    storage = UploadStorage(tmp_path)
    with pytest.raises(RuntimeError, match="database unavailable"):
        storage.store_and_record(7, "sales.csv", CSV, lambda stored: (_ for _ in ()).throw(RuntimeError("database unavailable")))
    assert list((tmp_path / "7").glob("*")) == []


def test_cleanup_failure_logs_only_opaque_recovery_information(tmp_path: Path, caplog, monkeypatch):
    storage = UploadStorage(tmp_path)
    monkeypatch.setattr(storage, "delete", lambda user_id, storage_key: (_ for _ in ()).throw(UploadStorageError("delete failed")))
    with pytest.raises(RuntimeError):
        storage.store_and_record(7, "sales.csv", CSV, lambda stored: (_ for _ in ()).throw(RuntimeError("metadata failed")))
    assert "Persistent-upload cleanup failed user_id=7 storage_key=7/" in caplog.text
    assert "Order_ID" not in caplog.text


def test_delete_failure_keeps_metadata_callback_unrun_and_allows_retry(tmp_path: Path, monkeypatch):
    storage = UploadStorage(tmp_path)
    stored = storage.store(7, "sales.csv", CSV)
    forgotten = []
    monkeypatch.setattr(storage, "delete", lambda user_id, storage_key: (_ for _ in ()).throw(UploadStorageError("delete failed")))
    with pytest.raises(UploadStorageError):
        storage.delete_and_forget(7, stored.storage_key, lambda: forgotten.append(True))
    assert forgotten == []
    monkeypatch.undo()
    storage.delete_and_forget(7, stored.storage_key, lambda: forgotten.append(True))
    assert forgotten == [True]
