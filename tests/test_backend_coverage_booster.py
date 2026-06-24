import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.group_service import GroupService
from app.utils.migrations import (
    migrations_are_current,
    reset_migration_cache,
)
from app.utils.pagination import (
    CursorParams,
    decode_cursor,
    decode_datetime_cursor,
    paginate_cursor,
)
from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7


def test_uuid7_edge_cases():
    # 1. dt with timezone
    dt_aware = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
    u_aware = generate_uuid7(dt=dt_aware)
    assert u_aware.version == 7
    ts_aware = extract_timestamp_from_uuid_v7(u_aware)
    assert abs((ts_aware - dt_aware).total_seconds()) < 0.01

    # 2. dt without timezone (naive)
    dt_naive = datetime.datetime(2026, 1, 1, 12, 0, 0)
    u_naive = generate_uuid7(dt=dt_naive)
    assert u_naive.version == 7


@pytest.mark.asyncio
async def test_migrations_engine_path():
    reset_migration_cache()

    # Mock the alembic script directory
    mock_script = MagicMock()
    mock_script.get_heads.return_value = ["head_xyz"]

    # Mock the database connection/result
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([("head_xyz",)]))

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_result)

    # Mock engine that yields connection
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock()

    with patch("app.utils.migrations.get_alembic_script", return_value=mock_script):
        is_current, current, expected = await migrations_are_current(engine=mock_engine)
        assert is_current is True
        assert current == {"head_xyz"}
        assert expected == {"head_xyz"}

    reset_migration_cache()


def test_decode_cursor_exceptions():
    # Test ValueError/TypeError in decode_cursor
    assert decode_cursor("not-base64-!") == ""
    # Test UnicodeDecodeError (passing bytes that cannot decode as UTF-8)
    # base64 representation of 0xff 0xff (invalid utf-8 bytes)
    assert decode_cursor("//8=") == ""


def test_decode_datetime_cursor_exceptions():
    assert decode_datetime_cursor(None) is None
    assert decode_datetime_cursor("") is None
    assert decode_datetime_cursor("no_colon") is None
    assert decode_datetime_cursor("notanint:id") is None
    assert decode_datetime_cursor("1234567890:id:extra") == (
        datetime.datetime(1970, 1, 1, 0, 20, 34, 567890, tzinfo=datetime.UTC),
        "id:extra",
    )
    # Test OverflowError/OSError
    assert decode_datetime_cursor("9999999999999999999999:id") is None


@pytest.mark.asyncio
async def test_paginate_cursor_uuid_cast_failure():
    # We want to test line 139 (ValueError/TypeError catch in uuid.UUID(cursor_value))
    mock_session = AsyncMock()
    # A cursor string that is >= 32 chars but NOT a valid UUID hex
    # (e.g. "x" * 32)
    import base64

    invalid_uuid_cursor = base64.urlsafe_b64encode(b"x" * 32).decode()

    params = CursorParams(cursor=invalid_uuid_cursor, limit=10)

    mock_stmt = MagicMock()
    mock_column = MagicMock()
    mock_column.key = "id"
    mock_column.__lt__ = MagicMock(return_value=MagicMock())

    # We mock scalars to return empty result
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.scalars = AsyncMock(return_value=mock_result)

    res = await paginate_cursor(
        session=mock_session,
        stmt=mock_stmt,
        cursor_column=mock_column,
        params=params,
        descending=True,
    )
    assert len(res.items) == 0
    assert res.next_cursor is None
    assert res.has_more is False


@pytest.mark.asyncio
async def test_group_service_list_groups():
    # Covers GroupService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.list_groups = AsyncMock(return_value=[])

    service = GroupService(db=mock_db, repo=mock_repo)
    res = await service.get_groups()
    assert res == []
    mock_repo.list_groups.assert_awaited_once()


@pytest.mark.asyncio
async def test_paginate_cursor_ascending_and_has_more():
    # Tests descending=False, and has_more=True branches in paginate_cursor
    mock_session = AsyncMock()

    # We pass a valid cursor (e.g. encoded "abc")
    import base64

    cursor_val = base64.urlsafe_b64encode(b"abc").decode()
    params = CursorParams(cursor=cursor_val, limit=1)

    mock_stmt = MagicMock()
    mock_column = MagicMock()
    mock_column.key = "id"
    mock_column.__gt__ = MagicMock(return_value=MagicMock())

    class MockItem:
        def __init__(self, id_val):
            self.id = id_val

    mock_result = MagicMock()
    mock_result.all.return_value = [MockItem("abc"), MockItem("def")]
    mock_session.scalars = AsyncMock(return_value=mock_result)

    res = await paginate_cursor(
        session=mock_session,
        stmt=mock_stmt,
        cursor_column=mock_column,
        params=params,
        descending=False,
    )
    assert len(res.items) == 1
    assert res.items[0].id == "abc"
    assert res.has_more is True
    # check that next_cursor is base64 encoded "abc"
    assert res.next_cursor == base64.urlsafe_b64encode(b"abc").decode()


def test_optimize_image_edge_cases():
    from io import BytesIO

    from PIL import Image

    from app.utils.images import _resolve_resample_filter, optimize_image

    # 1. Create a large PNG data (10x10) to trigger resizing
    img = Image.new("RGB", (10, 10), color="red")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    png_data = buffer.getvalue()

    # 2. Test max_width <= 0 and max_height <= 0
    _optimized, mime = optimize_image(png_data, max_width=-1, max_height=-1)
    assert mime == "image/webp"

    # 3. Test thumbnail resizing logic (max_width=2, max_height=2)
    _optimized_small, mime_small = optimize_image(png_data, max_width=2, max_height=2)
    assert mime_small == "image/webp"

    # 4. Test invalid image data fallback
    with pytest.raises(ValueError, match="Invalid image data"):
        optimize_image(b"not-an-image-data-at-all")

    # 5. Test exif_transposed path
    with patch("app.utils.images.ImageOps.exif_transpose", return_value=img):
        _optimized_exif, mime_exif = optimize_image(png_data)
        assert mime_exif == "image/webp"

    with patch("app.utils.images.ImageOps.exif_transpose", return_value=None):
        _optimized_exif_none, mime_exif_none = optimize_image(png_data)
        assert mime_exif_none == "image/webp"

    # 6. Test _resolve_resample_filter when Resampling not in Image, but LANCZOS is
    with patch("app.utils.images.Image") as mock_image:
        del mock_image.Resampling
        mock_image.LANCZOS = 123
        assert _resolve_resample_filter() == 123

    # 7. Test _resolve_resample_filter when neither is present
    with patch("app.utils.images.Image") as mock_image:
        del mock_image.Resampling
        del mock_image.LANCZOS
        with pytest.raises(AttributeError, match="does not expose a LANCZOS filter"):
            _resolve_resample_filter()

    # 8. Test pyvips branch success
    mock_vips_opt = MagicMock(return_value=(png_data, "image/webp"))
    with (
        patch("app.utils.images.VIPS_AVAILABLE", True),
        patch("app.utils.images.optimize_image_vips", mock_vips_opt),
    ):
        _opt, mime = optimize_image(png_data)
        assert mime == "image/webp"
        mock_vips_opt.assert_called_once()

    # 9. Test pyvips branch failure and Pillow fallback
    mock_vips_opt_fail = MagicMock(side_effect=RuntimeError("vips error"))
    with (
        patch("app.utils.images.VIPS_AVAILABLE", True),
        patch("app.utils.images.optimize_image_vips", mock_vips_opt_fail),
    ):
        _opt, mime = optimize_image(png_data)
        assert mime == "image/webp"
        mock_vips_opt_fail.assert_called_once()


def test_encryption_edge_cases():
    from cryptography.fernet import Fernet

    from app.utils.encryption import (
        SpotifyEncryptionError,
        _build_cipher,
        _normalize_secret,
        decrypt_string,
        reset_cached_cipher,
        rotate_encrypted_string,
    )

    # 1. empty entry in normalize
    with pytest.raises(SpotifyEncryptionError, match="contains an empty entry"):
        _normalize_secret(" ")

    # 2. not configured cipher
    with pytest.raises(SpotifyEncryptionError, match="not configured"):
        _build_cipher("")

    # 3. decrypt non-empty bytes
    key = Fernet.generate_key().decode()
    with patch("app.core.config.settings.spotify_token_secret", key):
        reset_cached_cipher()
        cipher = Fernet(key.encode())
        token_bytes = cipher.encrypt(b"hello")
        decrypted = decrypt_string(token_bytes)
        assert decrypted == "hello"

    # 4. rotate encrypted string when not MultiFernet and passing bytes
    raw_val = b"some-token"
    res = rotate_encrypted_string(raw_val)
    assert res == "some-token"


@pytest.mark.asyncio
async def test_retry_async_no_jitter():
    from app.utils.retry import RetryExhausted, retry_async

    calls = []

    async def mock_fn():
        calls.append(1)
        raise ValueError("fail")

    with patch("asyncio.sleep", return_value=None):
        with pytest.raises(RetryExhausted):
            await retry_async(mock_fn, max_attempts=2, jitter=False, base_delay=0.1)

    assert len(calls) == 2


def test_sanitization_booster_edge_cases():
    from pathlib import Path

    from fastapi import HTTPException

    from app.utils.sanitization import (
        sanitize_filename,
        sanitize_path,
        sanitize_rich_text,
        sanitize_url,
    )

    # 1. nh3.clean exception in sanitize_rich_text
    with patch("nh3.clean", side_effect=Exception("nh3 error")):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_rich_text("some html")
        assert exc_info.value.status_code == 400

    # 2. no extension truncation in sanitize_filename
    assert sanitize_filename("A" * 300, max_length=10) == "A" * 10
    assert sanitize_filename("A" * 300 + ".", max_length=10) == "A" * 10
    assert sanitize_filename("A" * 300 + ".txt", max_length=10) == "AAAAAA.txt"

    # 3. ValueError/OSError in sanitize_path
    with patch.object(Path, "resolve", side_effect=OSError("invalid path")):
        assert sanitize_path("abc", "C:\\temp_dir") is None

    # 4. hostname is None in sanitize_url
    assert sanitize_url("http://:8080/path") is None

    # 5. hostname contains non-ASCII and doesn't start with xn--
    assert sanitize_url("http://тест.рф/path") is None

    # 6. private / local IP variants
    assert sanitize_url("http://192.168.1.1/path") is None
    assert sanitize_url("http://127.0.0.1/path") is None
    assert sanitize_url("http://169.254.1.1/path") is None
    assert sanitize_url("http://240.0.0.0/path") is None
    # 6b. public IP and valid domain (covers branch 266->270 and 272->279)
    assert sanitize_url("http://8.8.8.8/path") == "http://8.8.8.8/path"
    assert sanitize_url("http://example.com/path") == "http://example.com/path"

    # 7. urllib.parse.urlparse raises ValueError
    with patch("urllib.parse.urlparse", side_effect=ValueError("bad url")):
        assert sanitize_url("http://example.com") is None


@pytest.mark.asyncio
async def test_paginate_cursor_empty_decoded_and_null_last_val():
    from app.utils.pagination import CursorParams, paginate_cursor

    # Covers 130->148 branch (cursor decodes to empty) and 167->170 branch (last cursor value is None)
    mock_session = AsyncMock()

    # Cursor that decodes to empty
    params = CursorParams(cursor="invalid-base64-!", limit=1)

    mock_stmt = MagicMock()
    mock_column = MagicMock()
    mock_column.key = "id"

    class MockItem:
        def __init__(self, id_val):
            self.id = id_val

    mock_result = MagicMock()
    # Return two items to trigger has_more = True
    mock_result.all.return_value = [MockItem(None), MockItem(None)]
    mock_session.scalars = AsyncMock(return_value=mock_result)

    res = await paginate_cursor(
        session=mock_session,
        stmt=mock_stmt,
        cursor_column=mock_column,
        params=params,
        descending=True,
    )
    assert len(res.items) == 1
    assert res.items[0].id is None
    assert res.has_more is True
    assert (
        res.next_cursor is None
    )  # Because last_cursor_value is None (covers 167->170 branch)


def test_spotify_shim_coverage():
    import app.auth.spotify as spotify_shim
    assert spotify_shim.router is not None


@pytest.mark.asyncio
async def test_search_provider():
    from app.core.di.search import SearchProvider
    provider = SearchProvider()
    generator = provider.search_service()
    svc = await anext(generator)
    assert svc is not None
    try:
        await generator.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_app_exceptions():
    from app.core.exceptions import (
        ResourceNotFoundException,
        PermissionDeniedException,
        InvalidOperationException,
        app_exception_handler,
        AppException,
    )
    from fastapi import Request

    rnfe = ResourceNotFoundException("Not found", {"item": 1})
    assert rnfe.status_code == 404
    assert rnfe.code == "resource_not_found"

    pde = PermissionDeniedException("Denied", {"user": "guest"})
    assert pde.status_code == 403
    assert pde.code == "permission_denied"

    ioe = InvalidOperationException("Invalid", {"op": "write"})
    assert ioe.status_code == 400
    assert ioe.code == "invalid_operation"

    # Mock Request
    request = MagicMock(spec=Request)

    # Test handler with AppException
    resp1 = await app_exception_handler(request, rnfe)
    assert resp1.status_code == 404

    # Test handler with non-AppException
    resp2 = await app_exception_handler(request, ValueError("Oops"))
    assert resp2.status_code == 500


@pytest.mark.asyncio
async def test_content_size_limit_middleware():
    from app.core.middleware.content_size import ContentSizeLimitMiddleware
    from starlette.types import Scope, Receive, Send
    from starlette.requests import Request as StarletteRequest

    # Create dummy app
    async def dummy_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    # Test non-http scope
    mw = ContentSizeLimitMiddleware(dummy_app)
    scope = {"type": "lifespan", "query_string": b""}
    calls = []
    async def dummy_receive():
        return {"type": "lifespan.startup"}
    async def dummy_send(message):
        calls.append(message)
    await mw(scope, dummy_receive, dummy_send)

    # Test HTTP scope under limit
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/submit",
        "headers": [(b"content-length", b"10")],
        "query_string": b"",
    }
    calls = []
    async def receive():
        return {"type": "http.request", "body": b"1234567890", "more_body": False}
    async def send(message):
        calls.append(message)

    await mw(scope, receive, send)
    assert any(c.get("status") == 200 for c in calls)

    # Test HTTP scope exceeding limit (fast path content-length)
    mw_small = ContentSizeLimitMiddleware(dummy_app, max_bytes=5)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/submit",
        "headers": [(b"content-length", b"10")],
        "query_string": b"",
    }
    calls = []
    await mw_small(scope, receive, send)
    assert any(c.get("status") == 413 for c in calls)

    # Test HTTP scope with invalid Content-Length
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/submit",
        "headers": [(b"content-length", b"not-an-integer")],
        "query_string": b"",
    }
    calls = []
    await mw_small(scope, receive, send)
    assert any(c.get("status") == 400 for c in calls)

    # Test chunked/unknown length (slow path) exceeding limit
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/submit",
        "headers": [],
        "query_string": b"",
    }
    calls = []
    chunk_index = 0
    async def receive_chunks():
        nonlocal chunk_index
        if chunk_index == 0:
            chunk_index += 1
            return {"type": "http.request", "body": b"12345", "more_body": True}
        else:
            return {"type": "http.request", "body": b"67890", "more_body": False}

    await mw_small(scope, receive_chunks, send)
    assert any(c.get("status") == 413 for c in calls)

    # Test chunked/unknown length within limit (slow path)
    calls = []
    chunk_index = 0
    async def receive_small_chunks():
        nonlocal chunk_index
        if chunk_index == 0:
            chunk_index += 1
            return {"type": "http.request", "body": b"12", "more_body": True}
        else:
            return {"type": "http.request", "body": b"34", "more_body": False}

    await mw_small(scope, receive_small_chunks, send)
    assert any(c.get("status") == 200 for c in calls)

    # Test chunked/unknown length exceeding mem threshold to spill to disk
    mw_threshold = ContentSizeLimitMiddleware(dummy_app, max_bytes=100)
    mw_threshold._MEM_BUFFER_THRESHOLD = 5
    calls = []
    chunk_index = 0
    async def receive_spill_chunks():
        nonlocal chunk_index
        if chunk_index == 0:
            chunk_index += 1
            return {"type": "http.request", "body": b"1234", "more_body": True}
        elif chunk_index == 1:
            chunk_index += 1
            return {"type": "http.request", "body": b"5678", "more_body": False}
        else:
            return {"type": "http.request", "body": b"", "more_body": False}

    await mw_threshold(scope, receive_spill_chunks, send)
    assert any(c.get("status") == 200 for c in calls)


def test_configure_middleware_rate_limiting():
    from app.core.middleware.setup import configure_middleware
    from app.core.config import Settings
    from fastapi import FastAPI
    app = FastAPI()
    settings = Settings()
    settings.rate_limit_enabled = True
    settings.rate_limit_storage_backend = "redis"
    settings.rate_limit_storage_uri = "redis://localhost"
    settings.rate_limit_default_list = ["10/minute"]
    settings.rate_limit_news = "5/minute"
    settings.response_compression_enabled = True
    settings.trusted_proxies = "127.0.0.1"
    settings.allowed_hosts = "localhost"
    
    configure_middleware(app, settings)
    # Verifies it registers without throwing exception


@pytest.mark.asyncio
async def test_spicedb_channel_lifecycle(monkeypatch):
    from app.core import spicedb
    from app.core.config import settings
    import grpc

    old_endpoint = settings.spicedb_endpoint
    old_channel = spicedb._global_channel

    try:
        spicedb._global_channel = None

        # 1. Test insecure channel creation
        monkeypatch.setenv("SPICEDB_INSECURE", "true")
        settings.spicedb_endpoint = "http://localhost:50051"
        mock_insecure = MagicMock()
        mock_insecure.close = AsyncMock()

        with patch("grpc.aio.insecure_channel", return_value=mock_insecure) as mock_insecure_call:
            generator = spicedb.get_async_spicedb_channel()
            chan = await anext(generator)
            assert chan is mock_insecure
            mock_insecure_call.assert_called_once()

            await spicedb.close_global_spicedb_channel()
            mock_insecure.close.assert_called_once()
            assert spicedb._global_channel is None

        # 2. Test secure channel creation
        monkeypatch.setenv("SPICEDB_INSECURE", "false")
        settings.spicedb_endpoint = "https://localhost:50051"
        mock_secure = MagicMock()
        mock_secure.close = AsyncMock()

        with (
            patch("grpc.aio.secure_channel", return_value=mock_secure) as mock_secure_call,
            patch("grpcutil.bearer_token_credentials", return_value=MagicMock())
        ):
            generator = spicedb.get_async_spicedb_channel()
            chan = await anext(generator)
            assert chan is mock_secure
            mock_secure_call.assert_called_once()

            await spicedb.close_global_spicedb_channel()
            mock_secure.close.assert_called_once()
            assert spicedb._global_channel is None

    finally:
        settings.spicedb_endpoint = old_endpoint
        spicedb._global_channel = old_channel

