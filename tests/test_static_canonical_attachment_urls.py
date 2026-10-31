"""Storage identity contracts; canonical chat URLs do not make files public."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.config.storage import StorageSettings
from app.services.storage import StaticFSStorage, get_storage_backend
from app.utils import files

_USERINFO_ORIGIN = f"https://{':'.join(('reader', 'fixture'))}@media.example.test"


def _configuration(tmp_path: Path, **overrides: str) -> StorageSettings:
    return StorageSettings(
        _env_file=None,
        static_dir=str(tmp_path),
        storage_backend="static",
        **overrides,
    )


@pytest.mark.asyncio
async def test_default_factory_keeps_public_urls_relative_and_private_identity_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORAGE_STATIC_ORIGIN", raising=False)
    monkeypatch.delenv("storage_static_origin", raising=False)
    configured = _configuration(tmp_path, storage_static_base_url="/static")
    backend = get_storage_backend(configured)
    assert isinstance(backend, StaticFSStorage)

    public_url = await backend.save_file("avatars/avatar.txt", b"avatar")

    assert public_url == "/static/avatars/avatar.txt"
    assert backend.canonical_file_url("chat_uploads/note.txt") == (
        "http://localhost:8000/static/chat_uploads/note.txt"
    )
    assert not (tmp_path / "chat_uploads").exists()


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "/static",
        "//media.example.test",
        "ftp://media.example.test",
        "https://reader@media.example.test",
        _USERINFO_ORIGIN,
        "https://media.example.test/prefix",
        "https://media.example.test?",
        "https://media.example.test#",
        "https://media.example.test:",
        "https://media.example.test:0",
        "https://media.example.test:65536",
        "https://media.example.test:invalid",
        r"https://media.example.test\path",
        " https://media.example.test",
        "https://media.example.test\n",
    ],
)
def test_static_origin_rejects_ambiguous_authorities(
    tmp_path: Path, origin: str
) -> None:
    with pytest.raises(ValueError):
        _configuration(
            tmp_path,
            storage_static_base_url="/static",
            storage_static_origin=origin,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "origin", "public_url", "canonical_url"),
    [
        (
            "/static",
            "https://media.example.test",
            "/static/chat_uploads/note.txt",
            "https://media.example.test/static/chat_uploads/note.txt",
        ),
        (
            "/media",
            "http://127.0.0.1:8123",
            "/media/chat_uploads/note.txt",
            "http://127.0.0.1:8123/media/chat_uploads/note.txt",
        ),
        (
            "/static",
            "http://[::1]:8123",
            "/static/chat_uploads/note.txt",
            "http://[::1]:8123/static/chat_uploads/note.txt",
        ),
        (
            "https://objects.example.test/uploads",
            "https://media.example.test",
            "https://objects.example.test/uploads/chat_uploads/note.txt",
            "https://objects.example.test/uploads/chat_uploads/note.txt",
        ),
    ],
)
async def test_factory_canonical_alias_reads_and_deletes_the_same_local_object(
    tmp_path: Path,
    base_url: str,
    origin: str,
    public_url: str,
    canonical_url: str,
) -> None:
    backend = get_storage_backend(
        _configuration(
            tmp_path,
            storage_static_base_url=base_url,
            storage_static_origin=origin,
        )
    )
    assert isinstance(backend, StaticFSStorage)

    assert await backend.save_file("chat_uploads/note.txt", b"private") == public_url
    assert backend.canonical_file_url("chat_uploads/note.txt") == canonical_url
    assert await backend.exists(canonical_url)
    assert await backend.read_file(canonical_url, max_bytes=7) == b"private"
    assert await backend.read_file(public_url, max_bytes=7) == b"private"

    await backend.delete_file(canonical_url)

    assert not (tmp_path / "chat_uploads" / "note.txt").exists()
    assert not await backend.exists(public_url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "public_url"),
    [
        ("avatars/avatar.txt", "/static/avatars/avatar.txt"),
        ("/avatars/rooted.txt", "/static/avatars/rooted.txt"),
        (
            "quarantine/literal%3F?#;.bin",
            "/static/quarantine/literal%3F?#;.bin",
        ),
    ],
)
async def test_canonical_identity_does_not_reinterpret_existing_literal_keys(
    tmp_path: Path, key: str, public_url: str
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")

    assert await backend.save_file(key, b"literal") == public_url
    assert await backend.exists(key)
    assert await backend.read_file(key) == b"literal"

    await backend.delete_file(key)

    assert not await backend.exists(key)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "foreign",
    [
        "https://foreign.example.test/static/chat_uploads/note.txt",
        "https://files.example.test/static-other/chat_uploads/note.txt",
        "//files.example.test/static/chat_uploads/note.txt",
    ],
)
async def test_foreign_url_shapes_never_fall_back_to_local_filesystem_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, foreign: str
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="https://files.example.test/static")
    target = tmp_path / "chat_uploads" / "note.txt"
    target.parent.mkdir()
    target.write_bytes(b"must remain")

    def reject_filesystem_access(_relative_path: Path) -> Path:
        raise AssertionError("Foreign URL reached filesystem resolution")

    monkeypatch.setattr(backend, "_resolve_validated_path", reject_filesystem_access)

    assert not await backend.exists(foreign)
    with pytest.raises(FileNotFoundError):
        await backend.read_file(foreign)
    await backend.delete_file(foreign)
    assert target.read_bytes() == b"must remain"


@pytest.mark.asyncio
async def test_canonical_attachment_preflight_rejects_key_before_directory_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = StaticFSStorage(tmp_path / "storage", base_url="/static")
    prepare = AsyncMock(
        side_effect=AssertionError("Directory prepared before validation")
    )
    save = AsyncMock(side_effect=AssertionError("File written before validation"))
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "_prepare_local_storage", prepare)
    monkeypatch.setattr(backend, "save_file", save)
    monkeypatch.setattr(files, "_gen_name", lambda _prefix, _ext: "note.txt")
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "text/plain")
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    upload = UploadFile(
        filename="note.txt",
        file=io.BytesIO(b"private"),
        headers=Headers({"content-type": "text/plain"}),
    )

    try:
        with pytest.raises(ValueError):
            await files.save_attachment(
                upload,
                "../outside",
                "chat",
                allowed_mime_types={"text/plain"},
                allowed_extensions={"txt"},
                max_size_bytes=1024,
                canonical_static_url=True,
            )
    finally:
        await upload.close()

    prepare.assert_not_awaited()
    save.assert_not_awaited()
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8000",
        "https://media.example.test",
        "https://media.example.test:443",
        "http://127.0.0.1:8123",
        "http://[::1]:8123",
        "https://MEDIA.example.test:8443",
    ],
)
def test_private_origin_validation_preserves_the_configured_identity(
    origin: str,
) -> None:
    from app.core.storage_urls import validate_static_storage_origin

    assert validate_static_storage_origin(origin) == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://[::1]garbage",
        "http://[::1]:80garbage",
        "http://media%2eexample.test",
        "http://[fe80::1%25eth0]",
        "http://[::1",
        "http://media|example.test",
        "http://999.999.999.999",
        "http://media.example.test\u00a0",
        "http://media.example.test\x7f",
        "http://",
        "HTTP://media.example.test",
    ],
)
def test_private_origin_rejects_malformed_authorities_without_parser_repair(
    tmp_path: Path, origin: str
) -> None:
    from app.core.storage_urls import validate_static_storage_origin

    with pytest.raises(ValueError):
        validate_static_storage_origin(origin)
    with pytest.raises(ValueError):
        _configuration(tmp_path, storage_static_origin=origin)
    with pytest.raises(ValueError):
        StaticFSStorage(tmp_path, static_origin=origin)


def test_direct_storage_constructor_rejects_a_non_string_origin(tmp_path: Path) -> None:
    from typing import cast

    with pytest.raises(ValueError):
        StaticFSStorage(tmp_path, static_origin=cast(str, None))


@pytest.mark.asyncio
async def test_origin_change_refreshes_the_backend_without_changing_public_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files.settings, "storage_backend", "static")
    monkeypatch.setattr(files.settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(files.settings, "storage_static_base_url", "/static")
    monkeypatch.setattr(
        files.settings, "storage_static_origin", "https://first.example.test"
    )
    first = get_storage_backend(files.settings.storage)
    assert isinstance(first, StaticFSStorage)
    monkeypatch.setattr(files, "storage_backend", first)
    monkeypatch.setattr(files, "_default_storage_backend", first)
    monkeypatch.setattr(
        files, "_storage_backend_snapshot", files._storage_backend_signature()
    )

    assert files._get_storage_backend() is first
    assert first.canonical_file_url("chat_uploads/note.txt") == (
        "https://first.example.test/static/chat_uploads/note.txt"
    )
    assert await first.save_file("avatars/avatar.txt", b"public") == (
        "/static/avatars/avatar.txt"
    )

    monkeypatch.setattr(
        files.settings, "storage_static_origin", "https://second.example.test"
    )
    second = files._get_storage_backend()

    assert isinstance(second, StaticFSStorage)
    assert second is not first
    assert second.canonical_file_url("chat_uploads/note.txt") == (
        "https://second.example.test/static/chat_uploads/note.txt"
    )
    assert await second.read_file("/static/avatars/avatar.txt") == b"public"
    assert await second.save_file("avatars/new.txt", b"new") == (
        "/static/avatars/new.txt"
    )
    assert files._get_storage_backend() is second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", ["report:final.txt", "/report:final.txt", "quarantine/a:b"]
)
async def test_opaque_colons_in_literal_keys_are_not_treated_as_external_urls(
    tmp_path: Path, key: str
) -> None:
    backend = StaticFSStorage(tmp_path)
    await backend.save_file(key, b"literal colon")

    assert await backend.exists(key)
    assert await backend.read_file(key) == b"literal colon"

    await backend.delete_file(key)

    assert not await backend.exists(key)


@pytest.mark.asyncio
async def test_absolute_base_preserves_public_case_and_canonicalizes_only_scheme(
    tmp_path: Path,
) -> None:
    backend = get_storage_backend(
        _configuration(
            tmp_path,
            storage_static_base_url="HTTPS://Files.example.test:443/Uploads",
            storage_static_origin="https://ignored.example.test",
        )
    )

    assert isinstance(backend, StaticFSStorage)

    public = await backend.save_file("chat_uploads/note.txt", b"private")
    assert public == "HTTPS://Files.example.test:443/Uploads/chat_uploads/note.txt"
    canonical = backend.canonical_file_url("chat_uploads/note.txt")
    assert canonical == "https://Files.example.test:443/Uploads/chat_uploads/note.txt"
    assert await backend.read_file(public) == b"private"
    assert await backend.read_file(canonical) == b"private"

    await backend.delete_file(canonical)

    assert not await backend.exists(public)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "filename"),
    [
        ("/static", "note?.txt"),
        ("/static", "note#.txt"),
        ("/static", "note%2Ftail.txt"),
        ("/static", "note;params.txt"),
        ("https://files.example.test/uploads?download", "note.txt"),
        ("https://files.example.test/uploads#", "note.txt"),
        ("https://reader@files.example.test/uploads", "note.txt"),
        ("https://[::1]garbage/uploads", "note.txt"),
        ("//files.example.test/uploads", "note.txt"),
        ("http:/files.example.test/uploads", "note.txt"),
        ("ftp://files.example.test/uploads", "note.txt"),
    ],
)
async def test_private_identity_rejects_ambiguous_keys_and_bases_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    filename: str,
) -> None:
    backend = StaticFSStorage(tmp_path / "storage", base_url=base_url)
    prepare = AsyncMock(side_effect=AssertionError("Prepared before URL validation"))
    save = AsyncMock(side_effect=AssertionError("Written before URL validation"))
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "_prepare_local_storage", prepare)
    monkeypatch.setattr(backend, "save_file", save)
    monkeypatch.setattr(files, "_gen_name", lambda _prefix, _ext: filename)
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "text/plain")
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    upload = UploadFile(
        filename="note.txt",
        file=io.BytesIO(b"private"),
        headers=Headers({"content-type": "text/plain"}),
    )

    try:
        with pytest.raises(ValueError):
            await files.save_attachment(
                upload,
                "chat_uploads",
                "chat",
                allowed_mime_types={"text/plain"},
                allowed_extensions={"txt"},
                max_size_bytes=1024,
                canonical_static_url=True,
            )
    finally:
        await upload.close()

    prepare.assert_not_awaited()
    save.assert_not_awaited()
    assert not (tmp_path / "storage").exists()
