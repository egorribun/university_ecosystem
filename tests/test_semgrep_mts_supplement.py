"""Focused controls for the explicit MTS Semgrep supplemental scan."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPOSITORY_ROOT / "scripts" / "quality" / "run_semgrep_gate.py"
SPEC = importlib.util.spec_from_file_location("mts_candidate_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

TARGETS = tuple(sorted(gate.REVIEWED_UNIGNORED_MTS_TARGETS))
IMAGE = "semgrep/semgrep:1.179.0@sha256:" + "d" * 64
CONTAINER_ID = "b" * 64


def _report(targets: tuple[str, ...] = TARGETS) -> dict[str, Any]:
    return {
        "version": "1.179.0",
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": list(targets), "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }


def _completed(
    command: list[str],
    returncode: int = 0,
    *,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command, returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_mts_target_set_is_exact_and_obeys_reviewed_ignore_policy(
    tmp_path: Path,
) -> None:
    overlay = tmp_path / "overlay"
    for relative in (*TARGETS, "frontend/tests/e2e/ignored.d.mts"):
        path = overlay / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("export {};\n", encoding="utf-8")
    hashes = {
        relative: hashlib.sha256(b"fixture\n").hexdigest()
        for relative in (*TARGETS, "frontend/tests/e2e/ignored.d.mts")
    }

    selected = gate._mts_scan_targets(
        overlay,
        hashes,
        lambda path: path.startswith("frontend/tests/"),
    )

    assert selected == TARGETS
    hashes["frontend/scripts/new-unreviewed.d.mts"] = "a" * 64
    with pytest.raises(gate.SemgrepGateError, match="unreviewed unignored MTS"):
        gate._mts_scan_targets(
            overlay,
            hashes,
            lambda path: path.startswith("frontend/tests/"),
        )


def test_mts_rule_projection_preserves_all_selected_javascript_and_typescript_rules(
    tmp_path: Path,
) -> None:
    selected_config = tmp_path / "selected.json"
    destination = tmp_path / "mts.json"
    rules = [
        {"id": "python-only", "languages": ["python"], "pattern": "x"},
        {"id": "javascript", "languages": ["javascript"], "pattern": "x"},
        {"id": "typescript", "languages": ["typescript"], "pattern": "x"},
        {
            "id": "mixed-js-ts",
            "languages": ["javascript", "typescript"],
            "pattern": "x",
        },
    ]
    selected_config.write_text(
        json.dumps({"rules": rules}), encoding="utf-8", newline="\n"
    )

    digest, ids = gate._write_mts_rules_config(selected_config, destination)

    projected = json.loads(destination.read_text(encoding="utf-8"))
    assert projected == {"rules": rules[1:]}
    assert ids == ("javascript", "typescript", "mixed-js-ts")
    assert digest == hashlib.sha256(destination.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-target", "exact target set"),
        ("skipped-target", "skipped an explicit target"),
        ("timeout", "timed-out analysis"),
        ("skipped-rule", "skipped rules"),
        ("error", "reported diagnostics"),
        ("outside-finding", "outside its target set"),
    ],
)
def test_mts_report_rejects_incomplete_or_out_of_scope_evidence(
    mutation: str, message: str
) -> None:
    report = _report()
    if mutation == "missing-target":
        report["paths"]["scanned"].pop()
    elif mutation == "skipped-target":
        report["paths"]["skipped"].append(TARGETS[0])
    elif mutation == "timeout":
        report["time"]["fixpoint_timeouts"].append({"rule": "r", "path": TARGETS[0]})
    elif mutation == "skipped-rule":
        report["skipped_rules"].append({"rule_id": "r"})
    elif mutation == "error":
        report["errors"].append({"type": "PartialParsing", "path": TARGETS[0]})
    else:
        report["results"].append({"path": "app/outside.py"})

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._validate_mts_supplement_report(report, TARGETS)


def test_report_merge_retains_both_scans_findings_in_one_sarif_run() -> None:
    primary = _report(("app/example.py",))
    primary["results"] = [{"check_id": "out.primary", "path": "app/example.py"}]
    supplementary = _report()
    supplementary["results"] = [
        {"check_id": "out.mts", "path": TARGETS[0], "start": {"line": 2}}
    ]
    supplementary["time"]["scanning_time"] = {"total_time": 0.5}

    merged = gate._merge_semgrep_reports(
        primary,
        supplementary,
        targets=TARGETS,
        javascript_typescript_config_sha256="a" * 64,
        javascript_typescript_rule_ids=("javascript-rule", "typescript-rule"),
    )

    assert [item["check_id"] for item in merged["results"]] == [
        "out.primary",
        "out.mts",
    ]
    assert set(merged["paths"]["scanned"]) == {"app/example.py", *TARGETS}
    assert merged["paths"]["skipped"] == []
    assert merged["supplemental_scan_evidence"] == [
        {
            "mode": "explicit-unknown-extension-typescript",
            "targets": list(TARGETS),
            "javascript_typescript_config_sha256": "a" * 64,
            "javascript_typescript_rule_ids": [
                "javascript-rule",
                "typescript-rule",
            ],
            "time": supplementary["time"],
        }
    ]
    assert primary["paths"]["scanned"] == ["app/example.py"]

    merged_sarif = gate._merge_sarif_reports(
        {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Semgrep OSS",
                            "semanticVersion": "1.179.0",
                            "rules": [{"id": "primary"}],
                        }
                    },
                    "invocations": [{"executionSuccessful": True}],
                    "results": [{"ruleId": "primary"}],
                }
            ],
        },
        {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Semgrep OSS",
                            "semanticVersion": "1.179.0",
                            "rules": [{"id": "mts"}],
                        }
                    },
                    "invocations": [{"executionSuccessful": True}],
                    "results": [{"ruleId": "mts"}],
                }
            ],
        },
    )
    assert len(merged_sarif["runs"]) == 1
    merged_run = merged_sarif["runs"][0]
    assert [rule["id"] for rule in merged_run["tool"]["driver"]["rules"]] == [
        "primary",
        "mts",
    ]
    assert [result["ruleId"] for result in merged_run["results"]] == [
        "primary",
        "mts",
    ]
    assert len(merged_run["invocations"]) == 2
    with pytest.raises(gate.SemgrepGateError, match="version is unsupported"):
        gate._merge_sarif_reports({"version": "1.0", "runs": [{}]}, {})


def test_sarif_merge_keeps_one_run_and_all_direct_uri_evidence() -> None:
    srcroot = {"uri": "file:///src/"}
    primary = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep OSS",
                        "semanticVersion": "1.179.0",
                        "rules": [{"id": "out.primary"}],
                    },
                    "extensions": [],
                },
                "invocations": [
                    {"executionSuccessful": True, "properties": {"scan": "primary"}}
                ],
                "artifacts": [{"location": {"uri": "app/a.py"}}],
                "originalUriBaseIds": {"%SRCROOT%": srcroot},
                "results": [
                    {
                        "ruleId": "out.primary",
                        "properties": {
                            "ruleIndex": 12,
                            "toolComponent": "custom Semgrep property",
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": "app/a.py",
                                        "uriBaseId": "%SRCROOT%",
                                    }
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
    supplemental = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep OSS",
                        "semanticVersion": "1.179.0",
                        "rules": [
                            {"id": "out.primary"},
                            {"id": "out.supplemental"},
                        ],
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "properties": {"scan": "supplemental"},
                    }
                ],
                "artifacts": [{"location": {"uri": "app/a.py"}}],
                "originalUriBaseIds": {"%SRCROOT%": srcroot},
                "results": [
                    {
                        "ruleId": "out.supplemental",
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": "frontend/index.html",
                                        "uriBaseId": "%SRCROOT%",
                                    }
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }

    merged = gate._merge_sarif_reports(primary, supplemental)

    assert len(merged["runs"]) == 1
    merged_run = merged["runs"][0]
    assert [rule["id"] for rule in merged_run["tool"]["driver"]["rules"]] == [
        "out.primary",
        "out.supplemental",
    ]
    assert [result["ruleId"] for result in merged_run["results"]] == [
        "out.primary",
        "out.supplemental",
    ]
    assert merged_run["results"][0]["properties"] == {
        "ruleIndex": 12,
        "toolComponent": "custom Semgrep property",
    }
    assert [
        invocation["properties"]["scan"] for invocation in merged_run["invocations"]
    ] == ["primary", "supplemental"]
    assert [artifact["location"]["uri"] for artifact in merged_run["artifacts"]] == [
        "app/a.py"
    ]
    assert merged_run["originalUriBaseIds"] == {"%SRCROOT%": srcroot}
    assert merged_run["results"][1]["locations"][0]["physicalLocation"][
        "artifactLocation"
    ] == {"uri": "frontend/index.html", "uriBaseId": "%SRCROOT%"}


@pytest.mark.parametrize(
    ("supplemental_rule", "message"),
    [
        ({"id": "out.shared", "name": "supplemental"}, "conflicting duplicate rule"),
    ],
    ids=("conflicting-rule-descriptor",),
)
def test_sarif_merge_rejects_conflicting_shared_metadata(
    supplemental_rule: dict[str, str], message: str
) -> None:
    primary_run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": "Semgrep OSS",
                "semanticVersion": "1.179.0",
                "rules": [{"id": "out.shared", "name": "primary"}],
            }
        },
        "results": [{"ruleId": "out.shared"}],
    }
    supplemental_run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": "Semgrep OSS",
                "semanticVersion": "1.179.0",
                "rules": [supplemental_rule],
            }
        },
        "results": [],
    }
    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._merge_sarif_reports(
            {"version": "2.1.0", "runs": [primary_run]},
            {"version": "2.1.0", "runs": [supplemental_run]},
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("empty-runs", "exactly one run"),
        ("multiple-runs", "exactly one run"),
        ("non-list-runs", "exactly one run"),
        ("non-object-run", "run is malformed"),
        ("missing-tool", "pinned Semgrep 1.179 profile"),
        ("bad-rules-type", "pinned Semgrep 1.179 profile"),
        ("bad-results-type", "pinned Semgrep 1.179 profile"),
        ("bad-rule-item", "driver rule is malformed"),
        ("missing-driver-name", "does not match the pinned Semgrep"),
        ("empty-driver-name", "does not match the pinned Semgrep"),
        ("bad-result-item", "result is malformed"),
        ("top-level-metadata", "top-level metadata is incompatible"),
        ("run-metadata", "run metadata is incompatible"),
        ("tool-metadata", "tool metadata is incompatible"),
        ("extensions", "extensions cannot be merged safely"),
        ("null-extensions", "extensions cannot be merged safely"),
        ("bad-rule-id-type", "rule identity is malformed"),
        ("empty-rule-id", "rule identity is malformed"),
        ("duplicate-rule-id", "duplicate driver rule identity"),
        ("bad-result-id-type", "undeclared driver rule"),
        ("undeclared-result-id", "undeclared driver rule"),
        ("bad-invocations-type", "invocations are malformed"),
        ("bad-invocation-item", "invocations are malformed"),
        ("missing-invocation-success", "invocations are malformed"),
        ("bad-invocation-success", "invocations are malformed"),
    ],
    ids=(
        "empty-runs",
        "multiple-runs",
        "non-list-runs",
        "non-object-run",
        "missing-tool",
        "bad-rules-type",
        "bad-results-type",
        "bad-rule-item",
        "missing-driver-name",
        "empty-driver-name",
        "bad-result-item",
        "top-level-metadata",
        "run-metadata",
        "tool-metadata",
        "extensions",
        "null-extensions",
        "bad-rule-id-type",
        "empty-rule-id",
        "duplicate-rule-id",
        "bad-result-id-type",
        "undeclared-result-id",
        "bad-invocations-type",
        "bad-invocation-item",
        "missing-invocation-success",
        "bad-invocation-success",
    ),
)
def test_sarif_merge_rejects_profile_mutations(mutation: str, message: str) -> None:
    def report(rule_id: str) -> dict[str, Any]:
        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Semgrep OSS",
                            "semanticVersion": "1.179.0",
                            "rules": [{"id": rule_id}],
                        }
                    },
                    "results": [{"ruleId": rule_id}],
                    "invocations": [{"executionSuccessful": True}],
                }
            ],
        }

    primary = report("out.primary")
    supplemental = report("out.supplemental")
    primary_run = primary["runs"][0]
    supplemental_run = supplemental["runs"][0]
    if mutation == "empty-runs":
        primary["runs"] = []
    elif mutation == "multiple-runs":
        primary["runs"].append(primary_run)
    elif mutation == "non-list-runs":
        primary["runs"] = None
    elif mutation == "non-object-run":
        primary["runs"] = [None]
    elif mutation == "missing-tool":
        del primary_run["tool"]
    elif mutation == "bad-rules-type":
        primary_run["tool"]["driver"]["rules"] = None
    elif mutation == "bad-results-type":
        primary_run["results"] = None
    elif mutation == "bad-rule-item":
        primary_run["tool"]["driver"]["rules"] = ["not-a-rule"]
    elif mutation == "missing-driver-name":
        del primary_run["tool"]["driver"]["name"]
    elif mutation == "empty-driver-name":
        primary_run["tool"]["driver"]["name"] = ""
    elif mutation == "bad-result-item":
        primary_run["results"] = ["not-a-result"]
    elif mutation == "top-level-metadata":
        supplemental["$schema"] = "https://example.invalid/sarif.json"
    elif mutation == "run-metadata":
        supplemental_run["artifacts"] = [{"location": {"uri": "other.py"}}]
    elif mutation == "tool-metadata":
        supplemental_run["tool"]["driver"]["semanticVersion"] = "1.180.0"
    elif mutation == "extensions":
        supplemental_run["tool"]["extensions"] = [{"name": "unsupported"}]
    elif mutation == "null-extensions":
        supplemental_run["tool"]["extensions"] = None
    elif mutation == "bad-rule-id-type":
        primary_run["tool"]["driver"]["rules"][0]["id"] = 1
    elif mutation == "empty-rule-id":
        primary_run["tool"]["driver"]["rules"][0]["id"] = ""
    elif mutation == "duplicate-rule-id":
        primary_run["tool"]["driver"]["rules"].append({"id": "out.primary"})
    elif mutation == "bad-result-id-type":
        primary_run["results"][0]["ruleId"] = 1
    elif mutation == "undeclared-result-id":
        primary_run["results"][0]["ruleId"] = "out.unknown"
    elif mutation == "bad-invocations-type":
        primary_run["invocations"] = None
    elif mutation == "bad-invocation-item":
        primary_run["invocations"] = ["not-an-invocation"]
    elif mutation == "missing-invocation-success":
        primary_run["invocations"] = [{}]
    elif mutation == "bad-invocation-success":
        primary_run["invocations"] = [{"executionSuccessful": "yes"}]

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._merge_sarif_reports(primary, supplemental)


@pytest.mark.parametrize(
    "reference",
    [
        {"ruleIndex": 0},
        {"toolComponent": {"index": 0}},
        {
            "invocations": [
                {
                    "toolExecutionNotifications": [
                        {"associatedRule": {"id": "out.primary", "index": 0}}
                    ]
                }
            ]
        },
        {
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "app/a.py", "index": 0}
                    }
                }
            ]
        },
        {"logicalLocations": [{"parentIndex": 0}]},
        {"taxonIndex": 0},
    ],
    ids=(
        "rule-index",
        "tool-component-index",
        "associated-rule-index",
        "artifact-index",
        "logical-location-parent-index",
        "taxon-index",
    ),
)
def test_sarif_merge_rejects_indexed_references_until_they_can_be_remapped(
    reference: dict[str, Any],
) -> None:
    primary = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep OSS",
                        "semanticVersion": "1.179.0",
                        "rules": [{"id": "out.primary"}],
                    }
                },
                "results": [{"ruleId": "out.primary", **reference}],
            }
        ],
    }
    supplemental = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep OSS",
                        "semanticVersion": "1.179.0",
                        "rules": [{"id": "out.supplemental"}],
                    }
                },
                "results": [],
            }
        ],
    }

    with pytest.raises(gate.SemgrepGateError, match="indexed references"):
        gate._merge_sarif_reports(primary, supplemental)


def test_docker_mts_scan_uses_exact_roots_and_deterministic_cli_flags(
    tmp_path: Path,
) -> None:
    scan_root = tmp_path / "scan"
    output = tmp_path / "runner" / "out"
    scan_root.mkdir()
    output.mkdir(parents=True)
    for relative in TARGETS:
        path = scan_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("export {};\n", encoding="utf-8")

    calls: list[list[str]] = []
    name: str | None = None

    def command_runner(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        nonlocal name
        calls.append(command)
        if command[:2] == ["docker", "run"]:
            name = command[command.index("--name") + 1]
            Path(command[command.index("--cidfile") + 1]).write_text(
                f"{CONTAINER_ID}\n", encoding="utf-8"
            )
            return _completed(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return _completed(command, stdout=f"{CONTAINER_ID} /{name}\n")
        if command[:3] == ["docker", "rm", "-v"]:
            return _completed(command)
        raise AssertionError(f"unexpected command: {command!r}")

    status = gate._docker_scan(
        scan_root=scan_root,
        output_directory=output,
        image=IMAGE,
        command_runner=command_runner,
        scan_id="semgrep-mts",
        config_name="security-rules-mts.json",
        report_prefix="semgrep-mts",
        target_paths=TARGETS,
        scan_unknown_extensions=True,
    )

    assert status == 0
    scan = calls[0]
    assert "--scan-unknown-extensions" in scan
    assert "--disable-version-check" in scan
    assert scan[scan.index("--metrics") + 1] == "off"
    assert scan[scan.index("--config") + 1] == "/out/security-rules-mts.json"
    assert scan[-len(TARGETS) :] == list(TARGETS)
    assert "--json-output=/out/semgrep-mts.json" in scan
    assert "--sarif-output=/out/semgrep-mts.sarif" in scan
    assert "--lang" not in scan
    assert "--exclude" not in scan
    assert [command[:3] for command in calls[1:]] == [
        ["docker", "inspect", "--format"],
        ["docker", "rm", "-v"],
    ]


def test_docker_mts_scan_rejects_root_or_missing_targets_before_launch(
    tmp_path: Path,
) -> None:
    scan_root = tmp_path / "scan"
    output = tmp_path / "out"
    scan_root.mkdir()
    output.mkdir()
    calls: list[list[str]] = []

    with pytest.raises(gate.SemgrepGateError, match="explicit file targets"):
        gate._docker_scan(
            scan_root=scan_root,
            output_directory=output,
            image=IMAGE,
            command_runner=lambda command, **_kwargs: calls.append(command),
            target_paths=(".",),
            scan_unknown_extensions=True,
        )
    assert calls == []


def test_run_gate_scans_mts_targets_and_dispositions_gate_receives_merged_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    private_parent = repository_root / ".git" / "ue-audit-work"
    private_parent.mkdir(parents=True)
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", repository_root)
    monkeypatch.setattr(
        gate,
        "_validate_semgrep_ignore_policy",
        lambda _root: lambda path: path.startswith("frontend/tests/"),
    )
    monkeypatch.setattr(gate, "_verify_source_snapshot", lambda *_args: {})
    monkeypatch.setattr(gate, "_precommit_semgrep_image", lambda _root: IMAGE)
    monkeypatch.setattr(gate, "_workflow_rules_commit", lambda _root: "a" * 40)
    rules_root = tmp_path / "rules"
    rules_root.mkdir()
    monkeypatch.setattr(
        gate,
        "_checkout_rules",
        lambda *_args, **_kwargs: rules_root,
    )
    monkeypatch.setattr(gate, "_chart_template_sources", lambda _root: set())

    def create_snapshot(
        _repository_root: Path,
        destination: Path,
        *,
        command_runner: Any,
    ) -> tuple[Path, list[dict[str, str]], list[Any]]:
        del command_runner
        destination.mkdir()
        return destination, [], []

    monkeypatch.setattr(gate, "_create_scan_snapshot", create_snapshot)
    helper_error = type("FakeHelmOverlayError", (Exception,), {})
    helm_tool = SimpleNamespace(
        version="v4.2.4",
        platform_key="linux-amd64",
        binary_sha256="c" * 64,
    )

    def prepare_overlay(
        _scan_root: Path,
        destination: Path,
        _manifest: list[dict[str, str]],
        *,
        helm_tool: Any,
        bounded_runner: Any,
    ) -> tuple[Path, dict[str, Any]]:
        del helm_tool, bounded_runner
        destination.mkdir()
        for relative in TARGETS:
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("export {};\n", encoding="utf-8")
        (destination / ".semgrepignore").write_text("tests/\n", encoding="utf-8")
        return destination, {"fixture": "rendered-source-overlay"}

    helper = SimpleNamespace(
        HelmOverlayError=helper_error,
        helm_archive_pin=lambda *_args: {},
        verify_helm_archive=lambda *_args: helm_tool,
        prepare_overlay=prepare_overlay,
        bounded_process_runner=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(gate, "_load_overlay_helper", lambda _root: helper)
    monkeypatch.setattr(gate, "_validated_helm_archive_pin", lambda _pin: {})
    monkeypatch.setattr(
        gate, "_download_helm_archive", lambda _pin, destination: destination
    )
    monkeypatch.setattr(
        gate,
        "_validate_overlay_provenance",
        lambda *, overlay_root, **_kwargs: gate._tree_file_hashes(
            overlay_root, description="fixture overlay"
        ),
    )
    monkeypatch.setattr(gate, "_verify_index_unchanged", lambda **_kwargs: None)
    monkeypatch.setattr(gate, "_persist_reports", lambda *_args: None)

    scan_calls: list[dict[str, Any]] = []
    primary_report = _report(("app/example.py",))
    supplemental_report = _report()
    supplemental_report["results"] = [
        {
            "check_id": "out.example.mts-rule",
            "path": TARGETS[0],
            "start": {"line": 1, "col": 1, "offset": 0},
            "end": {"line": 1, "col": 8, "offset": 7},
            "extra": {"message": "fixture finding"},
        }
    ]

    def fake_docker_scan(**kwargs: Any) -> int:
        scan_calls.append(kwargs)
        output_directory = kwargs["output_directory"]
        is_mts_scan = kwargs.get("scan_unknown_extensions", False)
        report = supplemental_report if is_mts_scan else primary_report
        prefix = kwargs.get("report_prefix", "semgrep")
        (output_directory / f"{prefix}.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        rule_id = "mts" if is_mts_scan else "primary"
        sarif = {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Semgrep OSS",
                            "semanticVersion": "1.179.0",
                            "rules": [{"id": rule_id}],
                        }
                    },
                    "results": [{"ruleId": rule_id}],
                }
            ],
        }
        (output_directory / f"{prefix}.sarif").write_text(
            json.dumps(sarif), encoding="utf-8"
        )
        return 0

    monkeypatch.setattr(gate, "_docker_scan", fake_docker_scan)
    gate_reports: list[dict[str, Any]] = []

    def run_dispositions_gate(*, results_path: Path, **_kwargs: Any) -> int:
        merged = json.loads(results_path.read_text(encoding="utf-8"))
        gate_reports.append(merged)
        assert len(merged["supplemental_scan_evidence"]) == 1
        assert set(merged["paths"]["scanned"]) == {"app/example.py", *TARGETS}
        assert any(
            item["check_id"] == "out.example.mts-rule" for item in merged["results"]
        )
        return 0

    monkeypatch.setattr(gate, "_run_dispositions_gate", run_dispositions_gate)

    def command_runner(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if any(token.endswith("select_semgrep_rules.py") for token in command):
            selected = {
                "rules": [
                    {"id": "javascript-rule", "languages": ["javascript"]},
                    {"id": "typescript-rule", "languages": ["typescript"]},
                    {"id": "python-rule", "languages": ["python"]},
                ]
            }
            output = Path(command[command.index("--output") + 1])
            output.write_text(json.dumps(selected), encoding="utf-8")
        return _completed(command)

    result = gate.run_gate(
        IMAGE,
        repository_root,
        command_runner=command_runner,
        temporary_parent=private_parent,
    )

    assert result == 0
    assert len(scan_calls) == 2
    assert scan_calls[0].get("target_paths", (".",)) == (".",)
    assert scan_calls[1]["target_paths"] == TARGETS
    assert scan_calls[1]["scan_unknown_extensions"] is True
    assert len(gate_reports) == 1
    assert gate_reports[0]["supplemental_scan_evidence"][0][
        "javascript_typescript_rule_ids"
    ] == ["javascript-rule", "typescript-rule"]
