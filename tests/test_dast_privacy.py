"""Privacy contracts for DAST target validation and report publication."""

from __future__ import annotations

import json
import os
import runpy
import stat
import sys
from pathlib import Path

import pytest

from scripts.quality import dast_privacy


@pytest.mark.parametrize(
    "target",
    [
        "https://stage.example.test",
        "http://stage.example.test:8080/api/v1",
        "https://[::1]:443/staging",
    ],
)
def test_target_validation_preserves_safe_origin_and_path(target: str) -> None:
    assert dast_privacy.target_is_safe(target)


@pytest.mark.parametrize(
    "target",
    [
        "",
        "stage.example.test",
        "file:///etc/hosts",
        "https://" + "demo" + ":" + "example" + "@stage.example.test/api",
        "https://" + "demo" + "@stage.example.test/api",
        "https://stage.example.test/api?q=1",
        "https://stage.example.test/api?",
        "https://stage.example.test/api#section",
        "https://stage.example.test/api#",
        "https://stage.example.test:invalid/api",
        "https://stage.example.test:65536/api",
        "https://stage.example.test:0/api",
        "https://stage%2eexample.test/api",
        "https://stagé.example.test/api",
        "https://stage.example.test/private%2Darea",
        "https://stage.example.test/a/../private-area",
        "https://stage.example.test/a/./private-area",
        "https://stage.example.test/a//private-area",
        "https://stage.example.test/nonascii-é",
        "https://stage.example.test/a\x7fb",
        "https://stage.example.test/a\x01b",
        "https://stage.example.test/with space",
        "https://stage.example.test/with\nnewline",
        "https://stage.example.test\\@elsewhere.test/",
    ],
)
def test_target_validation_rejects_credentials_and_ambiguous_urls(target: str) -> None:
    assert not dast_privacy.target_is_safe(target)


def test_target_validation_cli_does_not_print_rejected_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = "https://stage.example.test/path?q=private"
    monkeypatch.setenv("TARGET_URL", target)

    assert dast_privacy.main(["validate-target"]) == 1
    captured = capsys.readouterr()
    assert target not in captured.out + captured.err


def test_target_validation_cli_accepts_safe_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TARGET_URL", "https://stage.example.test/api/v1")

    assert dast_privacy.main(["validate-target"]) == 0
    output = capsys.readouterr().out
    assert "::add-mask::https://stage.example.test/api/v1" in output
    assert "::add-mask::stage.example.test" in output
    assert "::add-mask::api" in output


def _stand_status(base_url: str) -> str:
    """Mirror the lines printed by scripts/live_stand.py status."""
    return (
        "+ docker compose ps\n"
        "LIVE_BASE_URL=" + base_url + "\n"
        "LIVE_MAILPIT_URL=http://127.0.0.1:18025\n"
    )


@pytest.mark.parametrize(
    "base_url",
    ["http://localhost:80", "http://localhost:20000", "http://localhost:45000"],
)
def test_prepare_target_hands_off_only_the_owned_stand_base_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    base_url: str,
) -> None:
    status = tmp_path / "stand-status.txt"
    status.write_text(_stand_status(base_url), encoding="utf-8")
    handoff = tmp_path / "target.txt"
    monkeypatch.delenv("TARGET_URL", raising=False)

    assert (
        dast_privacy.main(
            ["prepare-target", "--status-in", str(status), "--output", str(handoff)]
        )
        == 0
    )
    assert handoff.read_text(encoding="utf-8") == base_url
    if os.name != "nt":
        assert stat.S_IMODE(handoff.stat().st_mode) == 0o600
    assert f"::add-mask::{base_url}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "status_text",
    [
        "",
        "LIVE_MAILPIT_URL=http://127.0.0.1:18025\n",
        "LIVE_BASE_URL=http://localhost:20000\nLIVE_BASE_URL=http://localhost:20001\n",
        "LIVE_BASE_URL=https://localhost:20000\n",
        "LIVE_BASE_URL=http://127.0.0.1:20000\n",
        "LIVE_BASE_URL=http://localhost:20000/api/v1\n",
        "LIVE_BASE_URL=http://localhost:0\n",
        "LIVE_BASE_URL=http://localhost:70000\n",
        "LIVE_BASE_URL=http://private.test:20000\n",
        "  LIVE_BASE_URL=http://localhost:20000\n",
        "LIVE_BASE_URL=http://localhost:20000?token=private\n",
    ],
)
def test_prepare_target_rejects_ambiguous_or_non_loopback_stand_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status_text: str,
) -> None:
    status = tmp_path / "stand-status.txt"
    status.write_text(status_text, encoding="utf-8")
    handoff = tmp_path / "target.txt"
    monkeypatch.delenv("TARGET_URL", raising=False)

    assert (
        dast_privacy.main(
            ["prepare-target", "--status-in", str(status), "--output", str(handoff)]
        )
        == 1
    )
    assert not handoff.exists()
    output = capsys.readouterr()
    assert "private.test" not in output.out + output.err
    assert "token=private" not in output.out + output.err


def test_prepare_target_never_overwrites_an_existing_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    status = tmp_path / "stand-status.txt"
    status.write_text(_stand_status("http://localhost:20000"), encoding="utf-8")
    handoff = tmp_path / "target.txt"
    handoff.write_text("existing", encoding="utf-8")

    assert (
        dast_privacy.main(
            ["prepare-target", "--status-in", str(status), "--output", str(handoff)]
        )
        == 1
    )
    assert handoff.read_text(encoding="utf-8") == "existing"
    assert "localhost:20000" not in capsys.readouterr().err


@pytest.mark.parametrize("unlink_fails", [False, True])
def test_prepare_target_fails_closed_on_handoff_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    unlink_fails: bool,
) -> None:
    status = tmp_path / "stand-status.txt"
    status.write_text(_stand_status("http://localhost:20000"), encoding="utf-8")
    handoff = tmp_path / "target.txt"
    original_fdopen = os.fdopen

    class BrokenWrite:
        def __init__(self, descriptor: int, *args: object, **kwargs: object) -> None:
            self.handle = original_fdopen(descriptor, *args, **kwargs)

        def __enter__(self) -> BrokenWrite:
            return self

        def write(self, _value: str) -> None:
            raise OSError("injected write failure")

        def __exit__(self, *_args: object) -> None:
            self.handle.close()

    monkeypatch.setattr(dast_privacy.os, "fdopen", BrokenWrite)
    if unlink_fails:

        def fail_unlink(_path: Path, *, missing_ok: bool = False) -> None:
            raise OSError("injected unlink failure")

        monkeypatch.setattr(Path, "unlink", fail_unlink)

    assert (
        dast_privacy.main(
            ["prepare-target", "--status-in", str(status), "--output", str(handoff)]
        )
        == 1
    )
    assert handoff.exists() is unlink_fails
    if unlink_fails:
        assert handoff.read_bytes() == b""
    assert "localhost:20000" not in capsys.readouterr().err


def test_target_file_is_used_without_putting_the_target_in_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target_file = tmp_path / "target.txt"
    target_file.write_text("https://manual.example.test/private", encoding="utf-8")
    monkeypatch.setenv("DAST_TARGET_FILE", str(target_file))
    monkeypatch.delenv("TARGET_URL", raising=False)

    assert dast_privacy.main(["validate-target"]) == 0
    assert "::add-mask::https://manual.example.test/private" in capsys.readouterr().out


def test_missing_target_file_does_not_fall_back_to_a_different_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DAST_TARGET_FILE", str(tmp_path / "missing.txt"))
    monkeypatch.setenv("TARGET_URL", "https://fallback.example.test")

    assert dast_privacy.main(["validate-target"]) == 1
    assert "fallback.example.test" not in capsys.readouterr().out


def test_encoded_target_path_is_rejected_before_any_mask_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TARGET_URL", "https://stage.example.test/api%2Fv1")

    assert dast_privacy.main(["validate-target"]) == 1
    assert capsys.readouterr().out == ""


def _native_reports() -> tuple[str, list[dict[str, object]], dict[str, object]]:
    target = "https://stage.example.test/private-area"
    finding: dict[str, object] = {
        "template-id": "CVE-2025-12345",
        "info": {"severity": "high", "name": "Example"},
        "type": "http",
        "host": target,
        "matched-at": f"{target}/endpoint?q=private-value",
        "request": "request-with-private-value",
        "response": "response-with-private-value",
        "extracted-results": ["private-value"],
        "curl-command": f"curl {target}",
    }
    report: dict[str, object] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Nuclei",
                        "semanticVersion": "v3.11.1",
                        "rules": [
                            {
                                "id": "CVE-2025-12345",
                                "name": "Example",
                                "properties": {
                                    "tags": ["security"],
                                    "security-severity": "8",
                                },
                            }
                        ],
                    }
                },
                "invocations": [{"arguments": ["-u", target]}],
                "results": [
                    {
                        "ruleId": "CVE-2025-12345",
                        "ruleIndex": 0,
                        "level": "error",
                        "kind": "open",
                        "message": {"text": f"Found at {target}"},
                        "locations": [
                            {
                                "message": {"text": target},
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": f"/{target}/endpoint?q=private-value",
                                        "description": {"text": target},
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
    return target, [finding], report


def test_published_findings_remove_target_and_raw_evidence() -> None:
    target, findings, _ = _native_reports()

    result = dast_privacy.sanitize_findings(findings, target)

    assert result == [{"template-id": "CVE-2025-12345", "info": {"severity": "high"}}]
    rendered = json.dumps(result)
    assert target not in rendered
    assert "private-value" not in rendered


def test_published_sarif_removes_invocation_and_target_but_keeps_findings() -> None:
    target, _, report = _native_reports()

    result = dast_privacy.sanitize_sarif(report, target)
    rendered = json.dumps(result)

    assert target not in rendered
    assert "stage.example.test" not in rendered
    assert "private-area" not in rendered
    assert "private-value" not in rendered
    assert "invocations" not in rendered
    run = result["runs"][0]
    assert run["tool"]["driver"]["name"] == "Nuclei"
    assert run["tool"]["driver"]["semanticVersion"] == "3.11.1"
    assert run["tool"]["driver"]["rules"][0]["id"] == "CVE-2025-12345"
    assert run["tool"]["driver"]["rules"][0]["shortDescription"] == {
        "text": "CVE-2025-12345"
    }
    assert run["tool"]["driver"]["rules"][0]["properties"]["security-severity"] == "8"
    assert len(run["results"]) == 1
    assert run["results"][0]["ruleId"] == "CVE-2025-12345"
    assert run["results"][0]["level"] == "error"


def test_sanitizer_publishes_only_filtered_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, findings, report = _native_reports()
    monkeypatch.setenv("TARGET_URL", target)
    native_json = tmp_path / "private.json"
    native_sarif = tmp_path / "private.sarif"
    public_json = tmp_path / "published.json"
    public_sarif = tmp_path / "published.sarif"
    native_json.write_text(json.dumps(findings), encoding="utf-8")
    native_sarif.write_text(json.dumps(report), encoding="utf-8")

    assert (
        dast_privacy.main(
            [
                "sanitize",
                "--json-in",
                str(native_json),
                "--sarif-in",
                str(native_sarif),
                "--json-out",
                str(public_json),
                "--sarif-out",
                str(public_sarif),
            ]
        )
        == 0
    )
    for path in (public_json, public_sarif):
        rendered = path.read_text(encoding="utf-8")
        assert "stage.example.test" not in rendered
        assert "private-value" not in rendered
        assert "private-area" not in rendered
    assert "invocations" not in public_sarif.read_text(encoding="utf-8")


def test_clean_json_is_retained_without_fabricating_a_sarif_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGET_URL", "https://stage.example.test")
    native_json = tmp_path / "private.json"
    native_json.write_text("[]", encoding="utf-8")
    public_json = tmp_path / "published.json"
    public_sarif = tmp_path / "published.sarif"

    assert (
        dast_privacy.main(
            [
                "sanitize",
                "--json-in",
                str(native_json),
                "--sarif-in",
                str(tmp_path / "absent.sarif"),
                "--json-out",
                str(public_json),
                "--sarif-out",
                str(public_sarif),
            ]
        )
        == 0
    )
    assert json.loads(public_json.read_text(encoding="utf-8")) == []
    assert not public_sarif.exists()


def test_findings_without_sarif_fail_but_keep_the_filtered_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, findings, _ = _native_reports()
    monkeypatch.setenv("TARGET_URL", target)
    native_json = tmp_path / "private.json"
    native_json.write_text(json.dumps(findings), encoding="utf-8")
    public_json = tmp_path / "published.json"

    assert (
        dast_privacy.main(
            [
                "sanitize",
                "--json-in",
                str(native_json),
                "--sarif-in",
                str(tmp_path / "absent.sarif"),
                "--json-out",
                str(public_json),
                "--sarif-out",
                str(tmp_path / "published.sarif"),
            ]
        )
        == 1
    )
    assert json.loads(public_json.read_text(encoding="utf-8")) == [
        {"template-id": "CVE-2025-12345", "info": {"severity": "high"}}
    ]


@pytest.mark.parametrize("change", ["missing-finding", "level", "score"])
def test_inconsistent_reports_never_publish_sarif(tmp_path: Path, change: str) -> None:
    target, findings, report = _native_reports()
    run = report["runs"][0]
    if change == "missing-finding":
        findings.append(
            {"template-id": "another-template", "info": {"severity": "low"}}
        )
    elif change == "level":
        run["results"][0]["level"] = "note"
    else:
        run["tool"]["driver"]["rules"][0]["properties"]["security-severity"] = "2"
    native_json = tmp_path / "private.json"
    native_sarif = tmp_path / "private.sarif"
    native_json.write_text(json.dumps(findings), encoding="utf-8")
    native_sarif.write_text(json.dumps(report), encoding="utf-8")
    published_sarif = tmp_path / "published.sarif"

    assert (
        dast_privacy.sanitize_files(
            target,
            native_json,
            native_sarif,
            tmp_path / "published.json",
            published_sarif,
        )
        == 1
    )
    assert not published_sarif.exists()


@pytest.mark.parametrize(
    ("severity", "level", "score"),
    [
        ("critical", "error", "9.4"),
        ("high", "error", "8"),
        ("medium", "note", "5"),
        ("low", "note", "2"),
        ("info", "none", "1"),
        ("unknown", "none", "9.5"),
    ],
)
def test_native_severity_is_preserved_in_both_published_reports(
    tmp_path: Path, severity: str, level: str, score: str
) -> None:
    target, findings, report = _native_reports()
    findings[0]["info"]["severity"] = severity
    run = report["runs"][0]
    run["results"][0]["level"] = level
    run["tool"]["driver"]["rules"][0]["properties"]["security-severity"] = score
    native_json = tmp_path / "private.json"
    native_sarif = tmp_path / "private.sarif"
    native_json.write_text(json.dumps(findings), encoding="utf-8")
    native_sarif.write_text(json.dumps(report), encoding="utf-8")
    public_json = tmp_path / "published.json"
    public_sarif = tmp_path / "published.sarif"

    assert (
        dast_privacy.sanitize_files(
            target, native_json, native_sarif, public_json, public_sarif
        )
        == 0
    )
    assert (
        json.loads(public_json.read_text(encoding="utf-8"))[0]["info"]["severity"]
        == severity
    )
    public_run = json.loads(public_sarif.read_text(encoding="utf-8"))["runs"][0]
    assert public_run["results"][0]["level"] == level
    assert (
        public_run["tool"]["driver"]["rules"][0]["properties"]["security-severity"]
        == score
    )


@pytest.mark.parametrize(
    "record,target",
    [
        (
            {"template-id": "bad/value", "info": {"severity": "high"}},
            "https://host.test",
        ),
        (
            {"template-id": "host.test", "info": {"severity": "high"}},
            "https://host.test",
        ),
        (
            {"template-id": "private-area", "info": {"severity": "high"}},
            "https://host.test/private-area",
        ),
        ({"template-id": "ok", "info": {"severity": []}}, "https://host.test"),
        ({"template-id": "ok", "info": {"severity": "other"}}, "https://host.test"),
        ({"template-id": "ok", "info": None}, "https://host.test"),
        ({"template-id": "ok", "info": {"severity": "high"}}, "not-a-url"),
    ],
)
def test_unsafe_or_invalid_finding_cannot_be_published(
    record: dict[str, object], target: str
) -> None:
    with pytest.raises(dast_privacy.PrivacyError):
        dast_privacy.sanitize_findings([record], target)


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "run-count",
        "tool",
        "tool-version",
        "duplicate-rule",
        "tags",
        "score-type",
        "score-value",
        "unknown-rule",
        "level",
        "locations",
        "kind",
        "empty-uri",
        "uri-type",
        "empty-results",
        "malformed",
    ],
)
def test_unsafe_or_invalid_sarif_cannot_be_published(change: str) -> None:
    target, _, report = _native_reports()
    run = report["runs"][0]
    driver = run["tool"]["driver"]
    result = run["results"][0]
    if change == "version":
        report["version"] = "1.0"
    elif change == "run-count":
        report["runs"] = []
    elif change == "tool":
        driver["name"] = "other"
    elif change == "tool-version":
        driver["semanticVersion"] = "bad"
    elif change == "duplicate-rule":
        driver["rules"].append(driver["rules"][0].copy())
    elif change == "tags":
        driver["rules"][0]["properties"]["tags"] = []
    elif change == "score-type":
        driver["rules"][0]["properties"]["security-severity"] = 8
    elif change == "score-value":
        driver["rules"][0]["properties"]["security-severity"] = "11"
    elif change == "unknown-rule":
        result["ruleId"] = "other-rule"
    elif change == "level":
        result["level"] = "other"
    elif change == "locations":
        result["locations"] = []
    elif change == "kind":
        result["kind"] = "pass"
    elif change == "empty-uri":
        result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] = ""
    elif change == "uri-type":
        result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] = 1
    elif change == "empty-results":
        run["results"] = []
    else:
        del run["tool"]

    with pytest.raises(dast_privacy.PrivacyError):
        dast_privacy.sanitize_sarif(report, target)


def test_location_fingerprints_hide_target_and_distinguish_endpoints() -> None:
    first_target = "https://stage.example.test/private-area"
    second_target = "https://other.example.test/other-private"
    first = dast_privacy._location_uri(f"/{first_target}/one?q=private", first_target)
    same = dast_privacy._location_uri(f"/{second_target}/one?q=other", second_target)
    second = dast_privacy._location_uri(f"/{first_target}/two", first_target)

    assert first == same
    assert first != second
    assert "stage.example.test" not in first
    assert "private-area" not in first
    assert dast_privacy._location_uri("/endpoint", "https://stage.example.test/")


def test_location_fingerprints_preserve_parameter_names_without_values() -> None:
    target = "https://stage.example.test/private-area"
    first = dast_privacy._location_uri(f"/{target}/one?a=private", target)
    same = dast_privacy._location_uri(f"/{target}/one?a=other", target)
    other = dast_privacy._location_uri(f"/{target}/one?b=private", target)

    assert first == same
    assert first != other


def test_location_fingerprints_normalize_encoded_target_paths() -> None:
    encoded = "https://stage.example.test/private%2Darea"
    normal = "https://other.example.test/other-private"

    assert dast_privacy._location_uri(
        "/https://stage.example.test/private-area/one", encoded
    ) == dast_privacy._location_uri(f"/{normal}/one", normal)


def test_invalid_target_cannot_produce_a_sarif_report() -> None:
    _, _, report = _native_reports()

    with pytest.raises(dast_privacy.PrivacyError):
        dast_privacy.sanitize_sarif(report, "not-a-url")


@pytest.mark.parametrize("second_severity,expected", [("high", 0), ("low", 1)])
def test_duplicate_template_severity_must_be_consistent(
    tmp_path: Path, second_severity: str, expected: int
) -> None:
    target, findings, report = _native_reports()
    findings.append(
        {"template-id": "CVE-2025-12345", "info": {"severity": second_severity}}
    )
    report["runs"][0]["results"].append(report["runs"][0]["results"][0].copy())
    native_json = tmp_path / "private.json"
    native_sarif = tmp_path / "private.sarif"
    native_json.write_text(json.dumps(findings), encoding="utf-8")
    native_sarif.write_text(json.dumps(report), encoding="utf-8")
    published_sarif = tmp_path / "published.sarif"

    assert (
        dast_privacy.sanitize_files(
            target,
            native_json,
            native_sarif,
            tmp_path / "published.json",
            published_sarif,
        )
        == expected
    )
    assert published_sarif.exists() is (expected == 0)


@pytest.mark.parametrize("sarif_text", ["[]", "{", '{"x":1,"x":2}', '{"x":NaN}'])
def test_invalid_sarif_never_publishes_raw_data(
    tmp_path: Path, sarif_text: str
) -> None:
    target, findings, _ = _native_reports()
    native_json = tmp_path / "private.json"
    native_sarif = tmp_path / "private.sarif"
    native_json.write_text(json.dumps(findings), encoding="utf-8")
    native_sarif.write_text(sarif_text, encoding="utf-8")
    published_sarif = tmp_path / "published.sarif"

    assert (
        dast_privacy.sanitize_files(
            target,
            native_json,
            native_sarif,
            tmp_path / "published.json",
            published_sarif,
        )
        == 1
    )
    assert not published_sarif.exists()


def test_unexpected_sarif_with_clean_json_is_not_published(tmp_path: Path) -> None:
    target, _, report = _native_reports()
    native_json = tmp_path / "private.json"
    native_sarif = tmp_path / "private.sarif"
    native_json.write_text("[]", encoding="utf-8")
    native_sarif.write_text(json.dumps(report), encoding="utf-8")
    published_sarif = tmp_path / "published.sarif"

    assert (
        dast_privacy.sanitize_files(
            target,
            native_json,
            native_sarif,
            tmp_path / "published.json",
            published_sarif,
        )
        == 1
    )
    assert not published_sarif.exists()


def test_module_entry_point_validates_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_URL", "https://stage.example.test/")
    monkeypatch.setattr(
        sys, "argv", [str(Path(dast_privacy.__file__)), "validate-target"]
    )

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(dast_privacy.__file__, run_name="__main__")

    assert raised.value.code == 0


def _trace_record(url: str, error: str = "none", kind: str = "http") -> dict[str, str]:
    return {
        "template": "local-template.yaml",
        "type": kind,
        "input": url,
        "address": "stage.example.test:443",
        "error": error,
    }


def _completion_files(tmp_path: Path, records: list[object]) -> tuple[Path, Path, Path]:
    trace = tmp_path / "private-trace.jsonl"
    trace.write_text("".join(json.dumps(record) + "\n" for record in records))
    log = tmp_path / "private-stderr.log"
    log.write_text("[INF] Scan completed in 1s. No results found.\n")
    return trace, log, tmp_path / "summary.md"


def test_scan_completion_requires_a_successful_same_origin_request(
    tmp_path: Path,
) -> None:
    target = "https://stage.example.test/private-area"
    trace, log, summary = _completion_files(
        tmp_path,
        [
            _trace_record("https://another.example.test/path", "refused"),
            _trace_record("https://stage.example.test:443/private-area/proof"),
        ],
    )

    assert (
        dast_privacy.verify_scan(target, "success", "a" * 40, trace, log, summary) == 0
    )
    published = summary.read_text(encoding="utf-8")
    assert "a" * 40 in published
    assert "same-origin HTTP" in published
    assert target not in published
    assert "private-area" not in published


@pytest.mark.parametrize(
    "records,outcome,sha,log_text",
    [
        ([], "success", "a" * 40, "[INF] Scan completed in 1s.\n"),
        (
            [_trace_record("https://other.example.test/")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("http://stage.example.test/")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test:444/")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test/", "connection refused")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [
                _trace_record("https://stage.example.test/"),
                _trace_record("https://stage.example.test/", "connection reset"),
            ],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test/", kind="dns")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test/")],
            "failure",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test/")],
            "success",
            "bad-sha",
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test/")],
            "success",
            "a" * 40,
            "[INF] started\n",
        ),
        (
            [_trace_record("https://stage.example.test/")],
            "success",
            "a" * 40,
            "[INF] Skipped stage.example.test:443 from target list as found unresponsive permanently: refused\n[INF] Scan completed in 1s.\n",
        ),
        (
            [{"type": "http", "input": "https://stage.example.test/"}],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("https://stage.example.test:bad/")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        (
            [_trace_record("not-an-http-url")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
        ([_trace_record("")], "success", "a" * 40, "[INF] Scan completed in 1s.\n"),
        (
            [_trace_record("https://stage.example.test/", "")],
            "success",
            "a" * 40,
            "[INF] Scan completed in 1s.\n",
        ),
    ],
)
def test_scan_completion_rejects_absent_or_failed_execution(
    tmp_path: Path,
    records: list[object],
    outcome: str,
    sha: str,
    log_text: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = "https://stage.example.test/private-area"
    trace, log, summary = _completion_files(tmp_path, records)
    log.write_text(log_text)

    assert dast_privacy.verify_scan(target, outcome, sha, trace, log, summary) == 1
    assert not summary.exists()
    output = capsys.readouterr()
    assert target not in output.out + output.err
    assert "stage.example.test" not in output.out + output.err


@pytest.mark.parametrize(
    "text", ["{", '{"type":"http","type":"http"}', '{"type":NaN}', "[]", "\n"]
)
def test_scan_completion_rejects_malformed_private_trace(
    tmp_path: Path, text: str
) -> None:
    trace, log, summary = _completion_files(tmp_path, [])
    trace.write_text(text, encoding="utf-8")
    assert (
        dast_privacy.verify_scan(
            "https://stage.example.test", "success", "a" * 40, trace, log, summary
        )
        == 1
    )


@pytest.mark.parametrize("missing", ["trace", "log"])
def test_scan_completion_rejects_missing_private_evidence(
    tmp_path: Path, missing: str
) -> None:
    trace, log, summary = _completion_files(
        tmp_path, [_trace_record("https://stage.example.test/")]
    )
    (trace if missing == "trace" else log).unlink()
    assert (
        dast_privacy.verify_scan(
            "https://stage.example.test", "success", "a" * 40, trace, log, summary
        )
        == 1
    )


def test_scan_completion_bounds_private_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace, log, summary = _completion_files(
        tmp_path, [_trace_record("https://stage.example.test/")]
    )
    monkeypatch.setattr(dast_privacy, "MAX_EVIDENCE_BYTES", 12)
    assert (
        dast_privacy.verify_scan(
            "https://stage.example.test", "success", "a" * 40, trace, log, summary
        )
        == 1
    )


def test_scan_completion_cli_uses_environment_and_private_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace, log, summary = _completion_files(
        tmp_path, [_trace_record("https://stage.example.test/")]
    )
    monkeypatch.setenv("TARGET_URL", "https://stage.example.test")
    monkeypatch.setenv("SCAN_OUTCOME", "success")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    assert (
        dast_privacy.main(
            [
                "verify-scan",
                "--trace-in",
                str(trace),
                "--log-in",
                str(log),
                "--summary-file",
                str(summary),
            ]
        )
        == 0
    )
