"""Storage identity contracts; canonical chat URLs do not make files public."""

from __future__ import annotations

import asyncio
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.config.storage import StorageSettings
from app.services.storage import S3Storage, StaticFSStorage, get_storage_backend
from app.utils import files

_USERINFO_ORIGIN = f"https://{':'.join(('reader', 'fixture'))}@media.example.test"


async def _wait_for_cancellable_writes_to_drain(backend: StaticFSStorage) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 3
    while backend._pending_cancellable_writes and loop.time() < deadline:
        await asyncio.sleep(0.005)
    assert not backend._pending_cancellable_writes


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


@pytest.mark.asyncio
async def test_cancellable_static_write_success_and_collision_preserve_ownership(
    tmp_path: Path,
) -> None:
    backend = StaticFSStorage(tmp_path)
    saved_url = await backend.save_file_cancellable("chat_uploads/new.pdf", b"new")
    assert saved_url == "/static/chat_uploads/new.pdf"
    assert (tmp_path / "chat_uploads" / "new.pdf").read_bytes() == b"new"
    await _wait_for_cancellable_writes_to_drain(backend)

    existing = tmp_path / "chat_uploads" / "existing.pdf"
    existing.write_bytes(b"keep existing bytes")
    with pytest.raises(FileExistsError):
        await backend.save_file_cancellable("chat_uploads/existing.pdf", b"replace")
    await _wait_for_cancellable_writes_to_drain(backend)
    assert existing.read_bytes() == b"keep existing bytes"

    await backend.save_file("ordinary/overwrite.txt", b"first")
    await backend.save_file("ordinary/overwrite.txt", b"second")
    assert (tmp_path / "ordinary" / "overwrite.txt").read_bytes() == b"second"

    root_url_backend = StaticFSStorage(tmp_path / "root-url", base_url="")
    root_url = await root_url_backend.save_file_cancellable(
        "chat_uploads/root.pdf", b"root url"
    )
    assert root_url == "/chat_uploads/root.pdf"
    assert (
        tmp_path / "root-url" / "chat_uploads" / "root.pdf"
    ).read_bytes() == b"root url"
    await _wait_for_cancellable_writes_to_drain(root_url_backend)


@pytest.mark.asyncio
async def test_cancellable_static_write_aborts_when_cancelled_before_worker_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = StaticFSStorage(tmp_path)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="static-cancel-test"
    )
    original_run_in_executor = loop.run_in_executor

    def use_private_executor(executor_arg, function, *args):
        if executor_arg is None:
            executor_arg = executor
        return original_run_in_executor(executor_arg, function, *args)

    monkeypatch.setattr(loop, "run_in_executor", use_private_executor)
    release_blocker = threading.Event()
    blocker_started = threading.Event()
    target = tmp_path / "chat_uploads" / "queued.pdf"

    def occupy_worker() -> None:
        blocker_started.set()
        if not release_blocker.wait(timeout=5):
            raise TimeoutError("test did not release the executor blocker")

    blocker = loop.run_in_executor(executor, occupy_worker)
    deadline = loop.time() + 3
    while not blocker_started.is_set() and loop.time() < deadline:
        await asyncio.sleep(0.005)
    assert blocker_started.is_set()

    save_task = asyncio.create_task(
        backend.save_file_cancellable("chat_uploads/queued.pdf", b"queued")
    )
    deadline = loop.time() + 3
    while not backend._pending_cancellable_writes and loop.time() < deadline:
        await asyncio.sleep(0.005)
    assert backend._pending_cancellable_writes
    write_future = next(iter(backend._pending_cancellable_writes))

    try:
        save_task.cancel("cancel before executor write starts")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(save_task, timeout=2)
        assert raised.value.args == ("cancel before executor write starts",)
        assert not target.exists()
        release_blocker.set()
        await asyncio.wait_for(blocker, timeout=2)
        await asyncio.wait_for(asyncio.shield(write_future), timeout=2)
        await _wait_for_cancellable_writes_to_drain(backend)
        assert not target.exists()
    finally:
        release_blocker.set()
        if not save_task.done():
            save_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(save_task, timeout=2)
        if not blocker.done():
            await asyncio.wait_for(blocker, timeout=2)
        executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_cancellable_static_write_aborts_after_parent_creation_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = StaticFSStorage(tmp_path)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="static-cancel-test"
    )
    original_run_in_executor = loop.run_in_executor

    def use_private_executor(executor_arg, function, *args):
        if executor_arg is None:
            executor_arg = executor
        return original_run_in_executor(executor_arg, function, *args)

    monkeypatch.setattr(loop, "run_in_executor", use_private_executor)
    parent_created = threading.Event()
    release_worker = threading.Event()
    worker_threads: list[threading.Thread] = []
    target = tmp_path / "chat_uploads" / "parent-created.pdf"
    original_mkdir = Path.mkdir

    def gated_mkdir(path: Path, *args, **kwargs):
        result = original_mkdir(path, *args, **kwargs)
        if path.resolve() == target.parent.resolve():
            worker_threads.append(threading.current_thread())
            parent_created.set()
            if not release_worker.wait(timeout=5):
                raise TimeoutError("test did not release the post-mkdir worker")
        return result

    monkeypatch.setattr(Path, "mkdir", gated_mkdir)
    save_task = asyncio.create_task(
        backend.save_file_cancellable("chat_uploads/parent-created.pdf", b"payload")
    )
    write_future = None

    try:
        deadline = loop.time() + 3
        while not parent_created.is_set() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert parent_created.is_set()
        write_future = next(iter(backend._pending_cancellable_writes))
        save_task.cancel("cancel after parent creation")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(save_task, timeout=2)
        assert raised.value.args == ("cancel after parent creation",)
        assert not target.exists()
        release_worker.set()
        await asyncio.wait_for(asyncio.shield(write_future), timeout=2)
        await _wait_for_cancellable_writes_to_drain(backend)
        assert not target.exists()
    finally:
        release_worker.set()
        if not save_task.done():
            save_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(save_task, timeout=2)
        if write_future is not None and not write_future.done():
            await asyncio.wait_for(asyncio.shield(write_future), timeout=2)
        executor.shutdown(wait=True, cancel_futures=True)
    assert worker_threads and all(not worker.is_alive() for worker in worker_threads)


@pytest.mark.asyncio
async def test_cancellable_static_write_reports_queued_executor_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = StaticFSStorage(tmp_path)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="static-shutdown-test"
    )
    original_run_in_executor = loop.run_in_executor

    def use_private_executor(executor_arg, function, *args):
        if executor_arg is None:
            executor_arg = executor
        return original_run_in_executor(executor_arg, function, *args)

    monkeypatch.setattr(loop, "run_in_executor", use_private_executor)
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    worker_threads: list[threading.Thread] = []
    target = tmp_path / "chat_uploads" / "shutdown.pdf"
    save_task = None
    blocker_future = None
    write_future = None

    def occupy_worker() -> None:
        worker_threads.append(threading.current_thread())
        blocker_started.set()
        if not release_blocker.wait(timeout=5):
            raise TimeoutError("test did not release the executor blocker")

    try:
        blocker_future = loop.run_in_executor(executor, occupy_worker)
        deadline = loop.time() + 3
        while not blocker_started.is_set() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert blocker_started.is_set()

        save_task = asyncio.create_task(
            backend.save_file_cancellable("chat_uploads/shutdown.pdf", b"payload")
        )
        deadline = loop.time() + 3
        while not backend._pending_cancellable_writes and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert backend._pending_cancellable_writes
        write_future = next(iter(backend._pending_cancellable_writes))

        executor.shutdown(wait=False, cancel_futures=True)
        deadline = loop.time() + 3
        while not write_future.done() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert write_future.cancelled()
        release_blocker.set()
        await asyncio.wait_for(blocker_future, timeout=2)
        with pytest.raises(
            RuntimeError,
            match="Static write executor stopped before the upload started",
        ):
            await asyncio.wait_for(save_task, timeout=2)
        await _wait_for_cancellable_writes_to_drain(backend)
        assert not target.exists()
    finally:
        release_blocker.set()
        if save_task is not None and not save_task.done():
            save_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(save_task, timeout=2)
        if blocker_future is not None and not blocker_future.done():
            await asyncio.wait_for(blocker_future, timeout=2)
        if write_future is not None and not write_future.done():
            try:
                await asyncio.wait_for(asyncio.shield(write_future), timeout=2)
            except asyncio.CancelledError:
                pass
        executor.shutdown(wait=True, cancel_futures=True)
    assert worker_threads and all(not worker.is_alive() for worker in worker_threads)


@pytest.mark.asyncio
async def test_cancellable_static_write_error_removes_partial_file_and_preserves_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = StaticFSStorage(tmp_path)
    original_open = Path.open
    target = tmp_path / "chat_uploads" / "partial.pdf"
    primary_error = OSError("private static write failure")

    class FailingWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, exc_type, exc, traceback):
            return self.stream.__exit__(exc_type, exc, traceback)

        def write(self, data: bytes) -> int:
            self.stream.write(data[:4])
            self.stream.flush()
            raise primary_error

    def failing_open(path: Path, mode: str = "r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path.resolve() == target.resolve() and mode == "xb":
            return FailingWriter(stream)
        return stream

    monkeypatch.setattr(Path, "open", failing_open)

    with pytest.raises(OSError) as raised:
        await backend.save_file_cancellable("chat_uploads/partial.pdf", b"payload")

    assert raised.value is primary_error
    await _wait_for_cancellable_writes_to_drain(backend)
    assert not target.exists()


@pytest.mark.asyncio
async def test_noncanonical_static_attachment_keeps_generic_save_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = StaticFSStorage(tmp_path)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "application/pdf")
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "_gen_name", lambda _prefix, _extension: "note.pdf")
    upload = UploadFile(
        filename="note.pdf",
        file=io.BytesIO(b"%PDF-1.7\ngeneric upload\n"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    try:
        result = await files.save_attachment(
            upload,
            "chat_uploads",
            "chat",
            allowed_mime_types={"application/pdf"},
            allowed_extensions={"pdf"},
            max_size_bytes=1024,
            return_meta=True,
        )
    finally:
        await upload.close()

    assert isinstance(result, dict)
    assert result["url"] == "/static/chat_uploads/note.pdf"
    assert (tmp_path / "chat_uploads" / "note.pdf").read_bytes() == (
        b"%PDF-1.7\ngeneric upload\n"
    )
    assert not backend._pending_cancellable_writes


@pytest.mark.asyncio
async def test_chat_canonical_opt_in_routes_s3_through_cancellable_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = S3Storage(
        bucket="uploads",
        base_url="https://media.example.test/uploads",
        client=AsyncMock(),
    )
    saved_url = "https://media.example.test/uploads/chat_uploads/note.txt"
    cancellable = AsyncMock(return_value=saved_url)
    save = AsyncMock(side_effect=AssertionError("Plain save used for chat opt-in"))
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "_prepare_local_storage", AsyncMock())
    monkeypatch.setattr(backend, "save_file_cancellable", cancellable)
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
        url = await files.save_attachment(
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

    assert url == saved_url
    cancellable.assert_awaited_once()
    assert cancellable.await_args.args[0] == "chat_uploads/note.txt"
    save.assert_not_awaited()
