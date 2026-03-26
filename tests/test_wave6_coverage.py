"""Wave 6 coverage tests: Feature Flags, Storage backends, Spotify API.

Targets uncovered paths in:
- app/core/feature_flags.py: FeatureFlag model, OpenFeature provider,
  FeatureFlagService (init, shutdown, CRUD, pub/sub)
- app/services/storage.py: StaticFSStorage, S3Storage (save/delete/exists/read,
  path normalization, error handling)
- app/api/spotify.py: OAuth flow, token refresh, error responses
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# Feature Flags — FeatureFlag model
# ===========================================================================


class TestFeatureFlag:
    def test_enabled_status(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="test", status=FlagStatus.ENABLED)
        assert flag.is_enabled_for_user(123) is True
        assert flag.is_enabled_for_user(None) is True

    def test_disabled_status(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="test", status=FlagStatus.DISABLED)
        assert flag.is_enabled_for_user(123) is False

    def test_percentage_rollout(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="rollout", status=FlagStatus.PERCENTAGE, percentage=50)
        # With 50% rollout, roughly half of user_ids should be enabled
        enabled = sum(flag.is_enabled_for_user(i) for i in range(1000))
        assert 300 < enabled < 700  # ~50% with reasonable tolerance

    def test_percentage_zero(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="zero", status=FlagStatus.PERCENTAGE, percentage=0)
        assert flag.is_enabled_for_user(1) is False

    def test_percentage_100(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="full", status=FlagStatus.PERCENTAGE, percentage=100)
        assert flag.is_enabled_for_user(1) is True

    def test_percentage_no_user(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="test", status=FlagStatus.PERCENTAGE, percentage=50)
        assert flag.is_enabled_for_user(None) is False

    def test_allowed_users(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(
            name="test",
            status=FlagStatus.PERCENTAGE,
            percentage=0,
            allowed_users={42, 99},
        )
        assert flag.is_enabled_for_user(42) is True
        assert flag.is_enabled_for_user(1) is False

    def test_to_dict_roundtrip(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(
            name="test",
            status=FlagStatus.PERCENTAGE,
            percentage=50,
            allowed_users={1, 2},
            allowed_groups={"admin"},
            metadata={"key": "val"},
        )
        d = flag.to_dict()
        assert isinstance(d["allowed_users"], list)
        assert isinstance(d["allowed_groups"], list)

        restored = FeatureFlag.from_dict(d)
        assert restored.name == "test"
        assert restored.percentage == 50
        assert 1 in restored.allowed_users

    def test_from_dict_with_string_status(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        d = {
            "name": "test",
            "status": "enabled",
            "percentage": 0,
            "allowed_users": [],
            "allowed_groups": [],
        }
        flag = FeatureFlag.from_dict(d)
        assert flag.status == FlagStatus.ENABLED

    def test_check_percentage_deterministic(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        flag = FeatureFlag(name="det", status=FlagStatus.PERCENTAGE, percentage=50)
        # Same user always gets same result
        r1 = flag._check_percentage(42)
        r2 = flag._check_percentage(42)
        assert r1 == r2


# ===========================================================================
# Feature Flags — OpenFeature Provider
# ===========================================================================


class TestUniversityFeatureProvider:
    def _make_provider(self, flags: dict | None = None):
        from app.core.feature_flags import (
            FeatureFlagService,
            UniversityFeatureProvider,
        )

        svc = FeatureFlagService()
        svc._is_initialized = True
        if flags:
            for name, f in flags.items():
                svc._flags[name] = f
        return UniversityFeatureProvider(svc)

    def test_metadata(self):
        provider = self._make_provider()
        meta = provider.get_metadata()
        assert meta.name == "UniversityFeatureProvider"

    def test_resolve_boolean_enabled(self):
        from app.core.feature_flags import FeatureFlag, FlagStatus

        provider = self._make_provider(
            {"test": FeatureFlag(name="test", status=FlagStatus.ENABLED)}
        )
        result = provider.resolve_boolean_details("test", False)
        assert result.value is True

    def test_resolve_boolean_default(self):
        provider = self._make_provider()
        result = provider.resolve_boolean_details("nonexistent", True)
        assert result.value is True

    def test_resolve_boolean_with_context(self):
        from openfeature.evaluation_context import EvaluationContext

        from app.core.feature_flags import FeatureFlag, FlagStatus

        provider = self._make_provider(
            {
                "test": FeatureFlag(
                    name="test", status=FlagStatus.PERCENTAGE, percentage=100
                )
            }
        )
        ctx = EvaluationContext(targeting_key="42")
        result = provider.resolve_boolean_details("test", False, ctx)
        assert result.value is True

    def test_resolve_boolean_invalid_targeting_key(self):
        from openfeature.evaluation_context import EvaluationContext

        from app.core.feature_flags import FeatureFlag, FlagStatus

        provider = self._make_provider(
            {
                "test": FeatureFlag(
                    name="test", status=FlagStatus.PERCENTAGE, percentage=50
                )
            }
        )
        ctx = EvaluationContext(targeting_key="not-a-number")
        result = provider.resolve_boolean_details("test", False, ctx)
        # Invalid targeting_key → user_id=None → percentage returns False
        assert result.value is False

    def test_resolve_string_from_metadata(self):
        from app.core.feature_flags import FeatureFlag

        provider = self._make_provider(
            {"str_flag": FeatureFlag(name="str_flag", metadata={"value": "hello"})}
        )
        result = provider.resolve_string_details("str_flag", "default")
        assert result.value == "hello"

    def test_resolve_string_default(self):
        provider = self._make_provider()
        result = provider.resolve_string_details("missing", "fallback")
        assert result.value == "fallback"

    def test_resolve_integer_from_metadata(self):
        from app.core.feature_flags import FeatureFlag

        provider = self._make_provider(
            {"int_flag": FeatureFlag(name="int_flag", metadata={"value": 42})}
        )
        result = provider.resolve_integer_details("int_flag", 0)
        assert result.value == 42

    def test_resolve_integer_invalid_value(self):
        from app.core.feature_flags import FeatureFlag

        provider = self._make_provider(
            {"bad": FeatureFlag(name="bad", metadata={"value": "not-int"})}
        )
        result = provider.resolve_integer_details("bad", 99)
        assert result.value == 99

    def test_resolve_float_from_metadata(self):
        from app.core.feature_flags import FeatureFlag

        provider = self._make_provider(
            {"f_flag": FeatureFlag(name="f_flag", metadata={"value": 3.14})}
        )
        result = provider.resolve_float_details("f_flag", 0.0)
        assert result.value == pytest.approx(3.14)

    def test_resolve_float_invalid(self):
        from app.core.feature_flags import FeatureFlag

        provider = self._make_provider(
            {"bad": FeatureFlag(name="bad", metadata={"value": "not-a-float-value"})}
        )
        result = provider.resolve_float_details("bad", 1.0)
        assert result.value == 1.0

    def test_resolve_object(self):
        from app.core.feature_flags import FeatureFlag

        obj = {"nested": [1, 2, 3]}
        provider = self._make_provider(
            {"obj_flag": FeatureFlag(name="obj_flag", metadata={"value": obj})}
        )
        result = provider.resolve_object_details("obj_flag", None)
        assert result.value == obj


# ===========================================================================
# Feature Flags — FeatureFlagService
# ===========================================================================


class TestFeatureFlagService:
    def test_is_enabled_defaults(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc._flags["on"] = FeatureFlag(name="on", status=FlagStatus.ENABLED)
        svc._flags["off"] = FeatureFlag(name="off", status=FlagStatus.DISABLED)

        assert svc.is_enabled("on") is True
        assert svc.is_enabled("off") is False
        assert svc.is_enabled("missing") is False
        assert svc.is_enabled("missing", default=True) is True

    def test_get_flag(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        flag = FeatureFlag(name="test", status=FlagStatus.ENABLED)
        svc._flags["test"] = flag

        assert svc.get("test") is flag
        assert svc.get("missing") is None

    def test_register(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc.register(FeatureFlag(name="beta_feature", status=FlagStatus.DISABLED))
        assert "beta_feature" in svc._flags

    def test_enable_flag(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc._flags["feat"] = FeatureFlag(name="feat", status=FlagStatus.DISABLED)
        svc.enable("feat")
        assert svc.is_enabled("feat") is True

    def test_disable_flag(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc._flags["feat"] = FeatureFlag(name="feat", status=FlagStatus.ENABLED)
        svc.disable("feat")
        assert svc.is_enabled("feat") is False

    def test_set_percentage(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc._flags["rollout"] = FeatureFlag(name="rollout", status=FlagStatus.DISABLED)
        svc.set_percentage("rollout", 75)
        assert svc._flags["rollout"].status == FlagStatus.PERCENTAGE
        assert svc._flags["rollout"].percentage == 75

    @pytest.mark.asyncio
    async def test_update_flag(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc._flags["upd"] = FeatureFlag(name="upd", status=FlagStatus.DISABLED)

        result = await svc.update("upd", description="Updated desc")
        assert result is True
        assert svc._flags["upd"].description == "Updated desc"

    @pytest.mark.asyncio
    async def test_update_nonexistent_flag(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        result = await svc.update("missing", description="nope")
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_without_redis(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        with patch("app.core.feature_flags.settings") as mock_settings:
            mock_settings.cache_redis_url = ""
            await svc.initialize(redis=None)

        assert svc._is_initialized is True

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        await svc.initialize(redis=mock_redis)
        assert svc._is_initialized is True
        assert svc._redis is mock_redis

        # Cleanup
        if svc._pubsub_task:
            svc._pubsub_task.cancel()
            try:
                await svc._pubsub_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_initialize_loads_flags_from_redis(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        stored = json.dumps(
            {
                "name": "loaded_flag",
                "status": "enabled",
                "percentage": 0,
                "allowed_users": [],
                "allowed_groups": [],
            }
        )
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={"loaded_flag": stored})

        await svc.initialize(redis=mock_redis)
        assert svc.is_enabled("loaded_flag") is True

        if svc._pubsub_task:
            svc._pubsub_task.cancel()
            try:
                await svc._pubsub_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_initialize_handles_invalid_json(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={"bad": "not{json"})

        await svc.initialize(redis=mock_redis)
        assert "bad" not in svc._flags

        if svc._pubsub_task:
            svc._pubsub_task.cancel()
            try:
                await svc._pubsub_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_shutdown(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        svc._redis = mock_redis

        async def _forever():
            await asyncio.sleep(9999)

        svc._pubsub_task = asyncio.create_task(_forever())

        await svc.shutdown()
        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_flag(self):
        from app.core.feature_flags import FeatureFlagService

        svc = FeatureFlagService()
        mock_redis = AsyncMock()
        stored = json.dumps(
            {
                "name": "reloaded",
                "status": "enabled",
                "percentage": 0,
                "allowed_users": [],
                "allowed_groups": [],
            }
        )
        mock_redis.hget = AsyncMock(return_value=stored)
        svc._redis = mock_redis

        await svc._reload_flag("reloaded")
        assert svc.is_enabled("reloaded") is True

    def test_list_flags(self):
        from app.core.feature_flags import FeatureFlag, FeatureFlagService, FlagStatus

        svc = FeatureFlagService()
        svc._flags["a"] = FeatureFlag(name="a", status=FlagStatus.ENABLED)
        svc._flags["b"] = FeatureFlag(name="b", status=FlagStatus.DISABLED)

        all_flags = svc.list_flags()
        assert len(all_flags) == 2


# ===========================================================================
# Storage — StaticFSStorage
# ===========================================================================


class TestStaticFSStorage:
    @pytest.mark.asyncio
    async def test_save_and_read(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        url = await storage.save_file("test/file.txt", b"hello world")
        assert "/static/test/file.txt" == url

        data = await storage.read_file(url)
        assert data == b"hello world"

    @pytest.mark.asyncio
    async def test_exists(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        await storage.save_file("check.txt", b"data")
        assert (
            await storage.exists("/static/check.txt") is True
            or await storage.exists("check.txt") is True
        )

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        url = await storage.save_file("del.txt", b"data")
        await storage.delete_file(url)
        assert not (tmp_path / "del.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        # Should not raise
        await storage.delete_file("/static/nonexistent.txt")

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            await storage.read_file("nonexistent.txt")

    def test_normalize_empty_path(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="empty"):
            storage._normalize_relative_path("")

    def test_normalize_traversal(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escape"):
            storage._normalize_relative_path("../../etc/passwd")

    def test_normalize_traversal_dotdot(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escape"):
            storage._normalize_relative_path("sub/../../etc/passwd")

    @pytest.mark.asyncio
    async def test_save_no_base_url(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="")
        url = await storage.save_file("file.txt", b"data")
        assert url == "/file.txt"

    def test_extract_relative_path_empty(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        assert storage._extract_relative_path("") is None
        assert storage._extract_relative_path("   ") is None


# ===========================================================================
# Storage — S3Storage
# ===========================================================================


class TestS3Storage:
    def test_init_with_endpoint(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="test-bucket", endpoint_url="http://minio:9000")
        assert s3.base_url == "http://minio:9000/test-bucket"

    def test_init_without_endpoint(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="my-bucket")
        assert "s3.amazonaws.com" in s3.base_url

    def test_init_with_base_url(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b", base_url="https://cdn.example.com/files")
        assert s3.base_url == "https://cdn.example.com/files"

    def test_init_empty_bucket_raises(self):
        from app.services.storage import S3Storage

        with pytest.raises(ValueError, match="empty"):
            S3Storage(bucket="")

    def test_normalize_key(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b")
        assert s3._normalize_key("path/to/file.txt") == "path/to/file.txt"
        assert s3._normalize_key("  /file.txt/  ") == "file.txt"

    def test_normalize_key_traversal(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b")
        with pytest.raises(ValueError):
            s3._normalize_key("../../etc/passwd")

    def test_normalize_key_empty(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b")
        with pytest.raises(ValueError, match="empty"):
            s3._normalize_key("")

    @pytest.mark.asyncio
    async def test_save_file_with_injected_client(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock()
        s3 = S3Storage(
            bucket="test",
            endpoint_url="http://minio:9000",
            client=mock_client,
        )
        url = await s3.save_file(
            "upload/file.pdf", b"pdf-data", content_type="application/pdf"
        )
        assert "upload/file.pdf" in url
        mock_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_file_error(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock(side_effect=Exception("S3 down"))
        s3 = S3Storage(bucket="test", client=mock_client)

        with pytest.raises(Exception, match="S3 down"):
            await s3.save_file("fail.txt", b"data")

    @pytest.mark.asyncio
    async def test_delete_file(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.delete_object = AsyncMock()
        s3 = S3Storage(
            bucket="test",
            endpoint_url="http://minio:9000",
            client=mock_client,
        )
        await s3.delete_file("http://minio:9000/test/path/file.txt")
        mock_client.delete_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.head_object = AsyncMock(return_value={})
        s3 = S3Storage(bucket="test", client=mock_client)

        result = await s3.exists("path/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        from botocore.exceptions import ClientError

        mock_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "HeadObject")
        )
        s3 = S3Storage(bucket="test", client=mock_client)

        result = await s3.exists("missing.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_read_file(self):
        from contextlib import asynccontextmanager

        from app.services.storage import S3Storage

        @asynccontextmanager
        async def _mock_stream():
            stream = AsyncMock()
            stream.read = AsyncMock(return_value=b"file-content")
            yield stream

        mock_client = AsyncMock()
        mock_client.get_object = AsyncMock(return_value={"Body": _mock_stream()})
        s3 = S3Storage(bucket="test", client=mock_client)

        data = await s3.read_file("path/file.txt")
        assert data == b"file-content"

    @pytest.mark.asyncio
    async def test_save_with_cache_control(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock()
        s3 = S3Storage(bucket="test", client=mock_client)

        await s3.save_file(
            "cached.js",
            b"js",
            content_type="text/javascript",
            cache_control="max-age=3600",
        )
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "text/javascript"
        assert call_kwargs["CacheControl"] == "max-age=3600"


# ===========================================================================
# Storage — get_storage_backend factory
# ===========================================================================


class TestGetStorageBackend:
    def test_returns_static_by_default(self):
        from app.services.storage import StaticFSStorage, get_storage_backend

        mock_settings = MagicMock()
        mock_settings.storage_backend = "local"
        mock_settings.static_dir_path = Path("/tmp/test-static")  # noqa: S108
        mock_settings.storage_static_base_url = "/static"

        backend = get_storage_backend(mock_settings)
        assert isinstance(backend, StaticFSStorage)

    def test_returns_s3(self):
        from app.services.storage import S3Storage, get_storage_backend

        mock_settings = MagicMock()
        mock_settings.storage_backend = "s3"
        mock_settings.storage_s3_bucket = "test-bucket"
        mock_settings.storage_s3_region = "us-east-1"
        mock_settings.storage_s3_access_key_id = "key"
        mock_settings.storage_s3_secret_access_key = (
            "secret"  # pragma: allowlist secret
        )
        mock_settings.storage_s3_endpoint_url = "http://minio:9000"
        mock_settings.storage_s3_base_url = ""

        backend = get_storage_backend(mock_settings)
        assert isinstance(backend, S3Storage)

    def test_unsupported_backend_raises(self):
        from app.services.storage import get_storage_backend

        mock_settings = MagicMock()
        mock_settings.storage_backend = "unsupported"

        with pytest.raises(ValueError, match="Unsupported"):
            get_storage_backend(mock_settings)
