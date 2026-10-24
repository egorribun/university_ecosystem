"""Ordinary checks for frozen AUD-350 input and isolated probe routing."""

import sys
from uuid import uuid4

import pytest

from tests.integration import test_aud350_stored_event_timestamp_migration as probe
from tests.integration.test_aud350_stored_event_timestamp_migration import (
    BASELINE_MIGRATION_PATH,
    _load_migration,
    _verify_frozen_baseline_and_candidate_delta,
)


def test_frozen_baseline_checksum_and_candidate_delta() -> None:
    _verify_frozen_baseline_and_candidate_delta()


def test_frozen_baseline_loads_from_raw_source_fixture() -> None:
    module_name = f"aud350_frozen_baseline_{uuid4().hex}"
    migration = _load_migration(BASELINE_MIGRATION_PATH, module_name)
    try:
        assert migration.__file__ == str(BASELINE_MIGRATION_PATH)
        assert migration.revision == "202603280001"
        assert callable(migration.upgrade)
        assert callable(migration.downgrade)
    finally:
        sys.modules.pop(module_name, None)


def test_counterfactual_uses_only_its_explicit_postgres_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    general_url = "sqlite+aiosqlite:///:memory:"
    probe_url = "postgresql+asyncpg://test@127.0.0.1:5433/test_migration"
    monkeypatch.setenv("DATABASE_URL", general_url)
    monkeypatch.setenv("AUD350_POSTGRES_DATABASE_URL", probe_url)

    class TargetSelected(Exception):
        pass

    def observe_engine_target(url, *, pool_pre_ping):
        assert str(url) == "postgresql+psycopg://test@127.0.0.1:5433/test_migration"
        assert pool_pre_ping is True
        assert probe.os.environ["DATABASE_URL"] == general_url
        raise TargetSelected

    monkeypatch.setattr(probe.sa, "create_engine", observe_engine_target)
    fixture = probe.postgres_engine.__wrapped__()
    with pytest.raises(TargetSelected):
        next(fixture)


def test_counterfactual_rejects_missing_target_without_default_database_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUD350_POSTGRES_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://test@127.0.0.1:5433/test_migration"
    )

    def unexpected_engine(*_args, **_kwargs):
        pytest.fail("missing explicit probe target must not create an engine")

    monkeypatch.setattr(probe.sa, "create_engine", unexpected_engine)
    fixture = probe.postgres_engine.__wrapped__()
    with pytest.raises(pytest.fail.Exception, match="AUD350_POSTGRES_DATABASE_URL"):
        next(fixture)
