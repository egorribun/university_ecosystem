"""Behavior and failure-path tests for app/services/minio_storage.py.

The Minio SDK class is patched at the module seam (app.services.minio_storage.Minio)
BEFORE constructing MinIOClient — all SDK calls become MagicMocks executed through
the real thread pool (they're sync mocks, safe).

S3Error signature verified against the installed minio package
(.venv/.../minio/error.py:98): S3Error(response, code, message, resource,
request_id, host_id, ...) — response comes FIRST.

get_minio_client() singleton tests temporarily rebind app.core.config.settings to a
SimpleNamespace via monkeypatch (the function does a call-time `from app.core.config
import settings`, so it sees the stub; monkeypatch restores the ORIGINAL settings
object afterwards — identity preserved, no config reload → mutmut clean-test safe).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from minio.error import S3Error

import app.services.minio_storage as minio_module
from app.services.minio_storage import MinIOClient, get_minio_client


def _s3_error(code: str = "NoSuchBucket") -> S3Error:
    return S3Error(
        MagicMock(),  # response
        code,
        "boom",
        "resource",
        "request-id",
        "host-id",
    )


@pytest.fixture
def minio_cls(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    cls = MagicMock(name="MinioClass")
    monkeypatch.setattr(minio_module, "Minio", cls)
    return cls


@pytest.fixture
def client(minio_cls: MagicMock) -> MinIOClient:
    return MinIOClient(
        endpoint="minio:9000",
        access_key="test-access",  # pragma: allowlist secret
        secret_key="test-secret",  # pragma: allowlist secret
        secure=False,
        default_bucket="uploads",
    )


# ------------------------------------------------------------- initialize


async def test_initialize_bucket_exists(client: MinIOClient) -> None:
    client._client.bucket_exists.return_value = True
    await client.initialize()
    assert client._initialized is True
    client._client.make_bucket.assert_not_called()


async def test_initialize_creates_missing_bucket(client: MinIOClient) -> None:
    client._client.bucket_exists.return_value = False
    await client.initialize()
    client._client.make_bucket.assert_called_once_with("uploads")
    assert client._initialized is True


async def test_initialize_short_circuits_second_call(client: MinIOClient) -> None:
    client._client.bucket_exists.return_value = True
    await client.initialize()
    await client.initialize()
    client._client.bucket_exists.assert_called_once()


async def test_initialize_s3_error_logged_and_raised(client: MinIOClient) -> None:
    client._client.bucket_exists.side_effect = _s3_error()
    with patch.object(minio_module.logger, "error") as error_logger:
        with pytest.raises(S3Error):
            await client.initialize()
    assert "Failed to initialize MinIO" in str(error_logger.call_args.args[0])
    assert client._initialized is False


# ------------------------------------------------------------ upload_file


async def test_upload_file_default_bucket(client: MinIOClient) -> None:
    data = BytesIO(b"hello world")
    data.seek(5)  # upload must rewind before sizing
    result = await client.upload_file("docs/a.txt", data, content_type="text/plain")
    assert result == "docs/a.txt"
    args, kwargs = client._client.put_object.call_args
    assert args[0] == "uploads"
    assert args[1] == "docs/a.txt"
    assert args[3] == 11  # full buffer size, post-rewind
    assert kwargs["content_type"] == "text/plain"


async def test_upload_file_explicit_bucket(client: MinIOClient) -> None:
    await client.upload_file("b.bin", BytesIO(b"x"), bucket="custom")
    args, kwargs = client._client.put_object.call_args
    assert args[0] == "custom"
    assert kwargs["content_type"] == "application/octet-stream"


# --------------------------------------------------------- presigned URLs


async def test_get_presigned_url(client: MinIOClient) -> None:
    client._client.presigned_get_object.return_value = "https://signed/get"
    url = await client.get_presigned_url("obj", expires=timedelta(minutes=5))
    assert url == "https://signed/get"
    args, kwargs = client._client.presigned_get_object.call_args
    assert args == ("uploads", "obj")
    assert kwargs["expires"] == timedelta(minutes=5)


async def test_get_presigned_upload_url_explicit_bucket(client: MinIOClient) -> None:
    client._client.presigned_put_object.return_value = "https://signed/put"
    url = await client.get_presigned_upload_url("obj2", bucket="media")
    assert url == "https://signed/put"
    args, _ = client._client.presigned_put_object.call_args
    assert args == ("media", "obj2")


# ----------------------------------------------------------- delete_object


async def test_delete_object(client: MinIOClient) -> None:
    await client.delete_object("old.txt")
    client._client.remove_object.assert_called_once_with("uploads", "old.txt")


# -------------------------------------------------------- get_minio_client


def test_get_minio_client_default_credentials_warns(
    minio_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(minio_module, "_minio_client", None)
    stub_settings = SimpleNamespace(
        minio_endpoint="minio:9000", minio_secure=False, minio_bucket="uploads"
    )  # no access/secret attrs -> getattr defaults ("minioadmin") kick in
    monkeypatch.setattr("app.core.config.settings", stub_settings)

    with patch.object(minio_module.logger, "warning") as warning_logger:
        instance = get_minio_client()

    warning_logger.assert_called_once_with(
        "MinIO factory defaults are active; override both access "
        "settings before staging or production"
    )
    warning_message = str(warning_logger.call_args.args[0])
    assert "factory defaults" in warning_message
    assert "minioadmin" not in warning_message
    assert isinstance(instance, MinIOClient)
    _, kwargs = minio_cls.call_args
    assert kwargs["access_key"] == "minioadmin"  # pragma: allowlist secret


def test_get_minio_client_custom_credentials_no_warning(
    minio_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(minio_module, "_minio_client", None)
    stub_settings = SimpleNamespace(
        minio_endpoint="s3.internal:9000",
        minio_secure=True,
        minio_bucket="media",
        minio_access_key="real-access",  # pragma: allowlist secret
        minio_secret_key="real-secret",  # pragma: allowlist secret
    )
    monkeypatch.setattr("app.core.config.settings", stub_settings)

    with caplog.at_level(logging.WARNING):
        instance = get_minio_client()

    assert "default credentials" not in caplog.text
    assert instance._default_bucket == "media"
    args, kwargs = minio_cls.call_args
    assert args[0] == "s3.internal:9000"
    assert kwargs["secure"] is True


def test_get_minio_client_fast_path_identity(
    minio_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(minio_module, "_minio_client", None)
    stub_settings = SimpleNamespace(
        minio_endpoint="minio:9000", minio_secure=False, minio_bucket="uploads"
    )
    monkeypatch.setattr("app.core.config.settings", stub_settings)

    first = get_minio_client()
    second = get_minio_client()  # fast path — no lock, same instance
    assert first is second
    minio_cls.assert_called_once()


def test_get_minio_client_second_lock_check_returns_racing_instance(monkeypatch):
    sentinel = object()

    class _RaceLock:
        def __enter__(self):
            minio_module._minio_client = sentinel
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(minio_module, "_minio_client", None)
    monkeypatch.setattr(minio_module, "_minio_client_lock", _RaceLock())

    assert get_minio_client() is sentinel
