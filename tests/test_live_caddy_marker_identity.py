from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import live_stand

_COMMON_FIELDS = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")


def _synthetic_stat(**changes: int) -> SimpleNamespace:
    values: dict[str, int] = {
        "st_dev": 11,
        "st_ino": 22,
        "st_mode": stat.S_IFREG | 0o600,
        "st_size": 33,
        "st_mtime_ns": 44,
        "st_ctime_ns": 55,
        "st_birthtime_ns": 66,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _copy_stat(info: os.stat_result) -> SimpleNamespace:
    return _synthetic_stat(
        st_dev=info.st_dev,
        st_ino=info.st_ino,
        st_mode=info.st_mode,
        st_size=info.st_size,
        st_mtime_ns=info.st_mtime_ns,
        st_ctime_ns=info.st_ctime_ns,
        st_birthtime_ns=getattr(info, "st_birthtime_ns", 77),
    )


@pytest.mark.parametrize("windows", [False, True], ids=["posix", "windows"])
@pytest.mark.parametrize("field", _COMMON_FIELDS)
def test_marker_identity_changes_with_each_common_field(
    field: str, windows: bool
) -> None:
    original = _synthetic_stat()
    changed = _synthetic_stat(**{field: getattr(original, field) + 1})
    platform_field = "st_birthtime_ns" if windows else "st_ctime_ns"

    expected = (
        *[getattr(original, name) for name in _COMMON_FIELDS],
        getattr(original, platform_field),
    )
    assert live_stand._live_caddy_marker_identity(original, windows=windows) == expected
    assert live_stand._live_caddy_marker_identity(changed, windows=windows) != expected


def test_marker_identity_default_matches_the_current_platform() -> None:
    info = _synthetic_stat()

    assert live_stand._live_caddy_marker_identity(
        info
    ) == live_stand._live_caddy_marker_identity(info, windows=os.name == "nt")


def test_windows_marker_identity_uses_birthtime_and_ignores_deprecated_ctime() -> None:
    original = _synthetic_stat()
    changed_ctime = _synthetic_stat(st_ctime_ns=original.st_ctime_ns + 1)
    changed_birthtime = _synthetic_stat(st_birthtime_ns=original.st_birthtime_ns + 1)

    identity = live_stand._live_caddy_marker_identity(original, windows=True)
    assert (
        live_stand._live_caddy_marker_identity(changed_ctime, windows=True) == identity
    )
    assert (
        live_stand._live_caddy_marker_identity(changed_birthtime, windows=True)
        != identity
    )


def test_posix_marker_identity_uses_ctime_and_ignores_birthtime() -> None:
    original = _synthetic_stat()
    changed_birthtime = _synthetic_stat(st_birthtime_ns=original.st_birthtime_ns + 1)
    changed_ctime = _synthetic_stat(st_ctime_ns=original.st_ctime_ns + 1)

    identity = live_stand._live_caddy_marker_identity(original, windows=False)
    assert (
        live_stand._live_caddy_marker_identity(changed_birthtime, windows=False)
        == identity
    )
    assert (
        live_stand._live_caddy_marker_identity(changed_ctime, windows=False) != identity
    )


def test_windows_marker_identity_fails_closed_when_birthtime_is_unavailable() -> None:
    info = _synthetic_stat()
    del info.st_birthtime_ns

    with pytest.raises(ValueError):
        live_stand._live_caddy_marker_identity(info, windows=True)


def _write_markers(directory: Path) -> None:
    for project, completed_at_ms in (("desktop", 1_000), ("mobile", 2_000)):
        (directory / f"aud174-caddy-probe-{project}.json").write_text(
            json.dumps(
                {
                    "schema": "aud174-caddy-probe-v1",
                    "project": project,
                    "completed_at_ms": completed_at_ms,
                }
            ),
            encoding="utf-8",
        )


def _inject_identity_change(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    *,
    snapshot_point: str,
    field: str,
) -> None:
    original_lstat = Path.lstat
    original_fstat = live_stand.os.fstat
    lstat_calls: dict[str, int] = {}
    fstat_call = 0

    def maybe_change(info: os.stat_result, *, change: bool) -> SimpleNamespace:
        snapshot = _copy_stat(info)
        if change:
            setattr(snapshot, field, getattr(snapshot, field) + 1)
        return snapshot

    def patched_lstat(path: Path) -> os.stat_result | SimpleNamespace:
        info = original_lstat(path)
        if path.parent != directory or not path.name.startswith("aud174-caddy-probe-"):
            return info
        call = lstat_calls.get(path.name, 0) + 1
        lstat_calls[path.name] = call
        change = (snapshot_point == "path_at_open" and call == 3) or (
            snapshot_point == "path_after_read" and call == 4
        )
        return maybe_change(info, change=change)

    def patched_fstat(descriptor: int) -> os.stat_result | SimpleNamespace:
        nonlocal fstat_call
        fstat_call += 1
        info = original_fstat(descriptor)
        change = (snapshot_point == "descriptor_at_open" and fstat_call == 1) or (
            snapshot_point == "descriptor_after_read" and fstat_call == 2
        )
        return maybe_change(info, change=change)

    monkeypatch.setattr(Path, "lstat", patched_lstat)
    monkeypatch.setattr(live_stand.os, "fstat", patched_fstat)


@pytest.mark.parametrize(
    ("snapshot_point", "field"),
    [
        ("descriptor_at_open", "st_ino"),
        ("path_at_open", "st_ino"),
        ("descriptor_after_read", "st_ino"),
        ("path_after_read", "st_ino"),
    ],
    ids=[
        "descriptor-replaced-before-read",
        "path-replaced-before-read",
        "descriptor-changed-during-read",
        "path-replaced-after-read",
    ],
)
def test_marker_reader_rejects_descriptor_or_path_identity_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot_point: str,
    field: str,
) -> None:
    _write_markers(tmp_path)
    _inject_identity_change(
        monkeypatch,
        tmp_path,
        snapshot_point=snapshot_point,
        field=field,
    )

    with pytest.raises(live_stand.StandError) as error:
        live_stand._read_live_caddy_probe_observations(
            tmp_path, started_at_ms=500, finished_at_ms=2_500
        )

    assert str(error.value) == live_stand._LIVE_CADDY_PROBE_FAILURE
    assert "aud174-caddy-probe" not in str(error.value)
    assert list(tmp_path.glob("aud174-caddy-probe-*.json")) == []


def test_marker_reader_rejects_default_platform_timestamp_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    field = "st_birthtime_ns" if os.name == "nt" else "st_ctime_ns"
    _write_markers(tmp_path)
    _inject_identity_change(
        monkeypatch,
        tmp_path,
        snapshot_point="descriptor_after_read",
        field=field,
    )

    with pytest.raises(live_stand.StandError) as error:
        live_stand._read_live_caddy_probe_observations(
            tmp_path, started_at_ms=500, finished_at_ms=2_500
        )

    assert str(error.value) == live_stand._LIVE_CADDY_PROBE_FAILURE
    assert list(tmp_path.glob("aud174-caddy-probe-*.json")) == []
