"""Fork safety of the Argon2 executor and its per-loop semaphores."""

from __future__ import annotations

import asyncio
import os
import signal
import time
import traceback
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest

from app.auth import security

_PASSWORD = "Fork-Safe-Passphrase-2026!"  # pragma: allowlist secret


@pytest.fixture
def restore_auth_executor() -> Iterator[None]:
    original = security._auth_executor
    original_hibp_client = security._hibp_client
    original_key_lock = security._public_key_cache_lock
    yield
    replacement = security._auth_executor
    security._auth_executor = original
    security._hibp_client = original_hibp_client
    security._public_key_cache_lock = original_key_lock
    security._get_argon2_semaphore_for_loop.cache_clear()
    security._get_hibp_lock_for_loop.cache_clear()
    if replacement is not original:
        replacement.shutdown(wait=True)


@pytest.mark.usefixtures("restore_auth_executor")
def test_fork_reset_replaces_the_executor_and_loop_semaphores() -> None:
    inherited = security._auth_executor
    inherited_semaphore = security._get_argon2_semaphore_for_loop(424242)
    inherited_hibp_lock = security._get_hibp_lock_for_loop(424242)
    inherited_key_lock = security._public_key_cache_lock
    security._hibp_client = object()  # type: ignore[assignment]

    security._reset_auth_state_after_fork()

    replacement = security._auth_executor
    assert replacement is not inherited
    assert replacement._max_workers == security._AUTH_EXECUTOR_WORKERS
    assert replacement._thread_name_prefix == "auth_worker"
    assert security._get_argon2_semaphore_for_loop(424242) is not inherited_semaphore
    assert security._get_hibp_lock_for_loop(424242) is not inherited_hibp_lock
    assert security._hibp_client is None
    assert security._public_key_cache_lock is not inherited_key_lock
    assert not security._public_key_cache_lock.locked()


def test_fork_reset_is_registered_as_the_child_hook() -> None:
    calls: list[dict[str, Callable[[], None]]] = []
    fake_os = SimpleNamespace(register_at_fork=lambda **hooks: calls.append(hooks))

    security._register_fork_reset(fake_os)  # type: ignore[arg-type]

    assert calls == [{"after_in_child": security._reset_auth_state_after_fork}]


def test_fork_reset_registration_is_skipped_without_fork_hooks() -> None:
    platform_without_hooks = SimpleNamespace()

    security._register_fork_reset(platform_without_hooks)  # type: ignore[arg-type]

    assert vars(platform_without_hooks) == {}


def _wait_for_child(pid: int, timeout_s: float) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        finished, status = os.waitpid(pid, os.WNOHANG)
        if finished:
            return os.waitstatus_to_exitcode(status)
        time.sleep(0.05)  # Bound by the timeout_s deadline checked above.
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    pytest.fail(f"forked child {pid} did not finish within {timeout_s}s")


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded, use of fork:DeprecationWarning"
)
def test_forked_child_can_verify_after_the_parent_warmed_the_pool() -> None:
    """A preloaded app server forks after the pool already has idle workers."""
    hashed = asyncio.run(security.get_password_hash(_PASSWORD, validate_policy=False))

    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child reports only through its exit code
        try:
            verified = asyncio.run(
                asyncio.wait_for(security.verify_password(_PASSWORD, hashed), 10)
            )
            os._exit(0 if verified else 2)
        except TimeoutError:
            os._exit(3)
        except BaseException:
            traceback.print_exc()
            os._exit(4)

    exit_code = _wait_for_child(pid, timeout_s=30)
    assert exit_code == 0, {
        2: "child verification returned False",
        3: "child verification timed out on the inherited executor",
        4: "child verification raised",
    }.get(exit_code, f"unexpected child exit code {exit_code}")
    assert asyncio.run(security.verify_password(_PASSWORD, hashed)) is True
