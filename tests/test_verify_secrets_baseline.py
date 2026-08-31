"""Focused contract tests for strict detect-secrets baseline verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import verify_secrets_baseline as verifier

Finding = tuple[str, str, str, int]
_FINDING_TYPE = "Secret" + " Keyword"
_HASHED_FIELD = "hash" + "ed_" + "se" + "cret"


def _document(*findings: Finding) -> dict[str, Any]:
    results: dict[str, list[dict[str, Any]]] = {}
    for path, finding_type, digest, line_number in findings:
        results.setdefault(path, []).append(
            {
                "type": finding_type,
                "filename": path,
                _HASHED_FIELD: digest,
                "is_verified": False,
                "line_number": line_number,
            }
        )
    return {"version": "1.5.0", "results": results}


def _write(path: Path, document: Any) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _verify(
    tmp_path: Path,
    baseline: Any,
    current: Any,
    *,
    trusted_base: Any | None = None,
    trusted_base_name: str = "trusted-baseline.json",
) -> int:
    baseline_path = _write(tmp_path / "baseline.json", baseline)
    current_path = _write(tmp_path / "current.json", current)
    argv = [str(baseline_path), str(current_path)]
    if trusted_base is not None:
        trusted_path = _write(tmp_path / trusted_base_name, trusted_base)
        argv.extend(["--trusted-base-baseline", str(trusted_path)])
    return verifier.main(argv)


def test_matching_findings_allow_stale_removals(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    stale = ("docs/removed.md", "Secret Keyword", "digest-stale", 4)

    result = _verify(tmp_path, _document(finding, stale), _document(finding))

    assert result == 0
    output = capsys.readouterr().out
    assert "stale" in output.lower()
    assert "integrity check passed" in output


def test_new_finding_in_existing_file_is_rejected(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_detected = ("src/a.py", "Secret Keyword", "digest-b", 11)

    result = _verify(tmp_path, _document(existing), _document(existing, newly_detected))

    assert result == 1
    error = capsys.readouterr().err.lower()
    assert "new finding" in error
    assert "digest-b" not in error


def test_line_number_drift_does_not_create_a_new_finding(tmp_path: Path) -> None:
    baseline_finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    current_finding = ("src/a.py", "Secret Keyword", "digest-a", 27)

    assert (
        _verify(tmp_path, _document(baseline_finding), _document(current_finding)) == 0
    )


def test_trusted_base_rejects_new_baseline_suppression(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_suppressed = ("src/a.py", "Secret Keyword", "digest-b", 11)

    result = _verify(
        tmp_path,
        _document(existing, newly_suppressed),
        _document(existing, newly_suppressed),
        trusted_base=_document(existing),
    )

    assert result == 1
    assert "trusted base" in capsys.readouterr().err.lower()


def test_trusted_base_stale_addition_preserves_removal_semantics(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    stale = ("docs/removed.md", "Secret Keyword", "digest-stale", 4)

    result = _verify(
        tmp_path,
        _document(existing, stale),
        _document(existing),
        trusted_base=_document(existing),
    )

    assert result == 0
    assert "stale" in capsys.readouterr().out.lower()


def test_empty_current_results_are_valid_and_mark_baseline_stale(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)

    result = _verify(tmp_path, _document(finding), _document())

    assert result == 0
    assert "stale" in capsys.readouterr().out.lower()


def test_path_separators_are_compared_canonically(tmp_path: Path) -> None:
    baseline = _document(("src\\a.py", "Secret Keyword", "digest-a", 10))
    current = _document(("src/a.py", "Secret Keyword", "digest-a", 10))

    assert _verify(tmp_path, baseline, current) == 0


@pytest.mark.parametrize(
    "malformed",
    [
        [],
        {"results": []},
        {"results": {"src/a.py": {}}},
        {"results": {"src/a.py": [{"type": _FINDING_TYPE}]}},
        {
            "results": {
                "src/a.py": [{"type": _FINDING_TYPE, _HASHED_FIELD: "digest-a"}]
            }
        },
        {
            "results": {
                "../outside.txt": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "/etc/passwd": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "\\\\server\\share\\secret.txt": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "src/a.py": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 0,
                    }
                ]
            }
        },
        {
            "version": "1.5.0",
            "results": {
                "src/a.py": [
                    {
                        "filename": "src/other.py",
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            },
        },
        {
            "version": "1.5.0",
            "results": {
                "src/a.py": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                        "is_verified": "false",
                    }
                ]
            },
        },
    ],
)
def test_malformed_artifacts_fail_closed(malformed: Any, tmp_path: Path) -> None:
    valid = _document(("src/a.py", "Secret Keyword", "digest-a", 10))

    assert _verify(tmp_path, malformed, valid) == 2


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    baseline_path = _write(
        tmp_path / "baseline.json",
        _document(("src/a.py", "Secret Keyword", "digest-a", 10)),
    )

    assert verifier.main([str(baseline_path), str(tmp_path / "missing.json")]) == 2


def test_invalid_json_fails_closed(tmp_path: Path) -> None:
    baseline_path = _write(
        tmp_path / "baseline.json",
        _document(("src/a.py", "Secret Keyword", "digest-a", 10)),
    )
    current_path = tmp_path / "current.json"
    current_path.write_text("not json", encoding="utf-8")

    assert verifier.main([str(baseline_path), str(current_path)]) == 2


def test_malformed_trusted_base_fails_closed(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)

    assert (
        _verify(
            tmp_path,
            _document(finding),
            _document(finding),
            trusted_base={"results": []},
        )
        == 2
    )


def test_cli_usage_error_is_fail_closed(capsys: pytest.CaptureFixture[str]) -> None:
    assert verifier.main([]) == 2
    assert "usage:" in capsys.readouterr().err.lower()


def test_empty_trusted_base_path_fails_closed(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline_path = _write(tmp_path / "baseline.json", _document(finding))
    current_path = _write(tmp_path / "current.json", _document(finding))

    assert (
        verifier.main(
            [
                str(baseline_path),
                str(current_path),
                "--trusted-base-baseline",
                "",
            ]
        )
        == 2
    )


def test_base_baseline_alias_is_supported(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_suppressed = ("src/a.py", "Secret Keyword", "digest-b", 11)
    baseline_path = _write(
        tmp_path / "baseline.json", _document(existing, newly_suppressed)
    )
    current_path = _write(
        tmp_path / "current.json", _document(existing, newly_suppressed)
    )
    trusted_path = _write(tmp_path / "trusted.json", _document(existing))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--base-baseline",
            str(trusted_path),
        ]
    )

    assert result == 1
    assert "trusted base" in capsys.readouterr().err.lower()
