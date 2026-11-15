"""Configuration-selection tests for upload storage backends."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.storage.r2 as r2_module
from src.storage.factory import (
    reset_storage_cache,
    storage_backend,
    storage_from_environment,
    validate_storage_configuration,
)
from src.storage.r2 import R2Config, R2UploadStorage, StorageConfigurationError
from src.storage.uploads import UploadStorage

R2_ENV = {
    "RETAIL_UPLOAD_STORAGE_BACKEND": "r2",
    "R2_ACCOUNT_ID": "account123",
    "R2_ACCESS_KEY_ID": "access-key",
    "R2_SECRET_ACCESS_KEY": "secret-key",
    "R2_BUCKET_NAME": "retailmind-test",
    "R2_REGION": "auto",
    "R2_KEY_PREFIX": "uploads",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (*R2_ENV, "RETAIL_UPLOAD_STORAGE_DIR", "R2_ENDPOINT_URL"):
        monkeypatch.delenv(name, raising=False)
    reset_storage_cache()
    yield
    reset_storage_cache()


def configure_r2(monkeypatch, **overrides: str) -> None:
    for name, value in {**R2_ENV, **overrides}.items():
        monkeypatch.setenv(name, value)


def test_unset_backend_defaults_to_filesystem(monkeypatch, tmp_path: Path):
    assert storage_backend() == "filesystem"
    assert validate_storage_configuration(tmp_path) == "filesystem"
    storage = storage_from_environment(tmp_path)
    assert isinstance(storage, UploadStorage)
    assert storage.root == (tmp_path / "var" / "user_uploads").resolve()


def test_explicit_filesystem_uses_the_configured_directory(monkeypatch, tmp_path: Path):
    desired = tmp_path / "store"
    monkeypatch.setenv("RETAIL_UPLOAD_STORAGE_BACKEND", "filesystem")
    monkeypatch.setenv("RETAIL_UPLOAD_STORAGE_DIR", str(desired))

    storage = storage_from_environment(tmp_path)

    assert isinstance(storage, UploadStorage)
    assert storage.root == desired.resolve()


def test_complete_r2_configuration_builds_a_cached_r2_backend(monkeypatch, tmp_path: Path):
    configure_r2(monkeypatch)
    fake_client = object()
    monkeypatch.setattr(r2_module, "_create_client", lambda config: fake_client)

    assert validate_storage_configuration(tmp_path) == "r2"
    first = storage_from_environment(tmp_path)
    second = storage_from_environment(tmp_path)

    assert isinstance(first, R2UploadStorage)
    assert first is second
    assert first._client is fake_client
    assert first.config.bucket == "retailmind-test"


def test_changing_r2_configuration_rebuilds_the_cached_backend(monkeypatch, tmp_path: Path):
    configure_r2(monkeypatch)
    monkeypatch.setattr(r2_module, "_create_client", lambda config: object())

    first = storage_from_environment(tmp_path)
    configure_r2(monkeypatch, R2_BUCKET_NAME="other-bucket")
    second = storage_from_environment(tmp_path)

    assert first is not second
    assert isinstance(second, R2UploadStorage)
    assert second.config.bucket == "other-bucket"


def test_rotating_only_the_secret_rebuilds_the_cached_backend(monkeypatch, tmp_path: Path):
    configure_r2(monkeypatch)
    monkeypatch.setattr(r2_module, "_create_client", lambda config: object())

    first = storage_from_environment(tmp_path)
    configure_r2(monkeypatch, R2_SECRET_ACCESS_KEY="rotated-secret")
    second = storage_from_environment(tmp_path)

    assert first is not second
    assert isinstance(second, R2UploadStorage)


@pytest.mark.parametrize("missing", ["R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"])
def test_missing_r2_secret_fails_fast_and_names_the_variable(monkeypatch, tmp_path: Path, missing: str):
    configure_r2(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(StorageConfigurationError, match=missing):
        validate_storage_configuration(tmp_path)
    with pytest.raises(StorageConfigurationError, match=missing):
        storage_from_environment(tmp_path)


def test_missing_account_and_endpoint_fails_fast(monkeypatch, tmp_path: Path):
    configure_r2(monkeypatch)
    monkeypatch.delenv("R2_ACCOUNT_ID")

    with pytest.raises(StorageConfigurationError, match="R2_ACCOUNT_ID"):
        storage_from_environment(tmp_path)


def test_endpoint_can_be_supplied_instead_of_account_id(monkeypatch):
    configure_r2(monkeypatch)
    monkeypatch.delenv("R2_ACCOUNT_ID")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://custom.example.com/")

    config = R2Config.from_environment()

    assert config.endpoint_url == "https://custom.example.com"
    assert config.object_key("7/file.csv") == "uploads/7/file.csv"


def test_insecure_endpoint_is_rejected(monkeypatch):
    configure_r2(monkeypatch, R2_ENDPOINT_URL="http://insecure.example.com")

    with pytest.raises(StorageConfigurationError, match="https://"):
        R2Config.from_environment()


@pytest.mark.parametrize("prefix", ["../evil", "a//b", "."])
def test_unsafe_key_prefix_is_rejected(monkeypatch, prefix: str):
    configure_r2(monkeypatch, R2_KEY_PREFIX=prefix)

    with pytest.raises(StorageConfigurationError, match="R2_KEY_PREFIX"):
        R2Config.from_environment()


def test_unknown_backend_is_rejected(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RETAIL_UPLOAD_STORAGE_BACKEND", "s3")

    with pytest.raises(StorageConfigurationError, match="RETAIL_UPLOAD_STORAGE_BACKEND"):
        storage_from_environment(tmp_path)


def test_r2_mode_never_falls_back_to_filesystem(monkeypatch, tmp_path: Path):
    configure_r2(monkeypatch)
    monkeypatch.delenv("R2_BUCKET_NAME")

    with pytest.raises(StorageConfigurationError):
        storage_from_environment(tmp_path)
    # No local upload directory is created as a side effect of the failure.
    assert not (tmp_path / "var" / "user_uploads").exists()


def test_blank_backend_value_is_treated_as_filesystem(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RETAIL_UPLOAD_STORAGE_BACKEND", "  ")

    assert storage_backend() == "filesystem"
    assert isinstance(storage_from_environment(tmp_path), UploadStorage)
