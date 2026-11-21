"""Admission, cancellation, and lifecycle contracts for image transforms."""

import asyncio
import gc
import hashlib
import importlib.util
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.deps.cache
from app.core.config.storage import StorageSettings
from app.services import image_proxy
from app.utils.images import ImagePixelLimitError


def _cache_key(path: str) -> str:
    digest = hashlib.sha256(f"{path}:100:webp".encode()).hexdigest()
    return f"image_proxy:{digest}"


class _ProxyHarness:
    def __init__(self, limit: int) -> None:
        self.loop = asyncio.get_running_loop()
        self.runtime = image_proxy._ImageTransformRuntime(limit)
        self.seen: asyncio.Queue[str] = asyncio.Queue()
        self.reads_seen: asyncio.Queue[str] = asyncio.Queue()
        self.started: asyncio.Queue[str] = asyncio.Queue()
        self.values: dict[str, bytes] = {}
        self.reads: list[str] = []
        self.blocked: set[str] = set()
        self.read_blocks: set[str] = set()
        self.read_errors: set[str] = set()
        self.errors: dict[str, Exception] = {}
        self.release = threading.Event()
        self.release_reads = asyncio.Event()
        self.tasks: list[asyncio.Task[tuple[bytes, str]]] = []

    async def get(self, key: str) -> bytes | None:
        self.loop.call_soon_threadsafe(self.seen.put_nowait, key)
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ex: int) -> None:
        self.values[key] = value

    async def exists(self, path: str) -> bool:
        return True

    async def read_file(self, path: str) -> bytes:
        self.reads.append(path)
        self.loop.call_soon_threadsafe(self.reads_seen.put_nowait, path)
        if path in self.read_blocks:
            await self.release_reads.wait()
        if path in self.read_errors:
            raise OSError("synthetic storage failure")
        return path.encode()

    def process(self, data: bytes, *_args: object) -> tuple[bytes, str]:
        path = data.decode()
        self.loop.call_soon_threadsafe(self.started.put_nowait, path)
        if path in self.blocked and not self.release.wait(timeout=15):
            raise TimeoutError("test encoder was not released")
        if path in self.errors:
            raise self.errors[path]
        return data, "image/webp"

    def request(self, path: str, *, other_loop: bool = False):
        operation = image_proxy.get_transformed_image(
            self, path, width=100, format_preference="webp"
        )
        if other_loop:
            operation = asyncio.to_thread(asyncio.run, operation)
        task = asyncio.create_task(operation)
        self.tasks.append(task)
        return task

    async def saw_cache(self, path: str) -> None:
        assert await asyncio.wait_for(self.seen.get(), timeout=5) == _cache_key(path)

    async def saw_read(self, path: str) -> None:
        assert await asyncio.wait_for(self.reads_seen.get(), timeout=5) == path

    async def saw_encoder(self, path: str) -> None:
        assert await asyncio.wait_for(self.started.get(), timeout=5) == path


@pytest.fixture
async def make_proxy(monkeypatch: pytest.MonkeyPatch):
    harnesses: list[_ProxyHarness] = []

    def make(limit: int = 1) -> _ProxyHarness:
        harness = _ProxyHarness(limit)
        harnesses.append(harness)

        async def get_cache_client():
            return harness

        monkeypatch.setattr(app.deps.cache, "get_cache_client", get_cache_client)
        monkeypatch.setattr(image_proxy, "_process_image", harness.process)
        monkeypatch.setattr(image_proxy, "_image_transform_runtime", harness.runtime)
        monkeypatch.setattr(
            image_proxy,
            "settings",
            SimpleNamespace(
                image_max_pixels=100,
                storage=SimpleNamespace(image_proxy_max_concurrency=limit),
            ),
        )
        return harness

    yield make
    for harness in harnesses:
        harness.release.set()
        harness.release_reads.set()
        await asyncio.wait_for(
            asyncio.gather(*harness.tasks, return_exceptions=True), timeout=5
        )
        harness.runtime.executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_limit_is_enforced_before_read_and_during_encoding(make_proxy) -> None:
    proxy = make_proxy(2)
    proxy.blocked.update({"/first.png", "/second.png"})
    for path in ("/first.png", "/second.png"):
        proxy.request(path)
        await proxy.saw_cache(path)
    assert {
        await asyncio.wait_for(proxy.started.get(), timeout=5) for _ in range(2)
    } == {"/first.png", "/second.png"}

    proxy.request("/third.png")
    await proxy.saw_cache("/third.png")
    assert set(proxy.reads) == {"/first.png", "/second.png"}

    proxy.release.set()
    assert await asyncio.wait_for(asyncio.gather(*proxy.tasks), timeout=5) == [
        (b"/first.png", "image/webp"),
        (b"/second.png", "image/webp"),
        (b"/third.png", "image/webp"),
    ]


@pytest.mark.asyncio
async def test_cache_hit_and_original_bypass_busy_encoder(make_proxy) -> None:
    proxy = make_proxy()
    proxy.blocked.add("/first.png")
    proxy.request("/first.png")
    await proxy.saw_encoder("/first.png")
    proxy.values[_cache_key("/cached.png")] = image_proxy._cache_encode(
        b"cached", "image/webp"
    )

    cached = proxy.request("/cached.png")
    assert await asyncio.wait_for(cached, timeout=5) == (b"cached", "image/webp")
    assert await asyncio.wait_for(
        image_proxy.get_transformed_image(proxy, "/original.png"), timeout=5
    ) == (b"/original.png", "image/png")
    assert proxy.reads == ["/first.png", "/original.png"]


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_read_or_free_live_encoder(make_proxy) -> None:
    proxy = make_proxy()
    proxy.blocked.add("/first.png")
    proxy.request("/first.png")
    await proxy.saw_encoder("/first.png")
    # Consume the first cache event before observing the queued requests.
    await proxy.saw_cache("/first.png")

    waiting = proxy.request("/cancelled.png")
    await proxy.saw_cache("/cancelled.png")
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    next_request = proxy.request("/next.png")
    await proxy.saw_cache("/next.png")
    assert proxy.reads == ["/first.png"]
    proxy.release.set()
    assert await asyncio.wait_for(next_request, timeout=5) == (
        b"/next.png",
        "image/webp",
    )
    assert proxy.reads == ["/first.png", "/next.png"]


@pytest.mark.asyncio
async def test_cancelled_granted_waiter_returns_slot(monkeypatch, make_proxy) -> None:
    proxy = make_proxy()
    proxy.blocked.add("/first.png")
    proxy.request("/first.png")
    await proxy.saw_encoder("/first.png")
    await proxy.saw_cache("/first.png")
    slots = proxy.runtime.slots_for_running_loop()
    release_slot = slots.release

    waiting = proxy.request("/cancelled.png")
    await proxy.saw_cache("/cancelled.png")
    next_request = proxy.request("/next.png")
    await proxy.saw_cache("/next.png")
    cancelled = False

    def release_and_cancel() -> None:
        nonlocal cancelled
        release_slot()
        if not cancelled:
            cancelled = True
            waiting.cancel()

    # Cancel in the same callback that grants the slot, before the waiter runs.
    monkeypatch.setattr(slots, "release", release_and_cancel)
    proxy.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiting, timeout=5)
    assert await asyncio.wait_for(next_request, timeout=5) == (
        b"/next.png",
        "image/webp",
    )
    assert proxy.reads == ["/first.png", "/next.png"]


@pytest.mark.parametrize("worker_fails", [False, True])
@pytest.mark.asyncio
async def test_cancelled_running_encoder_keeps_slot_until_finished(
    make_proxy, worker_fails: bool
) -> None:
    proxy = make_proxy()
    proxy.blocked.add("/first.png")
    if worker_fails:
        proxy.errors["/first.png"] = RuntimeError("synthetic encoder failure")
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    errors: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    try:
        first = proxy.request("/first.png")
        await proxy.saw_encoder("/first.png")
        await proxy.saw_cache("/first.png")
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        next_request = proxy.request("/next.png")
        await proxy.saw_cache("/next.png")
        assert proxy.reads == ["/first.png"]
        proxy.release.set()
        assert await asyncio.wait_for(next_request, timeout=5) == (
            b"/next.png",
            "image/webp",
        )
        gc.collect()
        await asyncio.sleep(0)
        assert not [
            error
            for error in errors
            if "never retrieved" in str(error.get("message"))
            and "synthetic encoder failure" in str(error.get("exception"))
        ]
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.parametrize(
    "failure", ["read", "submit", "fallback", "pixel", "unexpected"]
)
@pytest.mark.asyncio
async def test_failure_releases_slot_for_next_request(
    monkeypatch, make_proxy, failure: str
) -> None:
    proxy = make_proxy()
    if failure == "read":
        proxy.read_errors.add("/broken.png")
    elif failure == "submit":
        submit = proxy.runtime.executor.submit
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic submit failure")
            return submit(*args, **kwargs)

        monkeypatch.setattr(proxy.runtime.executor, "submit", fail_once)
    else:
        proxy.errors["/broken.png"] = {
            "fallback": OSError("synthetic encoder failure"),
            "pixel": ImagePixelLimitError(11, 11, 100),
            "unexpected": RuntimeError("synthetic encoder failure"),
        }[failure]

    broken = proxy.request("/broken.png")
    if failure == "fallback":
        assert await asyncio.wait_for(broken, timeout=5) == (
            b"/broken.png",
            "image/png",
        )
    else:
        error = {
            "read": ValueError,
            "submit": RuntimeError,
            "pixel": ImagePixelLimitError,
            "unexpected": RuntimeError,
        }[failure]
        with pytest.raises(error):
            await asyncio.wait_for(broken, timeout=5)

    next_request = proxy.request("/next.png")
    assert await asyncio.wait_for(next_request, timeout=5) == (
        b"/next.png",
        "image/webp",
    )


@pytest.mark.asyncio
async def test_cancellation_during_read_releases_slot(make_proxy) -> None:
    proxy = make_proxy()
    proxy.read_blocks.add("/cancelled.png")
    cancelled = proxy.request("/cancelled.png")
    await proxy.saw_read("/cancelled.png")
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert await asyncio.wait_for(proxy.request("/next.png"), timeout=5) == (
        b"/next.png",
        "image/webp",
    )


@pytest.mark.asyncio
async def test_cancellation_of_queued_encoder_prevents_execution(make_proxy) -> None:
    proxy = make_proxy()
    executor_busy = asyncio.Event()

    def occupy_executor() -> None:
        proxy.loop.call_soon_threadsafe(executor_busy.set)
        if not proxy.release.wait(timeout=15):
            raise TimeoutError("test executor was not released")

    blocker = proxy.runtime.executor.submit(occupy_executor)
    await asyncio.wait_for(executor_busy.wait(), timeout=5)
    cancelled = proxy.request("/cancelled.png")
    await proxy.saw_read("/cancelled.png")
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    next_request = proxy.request("/next.png")
    await proxy.saw_read("/next.png")
    proxy.release.set()
    assert await asyncio.wait_for(next_request, timeout=5) == (
        b"/next.png",
        "image/webp",
    )
    await asyncio.wait_for(asyncio.wrap_future(blocker), timeout=5)
    await proxy.saw_encoder("/next.png")
    assert proxy.started.empty()


@pytest.mark.asyncio
async def test_two_loops_share_configured_encoder_capacity(
    monkeypatch, make_proxy
) -> None:
    proxy = make_proxy()
    proxy.blocked.add("/first.png")
    submitted = asyncio.Event()
    submit = proxy.runtime.executor.submit
    count = 0

    def track_submit(*args, **kwargs):
        nonlocal count
        future = submit(*args, **kwargs)
        count += 1
        if count == 2:
            proxy.loop.call_soon_threadsafe(submitted.set)
        return future

    monkeypatch.setattr(proxy.runtime.executor, "submit", track_submit)
    first = proxy.request("/first.png", other_loop=True)
    await proxy.saw_encoder("/first.png")
    second = proxy.request("/second.png")
    await asyncio.wait_for(submitted.wait(), timeout=5)
    assert proxy.runtime.executor._max_workers == 1
    assert proxy.started.empty()

    proxy.release.set()
    assert await asyncio.wait_for(first, timeout=5) == (b"/first.png", "image/webp")
    assert await asyncio.wait_for(second, timeout=5) == (b"/second.png", "image/webp")
    await proxy.saw_encoder("/second.png")


@pytest.mark.parametrize("bad_value", [0, 9])
def test_concurrency_setting_has_finite_bounds(monkeypatch, bad_value: int) -> None:
    monkeypatch.delenv("IMAGE_PROXY_MAX_CONCURRENCY", raising=False)
    assert (
        StorageSettings(_allow_missing=True, _env_file=None).image_proxy_max_concurrency
        == 1
    )
    assert (
        StorageSettings(
            _allow_missing=True, image_proxy_max_concurrency=8
        ).image_proxy_max_concurrency
        == 8
    )
    with pytest.raises(ValidationError):
        StorageSettings(_allow_missing=True, image_proxy_max_concurrency=bad_value)


@pytest.mark.asyncio
async def test_fork_reset_recreates_executor_and_slots(monkeypatch, make_proxy) -> None:
    proxy = make_proxy()
    old_slots = proxy.runtime.slots_for_running_loop()
    monkeypatch.setattr(image_proxy.settings.storage, "image_proxy_max_concurrency", 2)
    image_proxy._reset_image_transform_capacity_after_fork()
    fresh = image_proxy._image_transform_runtime
    try:
        assert fresh is not proxy.runtime
        assert fresh.executor._max_workers == 2
        assert fresh.slots_for_running_loop() is not old_slots
    finally:
        fresh.executor.shutdown(wait=True)


@pytest.mark.parametrize("supported", [False, True])
def test_fork_hook_registration_on_supported_and_unsupported_platforms(
    monkeypatch: pytest.MonkeyPatch, supported: bool
) -> None:
    calls: list[dict[str, Callable[[], None]]] = []
    if supported:
        monkeypatch.setattr(
            os, "register_at_fork", lambda **hooks: calls.append(hooks), raising=False
        )
    else:
        monkeypatch.delattr(os, "register_at_fork", raising=False)
    name = "app.services.image_proxy_fork_test"
    spec = importlib.util.spec_from_file_location(name, image_proxy.__file__)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    try:
        spec.loader.exec_module(loaded)
        expected = [
            {"after_in_child": loaded._reset_image_transform_capacity_after_fork}
        ]
        assert calls == (expected if supported else [])
    finally:
        loaded._image_transform_runtime.executor.shutdown(wait=True)


def test_release_after_event_loop_closed_is_safe() -> None:
    loop = asyncio.new_event_loop()
    loop.close()
    slots = asyncio.Semaphore(0)
    completed = Future()
    completed.set_result((b"encoded", "image/webp"))
    image_proxy._release_image_slot(loop, slots, completed)
    assert slots.locked()
