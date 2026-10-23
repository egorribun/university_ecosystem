"""Ordinary checks for the byte-frozen AUD-350 migration fixture."""

import sys
from uuid import uuid4

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
