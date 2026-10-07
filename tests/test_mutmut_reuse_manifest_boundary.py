from __future__ import annotations

from pathlib import Path

import pytest

from scripts.mutmut_universe import (
    UniverseValidationError,
    validate_universe_manifest,
    write_universe_manifest,
)
from tests.test_mutmut_universe import _FakeCli, _write_universe


def test_primary_manifest_validates_pristine_inputs_and_rejects_full_stats_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_universe(tmp_path)
    monkeypatch.chdir(tmp_path)

    primary_manifest = write_universe_manifest(_FakeCli)
    assert validate_universe_manifest(_FakeCli) == primary_manifest

    stats_path = Path("mutants/mutmut-stats.json")
    stats_path.write_text(
        stats_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(UniverseValidationError, match="stats fingerprint"):
        validate_universe_manifest(_FakeCli)
