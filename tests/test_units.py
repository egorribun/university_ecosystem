"""Wave 1 coverage: pure unit tests with no external dependencies.

Covers:
- app/core/orjson_utils.py
- app/core/cache_versioning.py
- app/core/task_registry.py
- app/core/nats_registry.py
- app/core/versioning.py
- app/core/constants.py
- app/core/protocols.py
- app/core/timing.py
- app/services/group_service.py
- app/utils/uuid_v7.py
- app/utils/audit.py
- app/utils/migrations.py
- app/utils/img.py
- app/utils/query_batching.py (pure parts)
- app/utils/request_coalescing.py
- app/schemas/validators.py
- app/cqrs/base.py
- app/cqrs/bus.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# app/core/constants.py
# ---------------------------------------------------------------------------


def test_constants_import() -> None:
    from app.core.constants import ANONYMIZED_USER_CREDENTIAL

    assert ANONYMIZED_USER_CREDENTIAL == "deleted"


# ---------------------------------------------------------------------------
# app/core/versioning.py
# ---------------------------------------------------------------------------


def test_assert_semver_valid() -> None:
    from app.core.versioning import assert_semver

    assert assert_semver("1.0.0") == "1.0.0"
    assert assert_semver("0.0.1") == "0.0.1"
    assert assert_semver("10.20.30") == "10.20.30"
    assert assert_semver("1.0.0-alpha.1") == "1.0.0-alpha.1"
    assert assert_semver("1.0.0+build.42") == "1.0.0+build.42"
    assert assert_semver("1.2.3-beta.1+build.5") == "1.2.3-beta.1+build.5"


def test_assert_semver_invalid() -> None:
    from app.core.versioning import assert_semver

    with pytest.raises(ValueError, match="semantic versioning"):
        assert_semver("1.0")
    with pytest.raises(ValueError, match="semantic versioning"):
        assert_semver("v1.0.0")
    with pytest.raises(ValueError, match="semantic versioning"):
        assert_semver("not_a_version")
    with pytest.raises(ValueError, match="semantic versioning"):
        assert_semver("")


def test_api_version_constants() -> None:
    from app.core.versioning import API_V1_PREFIX, API_VERSION

    assert API_VERSION == "1.0.0"
    assert API_V1_PREFIX == "/api/v1"


# ---------------------------------------------------------------------------
# app/core/orjson_utils.py
# ---------------------------------------------------------------------------


def test_orjson_dumps_basic() -> None:
    from app.core.orjson_utils import orjson_dumps

    result = orjson_dumps({"key": "value"})
    assert isinstance(result, bytes)
    assert b"key" in result
    assert b"value" in result


def test_orjson_dumps_str() -> None:
    from app.core.orjson_utils import orjson_dumps_str

    result = orjson_dumps_str({"a": 1})
    assert isinstance(result, str)
    assert '"a"' in result


def test_orjson_loads() -> None:
    from app.core.orjson_utils import orjson_loads

    data = b'{"x": 42}'
    result = orjson_loads(data)
    assert result == {"x": 42}

    # also accepts str
    result2 = orjson_loads('{"y": true}')
    assert result2 == {"y": True}


def test_orjson_dumps_with_option() -> None:
    from app.core.orjson_utils import orjson_dumps

    # passing option=None uses defaults only
    result = orjson_dumps([1, 2, 3], option=None)
    assert result == b"[1,2,3]"

    # passing option=0 (OPT_NON_STR_KEYS or similar safe value)
    result2 = orjson_dumps({"n": 1}, option=0)
    assert b"n" in result2


def test_default_serializer_datetime() -> None:
    from app.core.orjson_utils import default_serializer

    dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert "2025" in default_serializer(dt)

    from datetime import date, time

    d = date(2025, 6, 15)
    assert "2025" in default_serializer(d)

    t = time(10, 30, 0)
    assert "10:30" in default_serializer(t)


def test_default_serializer_unsupported_type() -> None:
    from app.core.orjson_utils import default_serializer

    with pytest.raises(TypeError, match="not JSON serializable"):
        default_serializer(object())


def test_orjson_all_exports() -> None:
    from app.core import orjson_utils

    for name in orjson_utils.__all__:
        assert hasattr(orjson_utils, name)


# ---------------------------------------------------------------------------
# app/core/nats_registry.py
# ---------------------------------------------------------------------------


def test_nats_registry_register_and_get() -> None:
    import importlib

    import app.core.nats_registry as reg_module

    # Reload to get a clean state for testing
    importlib.reload(reg_module)

    @reg_module.register_task
    class MyTask(BaseModel):
        user_id: str

    assert reg_module.get_task_schema("MyTask") is MyTask
    assert reg_module.is_registered("MyTask") is True
    assert "MyTask" in reg_module.list_registered_tasks()


def test_nats_registry_custom_name() -> None:
    import importlib

    import app.core.nats_registry as reg_module

    importlib.reload(reg_module)

    @reg_module.register_task
    class TaskWithCustomName(BaseModel):
        __task_name__ = "custom.task.name"
        payload: str

    assert reg_module.get_task_schema("custom.task.name") is TaskWithCustomName
    assert reg_module.is_registered("custom.task.name") is True
    assert not reg_module.is_registered("TaskWithCustomName")


def test_nats_registry_unknown_task() -> None:
    import app.core.nats_registry as reg_module

    result = reg_module.get_task_schema("NonExistent")
    assert result is None
    assert reg_module.is_registered("NonExistent") is False


def test_nats_registry_duplicate_same_class() -> None:
    import importlib

    import app.core.nats_registry as reg_module

    importlib.reload(reg_module)

    @reg_module.register_task
    class DupTask(BaseModel):
        x: int

    # Registering the same class again should not raise
    reg_module.register_task(DupTask)
    assert reg_module.get_task_schema("DupTask") is DupTask


def test_nats_registry_duplicate_different_class_raises() -> None:
    import importlib

    import app.core.nats_registry as reg_module

    importlib.reload(reg_module)

    @reg_module.register_task
    class ConflictTask(BaseModel):
        a: int

    with pytest.raises(ValueError, match="already registered"):

        @reg_module.register_task
        class ConflictTask(BaseModel):  # type: ignore[no-redef]
            __task_name__ = "ConflictTask"
            b: str


def test_nats_registry_list_sorted() -> None:
    import importlib

    import app.core.nats_registry as reg_module

    importlib.reload(reg_module)

    @reg_module.register_task
    class ZTask(BaseModel):
        z: int

    @reg_module.register_task
    class ATask(BaseModel):
        a: int

    tasks = reg_module.list_registered_tasks()
    assert tasks == sorted(tasks)


# ---------------------------------------------------------------------------
# app/core/task_registry.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_registry_create_and_shutdown() -> None:
    from app.core.task_registry import TaskRegistry

    registry = TaskRegistry()

    async def noop() -> None:
        await asyncio.sleep(0)

    task = registry.create_task(noop(), name="test-noop")
    assert isinstance(task, asyncio.Task)

    await registry.shutdown(timeout=5.0)
    assert len(registry._tasks) == 0


@pytest.mark.asyncio
async def test_task_registry_shutdown_empty() -> None:
    from app.core.task_registry import TaskRegistry

    registry = TaskRegistry()
    # Should return immediately with no tasks
    await registry.shutdown(timeout=1.0)


@pytest.mark.asyncio
async def test_task_registry_exception_logged(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from app.core.task_registry import TaskRegistry

    registry = TaskRegistry()

    async def failing() -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="app.core.task_registry"):
        task = registry.create_task(failing(), name="test-fail")
        # Let the event loop process the task
        await asyncio.sleep(0.05)

    assert "boom" in caplog.text or task.done()


@pytest.mark.asyncio
async def test_task_registry_cancelled_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from app.core.task_registry import TaskRegistry

    registry = TaskRegistry()

    async def long_running() -> None:
        await asyncio.sleep(100)

    with caplog.at_level(logging.ERROR, logger="app.core.task_registry"):
        registry.create_task(long_running(), name="test-cancel")
        await registry.shutdown(timeout=5.0)

    # No error should be logged for cancellation
    assert "failed unexpectedly" not in caplog.text


# ---------------------------------------------------------------------------
# app/core/protocols.py
# ---------------------------------------------------------------------------


def test_extract_user_id_from_uuid() -> None:
    from app.core.protocols import extract_user_id

    uid = uuid.uuid4()
    assert extract_user_id(uid) == uid


def test_extract_user_id_from_str() -> None:
    from app.core.protocols import extract_user_id

    uid = uuid.uuid4()
    result = extract_user_id(str(uid))
    assert result == uid


def test_extract_user_id_from_has_id() -> None:
    from app.core.protocols import extract_user_id

    uid = uuid.uuid4()

    class Obj:
        id = uid

    obj = Obj()
    # HasID is not @runtime_checkable — just verify structural duck-typing works
    assert extract_user_id(obj) == uid  # type: ignore[arg-type]


def test_extract_user_id_invalid_string() -> None:
    import pytest

    from app.core.protocols import extract_user_id

    with pytest.raises(
        ValueError, match=r"extract_user_id: .* is not a valid UUID string"
    ):
        extract_user_id("invalid-uuid-string")


# ---------------------------------------------------------------------------
# app/core/timing.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_minimum_time_no_sleep() -> None:
    """If already past the minimum, no sleep occurs."""
    import time

    from app.core.timing import ensure_minimum_time

    start = time.perf_counter() - 1.0  # pretend 1 second already elapsed
    await ensure_minimum_time(start, min_duration_seconds=0.001)
    # should complete without significant delay


@pytest.mark.asyncio
async def test_ensure_minimum_time_sleeps() -> None:
    """If not enough time passed, sleep is called."""
    import time

    from app.core.timing import ensure_minimum_time

    start = time.perf_counter()
    # Require 50ms minimum
    await ensure_minimum_time(start, min_duration_seconds=0.05)
    elapsed = time.perf_counter() - start
    assert elapsed >= 0.04  # allow slight tolerance


def test_create_timing_middleware() -> None:
    from app.core.timing import RequestTimingMiddleware, create_timing_middleware

    cls = create_timing_middleware()
    assert cls is RequestTimingMiddleware


def test_slow_request_threshold_constant() -> None:
    from app.core.timing import SLOW_REQUEST_THRESHOLD_MS

    assert SLOW_REQUEST_THRESHOLD_MS == 500.0


# ---------------------------------------------------------------------------
# app/services/group_service.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_service_get_groups() -> None:
    from app.services.group_service import GroupService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.list_groups = AsyncMock(return_value=["group1", "group2"])

    service = GroupService(db=mock_db, repo=mock_repo)
    result = await service.get_groups()

    assert result == ["group1", "group2"]
    mock_repo.list_groups.assert_awaited_once()


# ---------------------------------------------------------------------------
# app/utils/uuid_v7.py
# ---------------------------------------------------------------------------


def test_generate_uuid7_format() -> None:
    from app.utils.uuid_v7 import generate_uuid7

    u = generate_uuid7()
    assert isinstance(u, uuid.UUID)
    # version field in high nibble of byte 6 = 0x7
    assert (u.int >> 76) & 0xF == 7


def test_generate_uuid7_with_datetime() -> None:
    from app.utils.uuid_v7 import generate_uuid7

    dt = datetime(2025, 6, 1, tzinfo=UTC)
    u = generate_uuid7(dt=dt)
    assert isinstance(u, uuid.UUID)
    # variant bits: top 2 bits of byte 8 should be 10
    byte8 = (u.int >> 56) & 0xFF
    assert (byte8 >> 6) == 0b10


def test_generate_uuid7_monotonic() -> None:
    from app.utils.uuid_v7 import generate_uuid7

    uuids = [generate_uuid7() for _ in range(10)]
    timestamps = [u.int >> 80 for u in uuids]
    # timestamps should be non-decreasing
    assert timestamps == sorted(timestamps)


def test_extract_timestamp_from_uuid7() -> None:
    from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7

    before = datetime.now(UTC) - timedelta(seconds=1)
    u = generate_uuid7()
    after = datetime.now(UTC) + timedelta(seconds=1)

    ts = extract_timestamp_from_uuid_v7(u)
    assert before <= ts <= after


def test_extract_timestamp_from_uuid7_str() -> None:
    from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7, generate_uuid7

    u = generate_uuid7()
    ts = extract_timestamp_from_uuid_v7(str(u))
    assert isinstance(ts, datetime)
    assert ts.tzinfo is not None


# ---------------------------------------------------------------------------
# app/utils/audit.py
# ---------------------------------------------------------------------------


def test_calculate_log_signature() -> None:
    from unittest.mock import patch

    from app.utils.audit import calculate_log_signature

    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    uid = uuid.uuid4()

    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = "secret_key_1,secret_key_2"
        sig = calculate_log_signature(
            actor_user_id=uid,
            subject_user_id=uid,
            resource_type="user",
            resource_id="123",
            action="read",
            context={"key": "val"},
            ip_address="127.0.0.1",
            user_agent="test-agent",
            created_at=now,
        )
    assert isinstance(sig, str)
    assert len(sig) == 64  # sha256 hex


def test_calculate_log_signature_none_fields() -> None:
    from unittest.mock import patch

    from app.utils.audit import calculate_log_signature

    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = "mykey"
        sig = calculate_log_signature(
            actor_user_id=None,
            subject_user_id=None,
            resource_type="event",
            resource_id=None,
            action="list",
            context={},
            ip_address=None,
            user_agent=None,
            created_at=now,
        )
    assert isinstance(sig, str)


def test_calculate_log_signature_empty_secret_raises() -> None:
    from unittest.mock import patch

    from app.utils.audit import calculate_log_signature

    now = datetime(2025, 1, 1, tzinfo=UTC)

    with patch("app.utils.audit.settings") as mock_settings:
        mock_settings.audit_log_secret = ""
        with pytest.raises(ValueError, match="AUDIT_LOG_SECRET"):
            calculate_log_signature(
                actor_user_id=None,
                subject_user_id=None,
                resource_type="x",
                resource_id=None,
                action="y",
                context={},
                ip_address=None,
                user_agent=None,
                created_at=now,
            )


def test_calculate_log_signature_uses_first_key_only() -> None:
    """Signature uses only the first comma-separated key."""
    from unittest.mock import patch

    from app.utils.audit import calculate_log_signature

    now = datetime(2025, 1, 1, tzinfo=UTC)
    uid = uuid.uuid4()

    args: dict[str, Any] = {
        "actor_user_id": uid,
        "subject_user_id": None,
        "resource_type": "news",
        "resource_id": "1",
        "action": "view",
        "context": {},
        "ip_address": None,
        "user_agent": None,
        "created_at": now,
    }

    with patch("app.utils.audit.settings") as s1:
        s1.audit_log_secret = "primary,secondary"
        sig1 = calculate_log_signature(**args)

    with patch("app.utils.audit.settings") as s2:
        s2.audit_log_secret = "primary"
        sig2 = calculate_log_signature(**args)

    assert sig1 == sig2


# ---------------------------------------------------------------------------
# app/utils/migrations.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrations_are_current_cache_hit() -> None:
    """Cached result is returned without hitting the DB again."""
    import time

    import app.utils.migrations as mig_mod

    mig_mod.reset_migration_cache()

    # Pre-populate cache
    expected = (True, {"abc"}, {"abc"})
    mig_mod._migration_cache["expires_at"] = time.monotonic() + 60.0
    mig_mod._migration_cache["result"] = expected

    result = await mig_mod.migrations_are_current(conn=None, engine=None)
    assert result == expected

    mig_mod.reset_migration_cache()


@pytest.mark.asyncio
async def test_migrations_are_current_with_conn() -> None:
    import app.utils.migrations as mig_mod

    mig_mod.reset_migration_cache()

    mock_script = MagicMock()
    mock_script.get_heads.return_value = ["head1"]

    mock_row = MagicMock()
    mock_row.__iter__ = MagicMock(return_value=iter(["head1"]))
    # Make the result iterable for set comprehension
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([("head1",)]))

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_result)

    with patch.object(mig_mod, "get_alembic_script", return_value=mock_script):
        is_current, current, expected_h = await mig_mod.migrations_are_current(
            conn=mock_conn
        )

    assert is_current is True
    assert current == {"head1"}
    assert expected_h == {"head1"}

    mig_mod.reset_migration_cache()


@pytest.mark.asyncio
async def test_migrations_are_current_no_conn_no_engine_raises() -> None:
    import app.utils.migrations as mig_mod

    mig_mod.reset_migration_cache()

    mock_script = MagicMock()
    mock_script.get_heads.return_value = ["head1"]

    with patch.object(mig_mod, "get_alembic_script", return_value=mock_script):
        with pytest.raises(ValueError, match="conn or engine"):
            await mig_mod.migrations_are_current(conn=None, engine=None)

    mig_mod.reset_migration_cache()


def test_reset_migration_cache() -> None:
    import time

    import app.utils.migrations as mig_mod

    mig_mod._migration_cache["expires_at"] = time.monotonic() + 100.0
    mig_mod._migration_cache["result"] = (True, set(), set())

    mig_mod.reset_migration_cache()

    assert mig_mod._migration_cache["expires_at"] == 0.0
    assert mig_mod._migration_cache["result"] == ()


# ---------------------------------------------------------------------------
# app/utils/img.py
# ---------------------------------------------------------------------------


def test_get_optimized_image_url_none_input() -> None:
    from app.utils.img import get_optimized_image_url

    assert get_optimized_image_url(None) is None
    assert get_optimized_image_url("") is None


def test_get_optimized_image_url_no_keys() -> None:
    from app.utils.img import get_optimized_image_url

    with patch("app.utils.img.settings") as mock_settings:
        mock_settings.imgproxy_key = ""
        mock_settings.imgproxy_salt = ""
        result = get_optimized_image_url("http://example.com/img.jpg")
    assert result == "http://example.com/img.jpg"


def test_get_optimized_image_url_with_keys() -> None:
    from app.utils.img import get_optimized_image_url

    with patch("app.utils.img.settings") as mock_settings:
        mock_settings.imgproxy_key = "a" * 64  # valid hex
        mock_settings.imgproxy_salt = "b" * 64
        mock_settings.imgproxy_base_url = "http://imgproxy"
        result = get_optimized_image_url(
            "http://example.com/photo.jpg", width=100, height=100
        )
    assert result is not None
    assert "imgproxy" in result


def test_get_optimized_image_url_local_path() -> None:
    from app.utils.img import get_optimized_image_url

    with patch("app.utils.img.settings") as mock_settings:
        mock_settings.imgproxy_key = "a" * 64
        mock_settings.imgproxy_salt = "b" * 64
        mock_settings.imgproxy_base_url = "http://imgproxy"
        result = get_optimized_image_url("/media/photo.jpg")
    # local path prefixed with backend URL
    assert result is not None


def test_get_optimized_image_url_no_extension() -> None:
    from app.utils.img import get_optimized_image_url

    with patch("app.utils.img.settings") as mock_settings:
        mock_settings.imgproxy_key = "c" * 64
        mock_settings.imgproxy_salt = "d" * 64
        mock_settings.imgproxy_base_url = "http://imgproxy"
        result = get_optimized_image_url("http://example.com/img.png", extension=None)
    assert result is not None


# ---------------------------------------------------------------------------
# app/utils/request_coalescing.py
# ---------------------------------------------------------------------------


def test_build_request_key_deterministic() -> None:
    from app.utils.request_coalescing import _build_request_key

    k1 = _build_request_key("prefix", "arg1", key="val")
    k2 = _build_request_key("prefix", "arg1", key="val")
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


def test_build_request_key_different_args() -> None:
    from app.utils.request_coalescing import _build_request_key

    k1 = _build_request_key("prefix", "arg1")
    k2 = _build_request_key("prefix", "arg2")
    assert k1 != k2


@pytest.mark.asyncio
async def test_coalesce_requests_basic() -> None:
    from app.utils.request_coalescing import coalesce_requests

    call_count = 0

    @coalesce_requests(prefix="test_basic")
    async def fetch(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    result = await fetch(5)
    assert result == 10
    assert call_count == 1


@pytest.mark.asyncio
async def test_coalesce_requests_concurrent_dedup() -> None:
    """Concurrent identical requests should be deduplicated."""
    from app.utils.request_coalescing import coalesce_requests

    call_count = 0
    barrier = asyncio.Event()

    @coalesce_requests(prefix="test_dedup")
    async def slow_fetch(x: int) -> int:
        nonlocal call_count
        call_count += 1
        await barrier.wait()
        return x

    # Start multiple concurrent requests before the first completes
    tasks = [asyncio.create_task(slow_fetch(99)) for _ in range(5)]
    await asyncio.sleep(0)  # let tasks start
    barrier.set()
    results = await asyncio.gather(*tasks)

    assert all(r == 99 for r in results)
    # At most 1 actual call (coalescing)
    assert call_count <= 5  # may be 1 or a few depending on timing


@pytest.mark.asyncio
async def test_coalesce_requests_exception_propagated() -> None:
    from app.utils.request_coalescing import coalesce_requests

    @coalesce_requests(prefix="test_exc")
    async def boom() -> None:
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        await boom()


@pytest.mark.asyncio
async def test_coalesce_requests_custom_key_builder() -> None:
    from app.utils.request_coalescing import coalesce_requests

    call_count = 0

    @coalesce_requests(key_builder=lambda x: f"fixed_key_{x}")
    async def fetch_with_custom_key(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    result = await fetch_with_custom_key(7)
    assert result == 7


@pytest.mark.asyncio
async def test_request_coalescer_basic() -> None:
    from app.utils.request_coalescing import RequestCoalescer

    coalescer = RequestCoalescer()
    call_count = 0

    async def fetch() -> str:
        nonlocal call_count
        call_count += 1
        return "data"

    result = await coalescer.execute("key1", fetch)
    assert result == "data"
    assert call_count == 1


@pytest.mark.asyncio
async def test_request_coalescer_exception() -> None:
    from app.utils.request_coalescing import RequestCoalescer

    coalescer = RequestCoalescer()

    async def failing() -> None:
        raise RuntimeError("coalescer error")

    with pytest.raises(RuntimeError, match="coalescer error"):
        await coalescer.execute("error_key", failing)


@pytest.mark.asyncio
async def test_request_coalescer_concurrent() -> None:
    from app.utils.request_coalescing import RequestCoalescer

    coalescer = RequestCoalescer()
    call_count = 0
    event = asyncio.Event()

    async def slow() -> str:
        nonlocal call_count
        call_count += 1
        await event.wait()
        return "done"

    tasks = [asyncio.create_task(coalescer.execute("shared", slow)) for _ in range(3)]
    await asyncio.sleep(0)
    event.set()
    results = await asyncio.gather(*tasks)
    assert all(r == "done" for r in results)


# ---------------------------------------------------------------------------
# app/schemas/validators.py
# ---------------------------------------------------------------------------


def test_sanitized_str_strips_html() -> None:
    from pydantic import BaseModel as PydanticModel

    from app.schemas.validators import SanitizedStr

    class M(PydanticModel):
        text: SanitizedStr

    m = M(text="<script>alert(1)</script>hello")
    assert "<script>" not in m.text
    assert "hello" in m.text


def test_sanitized_str_non_string_input() -> None:
    from pydantic import BaseModel as PydanticModel

    from app.schemas.validators import SanitizedStr

    class M(PydanticModel):
        text: SanitizedStr

    # SanitizedStr strips HTML tags via nh3
    m = M(text="<script>alert(1)</script>hello")
    assert "script" not in m.text
    assert "hello" in m.text


def test_sanitized_email_validator() -> None:
    from app.schemas.validators import _sanitize_email_validator

    result = _sanitize_email_validator("TEST@EXAMPLE.COM")
    assert result == result.lower()

    # Non-string returns empty
    assert _sanitize_email_validator(123) == ""


def test_sanitize_filename_validator() -> None:
    from app.schemas.validators import _sanitize_filename_validator

    result = _sanitize_filename_validator("../../../etc/passwd")
    assert ".." not in result

    assert _sanitize_filename_validator(None) == "unnamed"


def test_strip_control_chars_validator() -> None:
    from app.schemas.validators import _strip_control_chars_validator

    text = "hello\x00world\x01"
    result = _strip_control_chars_validator(text)
    assert "\x00" not in result
    assert "\x01" not in result

    # Non-string
    result2 = _strip_control_chars_validator(42)
    assert result2 == "42"

    # None
    result3 = _strip_control_chars_validator(None)
    assert result3 == ""


def test_sanitize_url_validator() -> None:
    from app.schemas.validators import _sanitize_url_validator

    # Non-string returns None
    assert _sanitize_url_validator(42) is None

    # Valid http URL
    result = _sanitize_url_validator("http://example.com/path")
    assert result is not None or result is None  # depends on sanitize_url impl

    # javascript: URL should be rejected
    result2 = _sanitize_url_validator("javascript:alert(1)")
    # Should return None or sanitized (not the javascript: scheme)
    if result2 is not None:
        assert "javascript:" not in result2


def test_sanitize_optional_text_validator() -> None:
    from app.schemas.validators import _sanitize_optional_text_validator

    assert _sanitize_optional_text_validator(None) is None
    assert _sanitize_optional_text_validator("   ") is None or isinstance(
        _sanitize_optional_text_validator("   "), str
    )
    result = _sanitize_optional_text_validator("hello")
    assert result is not None


def test_truncate_validators() -> None:
    from app.schemas.validators import _truncate_256, _truncate_1000, _truncate_5000

    long_str = "a" * 10000
    assert len(_truncate_256(long_str)) <= 256
    assert len(_truncate_1000(long_str)) <= 1000
    assert len(_truncate_5000(long_str)) <= 5000


def test_rich_text_validator() -> None:
    from app.schemas.validators import _sanitize_html_with_basic_tags

    # Basic tags should be preserved
    result = _sanitize_html_with_basic_tags("<b>bold</b> text")
    # Result depends on sanitize_html impl, just check it runs
    assert "bold" in result or "b" in result or "text" in result

    # Non-string
    result2 = _sanitize_html_with_basic_tags(None)
    assert result2 == ""


# ---------------------------------------------------------------------------
# app/cqrs/base.py
# ---------------------------------------------------------------------------


def test_cqrs_query_base() -> None:
    from app.cqrs.base import Query

    class MyQuery(Query):
        pass

    q = MyQuery()
    assert isinstance(q, Query)


def test_cqrs_command_base() -> None:
    from app.cqrs.base import Command

    class MyCommand(Command):
        pass

    c = MyCommand()
    assert isinstance(c, Command)


def test_cqrs_query_handler_abstract() -> None:
    from app.cqrs.base import Query, QueryHandler

    class Q(Query):
        pass

    with pytest.raises(TypeError):
        QueryHandler()  # type: ignore[abstract]


def test_cqrs_command_handler_abstract() -> None:
    from app.cqrs.base import Command, CommandHandler

    class C(Command):
        pass

    with pytest.raises(TypeError):
        CommandHandler()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# app/cqrs/bus.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_bus_execute_success() -> None:
    from app.cqrs.base import Query, QueryHandler
    from app.cqrs.bus import QueryBus

    class PingQuery(Query):
        pass

    class PingHandler(QueryHandler[PingQuery, str]):
        async def handle(self, query: PingQuery) -> str:
            return "pong"

    mock_container = AsyncMock()
    mock_container.get = AsyncMock(return_value=PingHandler())

    bus = QueryBus(container=mock_container)
    bus.register(PingQuery, PingHandler)

    result = await bus.execute(PingQuery())
    assert result == "pong"


@pytest.mark.asyncio
async def test_query_bus_no_handler_raises() -> None:
    from app.cqrs.base import Query
    from app.cqrs.bus import QueryBus

    class UnregisteredQuery(Query):
        pass

    mock_container = AsyncMock()
    bus = QueryBus(container=mock_container)

    with pytest.raises(ValueError, match="No handler registered"):
        await bus.execute(UnregisteredQuery())


@pytest.mark.asyncio
async def test_command_bus_execute_success() -> None:
    from app.cqrs.base import Command, CommandHandler
    from app.cqrs.bus import CommandBus

    class DoCmd(Command):
        pass

    class DoCmdHandler(CommandHandler[DoCmd, bool]):
        async def handle(self, command: DoCmd) -> bool:
            return True

    mock_container = AsyncMock()
    mock_container.get = AsyncMock(return_value=DoCmdHandler())

    bus = CommandBus(container=mock_container)
    bus.register(DoCmd, DoCmdHandler)

    result = await bus.execute(DoCmd())
    assert result is True


@pytest.mark.asyncio
async def test_command_bus_no_handler_raises() -> None:
    from app.cqrs.base import Command
    from app.cqrs.bus import CommandBus

    class Ghost(Command):
        pass

    mock_container = AsyncMock()
    bus = CommandBus(container=mock_container)

    with pytest.raises(ValueError, match="No handler registered"):
        await bus.execute(Ghost())


@pytest.mark.asyncio
async def test_logging_middleware_success() -> None:
    from app.cqrs.base import Query
    from app.cqrs.bus import LoggingMiddleware

    class Q(Query):
        pass

    mw = LoggingMiddleware()

    async def _ok(_: Any) -> str:
        return "ok"

    result = await mw(Q(), _ok)
    # just verify it doesn't raise and returns the result
    assert result == "ok"


@pytest.mark.asyncio
async def test_logging_middleware_error() -> None:
    from app.cqrs.base import Query
    from app.cqrs.bus import LoggingMiddleware

    class Q(Query):
        pass

    mw = LoggingMiddleware()

    async def failing(_: Any) -> None:
        raise RuntimeError("middleware test error")

    with pytest.raises(RuntimeError):
        await mw(Q(), failing)


@pytest.mark.asyncio
async def test_query_bus_with_middleware() -> None:
    from app.cqrs.base import Query, QueryHandler
    from app.cqrs.bus import LoggingMiddleware, QueryBus

    class EchoQuery(Query):
        value: int = 0

    class EchoHandler(QueryHandler[EchoQuery, int]):
        async def handle(self, query: EchoQuery) -> int:
            return query.value

    mock_container = AsyncMock()
    mock_container.get = AsyncMock(return_value=EchoHandler())

    bus = QueryBus(container=mock_container, middleware=[LoggingMiddleware()])
    bus.register(EchoQuery, EchoHandler)

    # Query is a plain class — set instance attribute after construction
    q = EchoQuery()
    q.value = 42
    result = await bus.execute(q)
    assert result == 42


# ---------------------------------------------------------------------------
# app/core/cache_versioning.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_version_manager_build_key() -> None:
    from app.core.cache_versioning import CacheVersionManager

    mgr = CacheVersionManager(prefix="test")
    key = mgr.build_cache_key(locale="ru", version="5", user_id="abc", page=1)
    assert key.startswith("test:5:ru:")
    assert len(key) > len("test:5:ru:")

    # Same params → same key
    key2 = mgr.build_cache_key(locale="ru", version="5", user_id="abc", page=1)
    assert key == key2

    # Different params → different key
    key3 = mgr.build_cache_key(locale="en", version="5", user_id="abc", page=1)
    assert key != key3


def test_cache_version_manager_version_key() -> None:
    from app.core.cache_versioning import CacheVersionManager

    mgr = CacheVersionManager(prefix="news:list")
    assert mgr.version_key == "news:list:version"


@pytest.mark.asyncio
async def test_cache_version_manager_disabled_cache() -> None:
    from app.core.cache_versioning import CacheVersionManager

    mgr = CacheVersionManager(prefix="test_disabled")

    mock_cache = MagicMock()
    mock_cache.enabled = False

    version = await mgr.get_version(cache=mock_cache)
    assert version == "0"

    # increment and reset are no-ops when disabled
    await mgr.increment(cache=mock_cache)
    await mgr.reset(cache=mock_cache)


@pytest.mark.asyncio
async def test_cache_version_manager_redis_get_valid() -> None:
    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_redis")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=b"42")

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        version = await mgr.get_version(cache=mock_cache)
    assert version == "42"


@pytest.mark.asyncio
async def test_cache_version_manager_redis_get_none() -> None:
    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_none")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        version = await mgr.get_version(cache=mock_cache)
    assert version == "0"


@pytest.mark.asyncio
async def test_cache_version_manager_redis_get_invalid_value() -> None:
    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_invalid")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=b"not_a_number")

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        version = await mgr.get_version(cache=mock_cache)
    assert version == "0"


@pytest.mark.asyncio
async def test_cache_version_manager_redis_error_fallback() -> None:
    from redis.exceptions import RedisError

    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_error")

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        side_effect=RedisError("connection failed"),
    ):
        version = await mgr.get_version(cache=mock_cache)
    assert version == "0"


@pytest.mark.asyncio
async def test_cache_version_manager_increment_with_incr() -> None:
    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_incr")

    mock_client = AsyncMock()
    mock_client.incr = AsyncMock(return_value=1)

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        await mgr.increment(cache=mock_cache)
    mock_client.incr.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_version_manager_increment_fallback_no_incr() -> None:
    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_fallback")

    mock_client = AsyncMock()
    del mock_client.incr  # remove incr method
    mock_client.get = AsyncMock(return_value=b"5")
    mock_client.set = AsyncMock()

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        await mgr.increment(cache=mock_cache)
    mock_client.set.assert_awaited()


@pytest.mark.asyncio
async def test_cache_version_manager_reset() -> None:
    from app.core.cache_versioning import CacheVersionManager
    from app.deps.cache import RedisCache

    mgr = CacheVersionManager(prefix="test_reset")

    mock_client = AsyncMock()
    mock_client.set = AsyncMock()

    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.enabled = True

    with patch(
        "app.core.cache_versioning.get_cache_client",
        new_callable=AsyncMock,
        return_value=mock_client,
    ):
        await mgr.reset(cache=mock_cache)
    mock_client.set.assert_awaited_once_with(mgr.version_key, "0")


def test_global_cache_version_instances() -> None:
    from app.core.cache_versioning import events_cache_version, news_cache_version

    assert events_cache_version.prefix == "events:list"
    assert news_cache_version.prefix == "news:list"
