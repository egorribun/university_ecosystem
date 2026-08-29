from __future__ import annotations

import argparse
import json
import os
import runpy
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

import scripts.quality.select_coverage_retry_artifacts_cli as retry_cli
from scripts.quality.coverage_provenance import write_metadata
from scripts.quality.coverage_retry_context import (
    RetryContextError,
    build_retry_provenance,
)
from scripts.quality.select_coverage_artifacts import (
    CoverageArtifactSlot,
    CoverageSelectionError,
)

GIT_EXECUTABLE = shutil.which("git")
WORKFLOW_SHA = "b" * 40
WORKFLOW_REF = "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"


def _git_head(repository_root: Path) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603  # test-only fixed argv invokes trusted Git.
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
    ).strip()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _layout(*, reports: list[object] | None = None) -> dict[str, object]:
    selected_reports = (
        reports
        if reports is not None
        else [
            {
                "component": "python",
                "format": "cobertura-xml",
                "path": "coverage.xml",
            }
        ]
    )
    return {
        "schema_version": 1,
        "slots": [
            {
                "logical_artifact": "coverage-evidence",
                "producer_job": "coverage-policy-gate",
                "metadata_path": "artifacts/coverage/provenance/aggregate.json",
                "reports": selected_reports,
            }
        ],
    }


def _contract(*, reports: list[object] | None = None) -> dict[str, object]:
    selected_reports = (
        reports
        if reports is not None
        else [
            {
                "component": "python",
                "format": "cobertura-xml",
                "path": "coverage.xml",
            }
        ]
    )
    return {"coverage_reports": selected_reports}


def _first_slot() -> dict[str, object]:
    slots = _layout()["slots"]
    assert isinstance(slots, list)
    first = slots[0]
    assert isinstance(first, dict)
    return first


@pytest.fixture
def retry_repository(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    _write_json(
        repository_root / retry_cli.QUALITY_CONTRACT_PATH,
        _contract(),
    )
    _write_json(
        repository_root / retry_cli.COVERAGE_RETRY_LAYOUT_PATH,
        _layout(),
    )
    workflow = repository_root / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: quality\n", encoding="utf-8")
    subprocess.run(  # noqa: S603  # test-only fixed argv invokes trusted Git.
        [GIT_EXECUTABLE, "init", "-q"], cwd=repository_root, check=True
    )
    subprocess.run(  # noqa: S603  # test-only fixed argv invokes trusted Git.
        [
            GIT_EXECUTABLE,
            "-c",
            "user.name=Quality Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        cwd=repository_root,
        check=True,
    )
    return repository_root


def _write_candidate(repository_root: Path, *, attempt: str = "2") -> Path:
    candidate = repository_root / f"coverage-evidence-attempt-{attempt}"
    candidate.mkdir()
    report = candidate / "coverage.xml"
    report.write_bytes(b"coverage evidence\n")
    metadata = candidate / "artifacts/coverage/provenance/aggregate.json"
    write_metadata(
        repository_root=repository_root,
        output_path=metadata,
        reports=[
            (
                "python",
                "cobertura-xml",
                "coverage-evidence-attempt-2/coverage.xml",
                "coverage.xml",
            )
        ],
        tool_versions={"coverage.py": "7.10.0", "python": "3.14.0"},
        expected_sha=_git_head(repository_root),
        identity_provider="github-actions",
        repository="example/university-ecosystem",
        workflow_ref=WORKFLOW_REF,
        workflow_sha=WORKFLOW_SHA,
        run_id="123456789",
        run_attempt=attempt,
        event="pull_request",
        job="coverage-policy-gate",
        artifact="coverage-evidence",
        collected_at="2026-08-29T12:34:56Z",
        retry_provenance=build_retry_provenance(
            repository_root=repository_root,
            config_inputs=(".github/workflows/ci.yml",),
            policy_inputs=(
                retry_cli.QUALITY_CONTRACT_PATH,
                retry_cli.COVERAGE_RETRY_LAYOUT_PATH,
            ),
            repository="example/university-ecosystem",
            run_id="123456789",
            run_attempt=attempt,
            workflow_ref=WORKFLOW_REF,
            workflow_sha=WORKFLOW_SHA,
            event="pull_request",
            artifact="coverage-evidence",
        ),
    )
    return candidate


def _argv(
    repository_root: Path,
    *candidate_roots: Path,
    destination_root: str = "artifacts/coverage/retry-selected",
) -> list[str]:
    result = [
        "--repository-root",
        str(repository_root),
        "--destination-root",
        destination_root,
        "--repository",
        "example/university-ecosystem",
        "--run-id",
        "123456789",
        "--run-attempt",
        "3",
        "--workflow-ref",
        WORKFLOW_REF,
        "--workflow-sha",
        WORKFLOW_SHA,
        "--event",
        "pull_request",
        "--consumer-job",
        "coverage-policy-gate",
        "--config-input",
        ".github/workflows/ci.yml",
    ]
    for candidate in candidate_roots:
        result.extend(("--candidate-root", str(candidate.relative_to(repository_root))))
    return result


def test_select_builds_current_context_selects_evidence_and_writes_receipt(
    retry_repository: Path,
) -> None:
    candidate = _write_candidate(retry_repository)

    summary = retry_cli._select(
        retry_cli._arguments(_argv(retry_repository, candidate))
    )

    assert summary == {
        "consumer_job": "coverage-policy-gate",
        "layout": retry_cli.COVERAGE_RETRY_LAYOUT_PATH.as_posix(),
        "receipt_path": str(
            retry_repository
            / "artifacts/coverage/retry-selected/selection-receipt.json"
        ),
        "selections": [
            {
                "logical_artifact": "coverage-evidence",
                "physical_artifact": "coverage-evidence-attempt-2",
                "producer_attempt": 2,
            }
        ],
    }
    receipt = json.loads(
        (
            retry_repository
            / "artifacts/coverage/retry-selected/selection-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["consumer"]["retry_context"]["source_sha"] == _git_head(
        retry_repository
    )


def test_checked_in_layout_exactly_matches_the_quality_contract() -> None:
    repository_root = Path(__file__).parents[1]

    slots = retry_cli.load_coverage_retry_layout(repository_root)

    assert len(slots) == 1
    assert slots[0].logical_artifact == "coverage-evidence"
    assert len(slots[0].reports) == 16


def _run_entrypoint(
    entrypoint: Sequence[str], argv: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # test-only fixed Python/in-repository entrypoint.
        [*entrypoint, *argv],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        check=False,
        text=True,
    )


@pytest.mark.parametrize(
    ("entrypoint", "destination_root"),
    [
        (
            (sys.executable, str(Path(retry_cli.__file__).resolve())),
            "artifacts/coverage/direct-selected",
        ),
        (
            (
                sys.executable,
                "-m",
                "scripts.quality.select_coverage_retry_artifacts_cli",
            ),
            "artifacts/coverage/module-selected",
        ),
    ],
)
def test_direct_and_module_entrypoints_select_full_evidence(
    retry_repository: Path, entrypoint: tuple[str, ...], destination_root: str
) -> None:
    candidate = _write_candidate(retry_repository)
    result = _run_entrypoint(
        entrypoint,
        _argv(
            retry_repository,
            candidate,
            destination_root=destination_root,
        ),
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["consumer_job"] == "coverage-policy-gate"
    assert result.stderr == ""
    assert (retry_repository / destination_root / "selection-receipt.json").is_file()


@pytest.mark.parametrize(
    ("layout", "contract", "message"),
    [
        ({"schema_version": 1}, _contract(), "missing fields: slots"),
        (
            {**_layout(), "unexpected": True},
            _contract(),
            "unexpected fields: unexpected",
        ),
        ({**_layout(), "schema_version": True}, _contract(), "schema_version"),
        ({**_layout(), "schema_version": 1.0}, _contract(), "schema_version"),
        ({**_layout(), "slots": []}, _contract(), "at least one slot"),
        ({**_layout(), "slots": ["not-an-object"]}, _contract(), "must be an object"),
        (
            {
                **_layout(),
                "slots": [
                    {
                        "logical_artifact": "coverage-evidence",
                        "producer_job": "coverage-policy-gate",
                        "metadata_path": "metadata.json",
                    }
                ],
            },
            _contract(),
            "missing fields: reports",
        ),
        (
            _layout(reports=[]),
            _contract(),
            "must be a non-empty array",
        ),
        (_layout(reports=["not-an-object"]), _contract(), "must be an object"),
        (
            _layout(
                reports=[
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": "other.xml",
                    }
                ]
            ),
            _contract(),
            "does not exactly match",
        ),
        (_layout(), {"coverage_reports": []}, "must be a non-empty array"),
        (_layout(), {}, "missing fields: coverage_reports"),
        (
            {
                **_layout(),
                "slots": [
                    {
                        **_first_slot(),
                        "logical_artifact": "",
                    }
                ],
            },
            _contract(),
            "must be a non-empty string",
        ),
        (
            {
                **_layout(),
                "slots": [
                    {
                        **_first_slot(),
                        "producer_job": "bad\njob",
                    }
                ],
            },
            _contract(),
            "contains forbidden control characters",
        ),
        (
            _layout(
                reports=[
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": "coverage.xml",
                    },
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": "coverage.xml",
                    },
                ]
            ),
            _contract(),
            "duplicate report identities",
        ),
    ],
)
def test_layout_parser_fails_closed_for_wrong_or_unbound_layouts(
    retry_repository: Path,
    layout: dict[str, object],
    contract: dict[str, object],
    message: str,
) -> None:
    _write_json(retry_repository / retry_cli.COVERAGE_RETRY_LAYOUT_PATH, layout)
    _write_json(retry_repository / retry_cli.QUALITY_CONTRACT_PATH, contract)

    with pytest.raises(retry_cli.CoverageRetryLayoutError, match=message):
        retry_cli.load_coverage_retry_layout(retry_repository)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            '{"schema_version": 1, "schema_version": 1, "slots": []}',
            "duplicate JSON key",
        ),
        ("{not-json}", "unable to parse"),
        ('{"schema_version": NaN, "slots": []}', "invalid JSON constant"),
    ],
)
def test_layout_parser_rejects_noncanonical_json(
    retry_repository: Path, payload: str, message: str
) -> None:
    layout_path = retry_repository / retry_cli.COVERAGE_RETRY_LAYOUT_PATH
    layout_path.write_text(payload, encoding="utf-8")

    with pytest.raises(retry_cli.CoverageRetryLayoutError, match=message):
        retry_cli.load_coverage_retry_layout(retry_repository)


def test_select_rechecks_context_after_layout_read(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _write_candidate(retry_repository)
    original_load = retry_cli.load_coverage_retry_layout

    def load_then_mutate(repository_root: Path) -> tuple[CoverageArtifactSlot, ...]:
        slots = original_load(repository_root)
        _write_json(
            repository_root / retry_cli.COVERAGE_RETRY_LAYOUT_PATH,
            _layout(
                reports=[
                    {
                        "component": "python",
                        "format": "cobertura-xml",
                        "path": "changed-after-read.xml",
                    }
                ]
            ),
        )
        return slots

    monkeypatch.setattr(retry_cli, "load_coverage_retry_layout", load_then_mutate)

    with pytest.raises(RetryContextError, match="policy_digest"):
        retry_cli._select(retry_cli._arguments(_argv(retry_repository, candidate)))
    assert not (retry_repository / "artifacts/coverage/retry-selected").exists()


def test_main_emits_json_and_reports_fail_closed_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = argparse.Namespace()
    monkeypatch.setattr(retry_cli, "_arguments", lambda _: arguments)
    monkeypatch.setattr(retry_cli, "_select", lambda _: {"selected": True})

    assert retry_cli.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"selected": True}

    monkeypatch.setattr(
        retry_cli,
        "_select",
        lambda _: (_ for _ in ()).throw(retry_cli.CoverageRetryLayoutError("bad")),
    )

    assert retry_cli.main([]) == 1
    assert capsys.readouterr().err == "error: bad\n"


def test_repository_path_resolves_safe_relative_paths_inside_the_repository(
    retry_repository: Path,
) -> None:
    assert (
        retry_cli._repository_path(retry_repository, Path("relative"))
        == (retry_repository / "relative").resolve()
    )


@pytest.mark.parametrize(
    ("path", "message"),
    [
        (Path("../outside"), "must not contain parent traversal"),
        (Path("../../outside"), "must not contain parent traversal"),
    ],
)
def test_repository_path_rejects_relative_traversal_outside_repository(
    retry_repository: Path, path: Path, message: str
) -> None:
    with pytest.raises(retry_cli.CoverageRetryLayoutError, match=message):
        retry_cli._repository_path(retry_repository, path)


def test_repository_path_rejects_parent_traversal_that_stays_inside_repository(
    retry_repository: Path,
) -> None:
    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must not contain parent traversal",
    ):
        retry_cli._repository_path(retry_repository, Path("nested/../inside"))


def _directory_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")


def test_repository_path_rejects_a_resolved_link_escape(
    retry_repository: Path,
) -> None:
    outside = retry_repository.parent / "outside"
    outside.mkdir()
    link = retry_repository / "outside-link"
    _directory_symlink(link, outside)

    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must not traverse a symlink or junction",
    ):
        retry_cli._repository_path(retry_repository, link.relative_to(retry_repository))


def test_repository_path_rejects_a_resolved_escape_after_link_checks(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lexical_repository_root = Path(os.path.abspath(retry_repository))
    escaped = retry_repository.parent / "escaped"
    original_resolve = Path.resolve

    def resolve(path: Path, strict: bool = False) -> Path:
        if path == lexical_repository_root / "candidate":
            return escaped
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)

    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must resolve inside the repository root",
    ):
        retry_cli._repository_path(retry_repository, Path("candidate"))


def test_repository_path_rejects_a_symlink_to_an_internal_candidate(
    retry_repository: Path,
) -> None:
    candidate = _write_candidate(retry_repository)
    link = retry_repository / "candidate-link"
    _directory_symlink(link, candidate)

    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must not traverse a symlink or junction",
    ):
        retry_cli._repository_path(retry_repository, link.relative_to(retry_repository))


def test_repository_path_rejects_a_symlinked_destination_component(
    retry_repository: Path,
) -> None:
    target = retry_repository / "safe-target"
    target.mkdir()
    artifacts = retry_repository / "artifacts"
    _directory_symlink(artifacts, target)

    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must not traverse a symlink or junction",
    ):
        retry_cli._repository_path(retry_repository, Path("artifacts/selected"))


def test_repository_path_rejects_a_symlinked_repository_root(
    retry_repository: Path,
) -> None:
    repository_link = retry_repository.parent / "repository-link"
    _directory_symlink(repository_link, retry_repository)

    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must not traverse a symlink or junction",
    ):
        retry_cli._repository_path(repository_link, Path("."))


def test_repository_path_rejects_absolute_artifact_roots(
    retry_repository: Path,
) -> None:
    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must be repository-relative",
    ):
        retry_cli._repository_path(retry_repository, retry_repository / "absolute")


def test_repository_path_rejects_a_windows_drive_relative_artifact_root(
    retry_repository: Path,
) -> None:
    with pytest.raises(
        retry_cli.CoverageRetryLayoutError,
        match="must be repository-relative",
    ):
        retry_cli._repository_path(retry_repository, Path("C:relative"))


def test_repository_path_accepts_the_repository_relative_root(
    retry_repository: Path,
) -> None:
    assert retry_cli._repository_path(retry_repository, Path(".")) == (
        retry_repository.resolve()
    )


def test_main_reports_selector_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(retry_cli, "_arguments", lambda _: argparse.Namespace())
    monkeypatch.setattr(
        retry_cli,
        "_select",
        lambda _: (_ for _ in ()).throw(CoverageSelectionError("bad slot")),
    )

    assert retry_cli.main([]) == 1
    assert capsys.readouterr().err == "error: bad slot\n"


def test_direct_file_entrypoint_delegates_to_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", [str(Path(retry_cli.__file__)), "--help"])

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(retry_cli.__file__)), run_name="__main__")

    assert raised.value.code == 0
    assert "Fail-closed CLI adapter" in capsys.readouterr().out
