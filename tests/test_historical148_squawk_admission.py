"""Owner-activated finite historical-148 Squawk admission (decision 2026-10-31).

The tests use the committed policy, the immutable historical SQL bytes, the
recorded migration git object and scanner outputs written to temporary files. No
Squawk binary is downloaded or executed here. A green result proves only the exact
admitted inventory matcher; it does not prove scanner success, migration
permission for another revision or populated-database admission.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import runpy
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.quality import historical148_squawk_admission as admission
from scripts.quality.historical148_squawk_admission import (
    AdmissionError,
    ScenarioEvidence,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "quality/historical148-squawk-policy.json"
CAPTURE = ROOT / "tests/fixtures/historical148-squawk-capture-3d83fb27.json"
MIGRATION = ROOT / "alembic/versions/148642dd1207_fix_missing_tables.py"
SCANNER_SHA256 = json.loads(POLICY.read_bytes())["scanner"]["binary_sha256"]
RECORDED = json.loads(POLICY.read_bytes())


def _git_object_id(data: bytes) -> str:
    """Blob id that `git hash-object` reports for these regular-file bytes."""
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


class World:
    """Temporary copies of the exact historical SQL and scanner evidence."""

    def __init__(self, tmp_path: Path) -> None:
        self.evidence_dir = tmp_path / "evidence"
        self.evidence_dir.mkdir()
        capture = json.loads(CAPTURE.read_bytes())
        self.sql = (
            self.evidence_dir / "148642dd1207.sql",
            self.evidence_dir / "148642dd1207.expanded.sql",
        )
        self.sql[0].write_bytes(capture["ordinary"]["sql"].encode("utf-8"))
        self.sql[1].write_bytes(capture["expanded"]["sql"].encode("utf-8"))
        self.policy: dict[str, Any] = json.loads(POLICY.read_bytes())
        self.scanner_sha256 = SCANNER_SHA256
        self.scanner_version = "squawk 2.67.0"
        # The workflow supplies `git hash-object` of the working-tree migration.
        self.migration_blob = RECORDED["source_blobs"][admission.MIGRATION_PATH]
        self.excludes = tuple(RECORDED["scanner"]["args"])
        self.json_exit = [1, 1]
        for index in range(2):
            self.write_json(index, self.recorded_rows(index))
            self.write_stderr(index, b"")

    def recorded_rows(self, index: int) -> list[dict[str, Any]]:
        """Rows the scanner reports for the committed inventory (live truth)."""
        findings = RECORDED["scenarios"][index]["findings"]
        return [{**finding, "file": str(self.sql[index])} for finding in findings]

    def write_json(self, index: int, rows: Any) -> None:
        path = self.evidence_dir / f"scan-{index}.json"
        path.write_bytes(json.dumps(rows).encode("utf-8"))

    def write_stderr(self, index: int, data: bytes) -> None:
        (self.evidence_dir / f"scan-{index}.stderr").write_bytes(data)

    def evidence(self, index: int, *, raw_exit: int = 1) -> ScenarioEvidence:
        return ScenarioEvidence(
            sql_path=str(self.sql[index]),
            raw_exit=raw_exit,
            json_path=str(self.evidence_dir / f"scan-{index}.json"),
            json_exit=self.json_exit[index],
            stderr_path=str(self.evidence_dir / f"scan-{index}.stderr"),
        )

    def policy_bytes(self) -> bytes:
        return json.dumps(self.policy, ensure_ascii=False).encode("utf-8")

    def admit(self, policy_bytes: bytes | None = None, **overrides: Any) -> str:
        values: dict[str, Any] = {
            "migration_blob": self.migration_blob,
            "scanner_sha256": self.scanner_sha256,
            "scanner_version": self.scanner_version,
            "scanner_args": self.excludes,
            "ordinary": self.evidence(0),
            "expanded": self.evidence(1),
        }
        values.update(overrides)
        return admission.admit(
            self.policy_bytes() if policy_bytes is None else policy_bytes,
            **values,
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    current = [datetime(2026, 10, 31, tzinfo=UTC)]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return current[0].astimezone(tz) if tz else current[0].replace(tzinfo=None)

    monkeypatch.setattr(admission, "datetime", FrozenDateTime)
    return current


def test_exact_historical_inventory_is_admitted(world: World) -> None:
    message = world.admit()
    assert "13 ordinary + 24 expanded" in message
    assert "raw Squawk exits 1/1 retained" in message
    assert "expires 2026-11-13T00:00:00Z" in message


def test_unchanged_migration_bytes_hash_to_the_recorded_git_object(
    world: World,
) -> None:
    unchanged = _git_object_id(MIGRATION.read_bytes())
    assert unchanged == world.migration_blob
    assert "13 ordinary" in world.admit(migration_blob=unchanged)


@pytest.mark.parametrize("index", [0, 1])
def test_warning_order_does_not_change_the_exact_multiset(
    world: World, index: int
) -> None:
    world.write_json(index, list(reversed(world.recorded_rows(index))))
    assert "13 ordinary" in world.admit()


@pytest.mark.parametrize(
    ("index", "mutation"),
    [
        (index, mutation)
        for index in range(2)
        for mutation in (
            "missing",
            "extra",
            "duplicate",
            "changed_rule",
            "changed_line",
        )
    ],
)
def test_one_missing_extra_duplicate_or_changed_warning_fails(
    world: World, index: int, mutation: str
) -> None:
    rows = world.recorded_rows(index)
    if mutation == "missing":
        rows.pop(0)
    elif mutation == "extra":
        rows.append({**rows[0], "rule_name": "ban-drop-column", "line": 999})
    elif mutation == "duplicate":
        rows[1] = dict(rows[0])
    elif mutation == "changed_rule":
        rows[0]["rule_name"] = "changed-rule"
    else:
        rows[0]["line"] += 1
    world.write_json(index, rows)
    with pytest.raises(AdmissionError, match="warning inventory differs"):
        world.admit()


@pytest.mark.parametrize("index", [0, 1])
def test_warning_location_must_name_the_scanned_sql(world: World, index: int) -> None:
    rows = world.recorded_rows(index)
    rows[0]["file"] = "elsewhere/other.sql"
    world.write_json(index, rows)
    with pytest.raises(AdmissionError, match="location is not the scanned SQL"):
        world.admit()


def test_row_without_a_location_fails(world: World) -> None:
    rows = world.recorded_rows(0)
    del rows[0]["file"]
    world.write_json(0, rows)
    with pytest.raises(AdmissionError, match="location is not the scanned SQL"):
        world.admit()


@pytest.mark.parametrize("index", [0, 1])
def test_changed_sql_bytes_fail_the_digest(world: World, index: int) -> None:
    world.sql[index].write_bytes(world.sql[index].read_bytes() + b" ")
    with pytest.raises(AdmissionError, match="SQL digest does not match"):
        world.admit()


@pytest.mark.parametrize("index", [0, 1])
def test_changed_policy_sql_digest_fails(world: World, index: int) -> None:
    world.policy["scenarios"][index]["sql_sha256"] = "0" * 64
    with pytest.raises(AdmissionError, match="SQL digest does not match"):
        world.admit()


def test_non_utf8_sql_is_rejected(world: World) -> None:
    world.sql[0].write_bytes(b"\xff\xfe")
    with pytest.raises(AdmissionError, match="not UTF-8"):
        world.admit()


def test_expired_policy_fails_at_the_exact_boundary(
    world: World, clock: list[datetime]
) -> None:
    clock[0] = datetime(2026, 11, 13, tzinfo=UTC)
    with pytest.raises(AdmissionError, match="expired"):
        world.admit()


def test_one_microsecond_before_expiry_is_admitted(
    world: World, clock: list[datetime]
) -> None:
    clock[0] = datetime(2026, 11, 13, tzinfo=UTC) - timedelta(microseconds=1)
    assert "13 ordinary" in world.admit()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("status", "prepared-inactive"),
        ("status", "active"),
        ("owner", "someone-else"),
        ("execution_scope", "populated-database"),
        ("expires_at", "2026-11-14T00:00:00Z"),
        ("expires_at", "2026-11-13"),
    ],
)
def test_policy_status_owner_scope_and_expiry_are_exact(
    world: World, key: str, value: str
) -> None:
    world.policy[key] = value
    with pytest.raises(AdmissionError):
        world.admit()


@pytest.mark.parametrize("activation_key", ["decision_date", "owner", "expires_at"])
def test_activation_record_must_match_the_owner_decision(
    world: World, activation_key: str
) -> None:
    world.policy["activation"][activation_key] = "changed"
    with pytest.raises(AdmissionError, match="activation record"):
        world.admit()


def test_activation_record_must_be_an_object(world: World) -> None:
    world.policy["activation"] = "approved"
    with pytest.raises(AdmissionError, match="activation record"):
        world.admit()


def test_policy_root_must_be_an_object_with_the_recorded_schema(world: World) -> None:
    world.policy["schema"] = "ue-historical148-policy-v2"
    with pytest.raises(AdmissionError, match="policy schema is invalid"):
        world.admit()


@pytest.mark.parametrize(
    ("key", "value"),
    [("version", "squawk 2.67.1"), ("binary_sha256", 7), ("args", "--exclude")],
)
def test_scanner_pin_must_be_well_formed(world: World, key: str, value: Any) -> None:
    world.policy["scanner"][key] = value
    with pytest.raises(AdmissionError, match="scanner pin is invalid"):
        world.admit()


def test_migration_source_pin_must_be_recorded(world: World) -> None:
    del world.policy["source_blobs"][admission.MIGRATION_PATH]
    with pytest.raises(AdmissionError, match="migration source pin is missing"):
        world.admit()


def test_migration_pin_must_be_the_exact_revision(world: World) -> None:
    world.policy["migration"]["revision"] = "other"
    with pytest.raises(AdmissionError, match="migration pin"):
        world.admit()


def test_migration_pin_must_not_carry_unchecked_fields(world: World) -> None:
    # A digest the admission never compares would be a silent, unenforced pin.
    world.policy["migration"]["sha256"] = "0" * 64
    with pytest.raises(AdmissionError, match="migration pin is invalid"):
        world.admit()


def test_producer_job_in_provenance_must_be_the_alembic_job(world: World) -> None:
    world.policy["provenance"]["producer_job"] = "other"
    with pytest.raises(AdmissionError, match="producer job"):
        world.admit()


def test_changed_migration_bytes_have_a_different_git_object_and_fail(
    world: World,
) -> None:
    changed = MIGRATION.read_bytes() + b"\n# changed\n"
    with pytest.raises(AdmissionError, match="unchanged historical revision"):
        world.admit(migration_blob=_git_object_id(changed))


@pytest.mark.parametrize(
    "blob",
    ["0" * 40, "", RECORDED["source_blobs"][admission.MIGRATION_PATH].upper()],
)
def test_migration_git_object_argument_must_be_the_recorded_blob(
    world: World, blob: str
) -> None:
    with pytest.raises(AdmissionError, match="unchanged historical revision"):
        world.admit(migration_blob=blob)


def test_scanner_binary_digest_must_match_the_policy(world: World) -> None:
    with pytest.raises(AdmissionError, match="binary digest"):
        world.admit(scanner_sha256="0" * 64)


def test_scanner_version_must_be_squawk_2_67_0(world: World) -> None:
    with pytest.raises(AdmissionError, match="version"):
        world.admit(scanner_version="squawk 2.67.1")


def test_scanner_arguments_must_be_the_recorded_raw_gate_arguments(
    world: World,
) -> None:
    with pytest.raises(AdmissionError, match="scanner arguments"):
        world.admit(scanner_args=world.excludes[:-1])


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("raw_exit", [0, 2, True])
def test_only_the_recorded_raw_failure_is_admitted(
    world: World, index: int, raw_exit: Any
) -> None:
    key = "ordinary" if index == 0 else "expanded"
    overrides: dict[str, Any] = {key: world.evidence(index, raw_exit=raw_exit)}
    with pytest.raises(AdmissionError, match="raw Squawk exit"):
        world.admit(**overrides)


@pytest.mark.parametrize("index", [0, 1])
def test_json_scan_must_repeat_the_recorded_failure_exit(
    world: World, index: int
) -> None:
    world.json_exit[index] = 0
    with pytest.raises(AdmissionError, match="JSON scan exit"):
        world.admit()


@pytest.mark.parametrize("index", [0, 1])
def test_scanner_diagnostics_on_stderr_fail_closed(world: World, index: int) -> None:
    world.write_stderr(index, b"warning: something\n")
    with pytest.raises(AdmissionError, match="stderr"):
        world.admit()


SCANNER_OUTPUT_DEFECTS: dict[str, tuple[bytes, str]] = {
    "truncated": (b"[", "malformed"),
    "invalid_utf8": (b"\xff", "malformed"),
    "nan": (b"[NaN]", "malformed"),
    "fraction": (b"[1.5]", "malformed"),
    "duplicate_key": (b'[{"file": "x", "file": "y"}]', "malformed"),
    "not_a_list": (b'{"file": "x"}', "not a list"),
    "not_an_object": (b"[1]", "not an object"),
    "empty": (b"", "exceeds its byte limit"),
    "oversized": (b" " * (admission.OUTPUT_LIMIT + 1), "exceeds its byte limit"),
}


@pytest.mark.parametrize("defect", sorted(SCANNER_OUTPUT_DEFECTS))
def test_malformed_or_oversized_scanner_output_fails(world: World, defect: str) -> None:
    payload, reason = SCANNER_OUTPUT_DEFECTS[defect]
    (world.evidence_dir / "scan-0.json").write_bytes(payload)
    with pytest.raises(AdmissionError, match=reason):
        world.admit()


@pytest.mark.parametrize(
    ("defect", "reason"),
    [
        ("empty", "empty or exceeds"),
        ("oversized", "empty or exceeds"),
        ("directory", "regular file"),
        ("missing", "regular file"),
        ("symlink", "symlink input is forbidden"),
    ],
)
def test_sql_inputs_must_be_bounded_regular_files(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
    reason: str,
) -> None:
    if defect == "empty":
        world.sql[0].write_bytes(b"")
    elif defect == "oversized":
        world.sql[0].write_bytes(b" " * (admission.SQL_LIMIT + 1))
    elif defect == "directory":
        world.sql = (tmp_path, world.sql[1])
    elif defect == "missing":
        world.sql = (tmp_path / "does-not-exist.sql", world.sql[1])
    else:
        target = world.sql[0]
        original = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda self: self == target or original(self),
        )
    with pytest.raises(AdmissionError, match=reason):
        world.admit()


def test_scanner_output_files_must_be_regular_files(
    world: World, tmp_path: Path
) -> None:
    with pytest.raises(AdmissionError, match="regular file"):
        world.admit(
            ordinary=ScenarioEvidence(
                sql_path=str(world.sql[0]),
                raw_exit=1,
                json_path=str(tmp_path),
                json_exit=1,
                stderr_path=str(world.evidence_dir / "scan-0.stderr"),
            )
        )


def test_policy_must_be_strict_bounded_json(world: World) -> None:
    valid = world.policy_bytes()
    bad_policies = [
        b"",
        b" " * (admission.POLICY_LIMIT + 1),
        b"\xff",
        valid[:-3],
        b'{"schema":"x",' + valid[1:],
        b'{"schema":NaN}',
        b'{"schema":1.5}',
        b"[]",
    ]
    for payload in bad_policies:
        with pytest.raises(AdmissionError):
            world.admit(payload)


def test_admission_uses_the_real_clock_not_a_caller_argument() -> None:
    parameters = inspect.signature(admission.admit).parameters
    assert "now" not in parameters
    assert "clock" not in parameters


def test_wrong_scenario_inventory_is_rejected(world: World) -> None:
    world.policy["scenarios"].pop()
    with pytest.raises(AdmissionError, match="scenario inventory"):
        world.admit()


def test_policy_inventory_count_cannot_be_reduced_to_match_live_output(
    world: World,
) -> None:
    world.policy["scenarios"][1]["findings"].pop()
    with pytest.raises(AdmissionError, match="inventory count is invalid"):
        world.admit()


def test_scanner_pins_are_compared_as_text_not_as_loose_values(world: World) -> None:
    with pytest.raises(AdmissionError, match="binary digest"):
        world.admit(scanner_sha256=SCANNER_SHA256.upper())


def _cli(world: World, *, excludes: bool = True) -> list[str]:
    rules: list[str] = []
    if excludes:
        for flag, rule in zip(world.excludes[::2], world.excludes[1::2], strict=True):
            assert flag == "--exclude"
            rules.extend(["--exclude", rule])
    arguments = [
        "--policy",
        str(POLICY),
        "--migration-blob",
        world.migration_blob,
        "--scanner-sha256",
        world.scanner_sha256,
        "--scanner-version",
        world.scanner_version,
        *rules,
    ]
    for prefix, index in (("ordinary", 0), ("expanded", 1)):
        evidence = world.evidence(index)
        arguments.extend(
            [
                f"--{prefix}-sql",
                evidence.sql_path,
                f"--{prefix}-raw-exit",
                str(evidence.raw_exit),
                f"--{prefix}-json",
                evidence.json_path,
                f"--{prefix}-json-exit",
                str(evidence.json_exit),
                f"--{prefix}-stderr",
                evidence.stderr_path,
            ]
        )
    return arguments


def test_cli_requires_the_alembic_producer_job(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GITHUB_JOB", raising=False)
    assert admission.main(_cli(world)) == 1
    assert "producer job is invalid" in capsys.readouterr().out


def test_cli_admits_the_exact_inventory_with_the_recorded_scanner_args(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GITHUB_JOB", "alembic-migrations")
    assert admission.main(_cli(world)) == 0
    assert "13 ordinary + 24 expanded" in capsys.readouterr().out


def test_cli_reports_a_rejection_and_exits_nonzero(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GITHUB_JOB", "alembic-migrations")
    world.scanner_sha256 = "0" * 64
    assert admission.main(_cli(world)) == 1
    assert "historical admission rejected: scanner binary digest" in (
        capsys.readouterr().out
    )


def test_cli_requires_the_migration_git_object_argument(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_JOB", "alembic-migrations")
    arguments = _cli(world)
    index = arguments.index("--migration-blob")
    del arguments[index : index + 2]
    with pytest.raises(SystemExit):
        admission.main(arguments)


def test_cli_rejects_a_wrong_migration_git_object(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GITHUB_JOB", "alembic-migrations")
    world.migration_blob = "0" * 40
    assert admission.main(_cli(world)) == 1
    assert (
        "historical admission rejected: migration source is not the unchanged "
        "historical revision" in capsys.readouterr().out
    )


def test_cli_without_recorded_scanner_arguments_is_rejected(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GITHUB_JOB", "alembic-migrations")
    assert admission.main(_cli(world, excludes=False)) == 1
    assert "scanner arguments" in capsys.readouterr().out


def test_cli_rejects_non_integer_raw_exit_by_argument_parsing(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_JOB", "alembic-migrations")
    arguments = _cli(world)
    arguments[arguments.index("--ordinary-raw-exit") + 1] = "one"
    with pytest.raises(SystemExit):
        admission.main(arguments)


def test_module_entry_point_exits_with_the_cli_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["historical148_squawk_admission", "--help"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(admission.__file__, run_name="__main__")
    assert exit_info.value.code == 0
