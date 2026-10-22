from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts import live_stand


class _TrackedScandir:
    def __init__(self, entries: Iterator[os.DirEntry[str]]) -> None:
        self._entries = entries
        self.yielded = 0
        self.closed = False

    def __enter__(self) -> _TrackedScandir:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.closed = True
        self._entries.close()

    def __iter__(self) -> _TrackedScandir:
        return self

    def __next__(self) -> os.DirEntry[str]:
        entry = next(self._entries)
        self.yielded += 1
        return entry


def _write_probe_markers(directory: Path) -> None:
    for project, timestamp in (("desktop", 1_000), ("mobile", 2_000)):
        (directory / f"aud174-caddy-probe-{project}.json").write_text(
            json.dumps(
                {
                    "schema": "aud174-caddy-probe-v1",
                    "project": project,
                    "completed_at_ms": timestamp,
                }
            ),
            encoding="utf-8",
        )


def _write_unrelated_outputs(
    directory: Path, count: int, *, canary_index: int | None = None
) -> None:
    for index in range(count):
        name = (
            "output-path-private-canary-do-not-disclose"
            if index == canary_index
            else f"playwright-output-{index}"
        )
        (directory / name).write_bytes(b"")


def _patch_scandir(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
) -> list[_TrackedScandir]:
    original_scandir = live_stand.os.scandir
    original_iterdir = Path.iterdir
    tracked: list[_TrackedScandir] = []

    def counted_scandir(path: object = None) -> object:
        if isinstance(path, (str, os.PathLike)) and Path(path) == directory:
            iterator = _TrackedScandir(original_scandir(path))
            tracked.append(iterator)
            return iterator
        return original_scandir(path)

    def forbid_output_path_iterdir(path: Path) -> Iterator[Path]:
        if path == directory:
            pytest.fail("probe reader must scan output incrementally with os.scandir")
        return original_iterdir(path)

    monkeypatch.setattr(live_stand.os, "scandir", counted_scandir)
    monkeypatch.setattr(Path, "iterdir", forbid_output_path_iterdir)
    return tracked


def test_probe_directory_rejects_cap_plus_one_and_closes_iterator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_probe_markers(tmp_path)
    cap = 512  # Fixed contract: count every direct output entry, including markers.
    _write_unrelated_outputs(tmp_path, cap - 1, canary_index=100)
    scans = _patch_scandir(monkeypatch, tmp_path)

    with pytest.raises(live_stand.StandError) as error:
        live_stand._read_live_caddy_probe_observations(
            tmp_path, started_at_ms=500, finished_at_ms=2_500
        )

    assert len(scans) == 1
    assert scans[0].yielded == cap + 1
    assert scans[0].closed
    assert str(error.value) == live_stand._LIVE_CADDY_PROBE_FAILURE
    assert "output-path-private-canary-do-not-disclose" not in str(error.value)
    assert not (tmp_path / "aud174-caddy-probe-desktop.json").exists()
    assert not (tmp_path / "aud174-caddy-probe-mobile.json").exists()


def test_probe_directory_checks_deadline_during_incremental_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_probe_markers(tmp_path)
    _write_unrelated_outputs(tmp_path, 20)
    scans = _patch_scandir(monkeypatch, tmp_path)

    def expire_after_three_scanned(deadline: float | None) -> float:
        assert deadline == 100.5
        if scans and scans[0].yielded >= 3:
            raise live_stand.StandError(live_stand._LIVE_CADDY_PROBE_FAILURE)
        return 1.0

    monkeypatch.setattr(live_stand, "_live_probe_remaining", expire_after_three_scanned)

    with pytest.raises(live_stand.StandError) as error:
        live_stand._read_live_caddy_probe_observations(
            tmp_path,
            started_at_ms=500,
            finished_at_ms=2_500,
            deadline=100.5,
        )

    assert len(scans) == 1
    assert scans[0].yielded == 3
    assert scans[0].closed
    assert str(error.value) == live_stand._LIVE_CADDY_PROBE_FAILURE
    assert not (tmp_path / "aud174-caddy-probe-desktop.json").exists()
    assert not (tmp_path / "aud174-caddy-probe-mobile.json").exists()


def test_probe_directory_accepts_expected_markers_with_bounded_other_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_probe_markers(tmp_path)
    _write_unrelated_outputs(tmp_path, 12)
    scans = _patch_scandir(monkeypatch, tmp_path)

    result = live_stand._read_live_caddy_probe_observations(
        tmp_path,
        started_at_ms=500,
        finished_at_ms=2_500,
        deadline=live_stand.time.monotonic() + 5,
    )

    assert result == {"desktop": 1_000, "mobile": 2_000}
    assert len(scans) == 1
    assert scans[0].yielded == 14
    assert scans[0].closed
    assert not (tmp_path / "aud174-caddy-probe-desktop.json").exists()
    assert not (tmp_path / "aud174-caddy-probe-mobile.json").exists()
