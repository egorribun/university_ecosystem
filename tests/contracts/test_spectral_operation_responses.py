"""Unit guards supplement, but never replace, pinned Spectral execution."""

from __future__ import annotations

import json
import sys

import pytest
import yaml

from scripts.quality import check_spectral_operation_responses as spectral


@pytest.fixture
def spectral_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(spectral, "ROOT", tmp_path)
    ruleset = {
        "extends": ["spectral:oas"],
        "rules": {
            spectral.RULE: {
                "severity": "warn",
                "given": "$.paths.*[get,post,put,patch,delete]",
            }
        },
    }
    (tmp_path / ".spectral.yml").write_text(yaml.safe_dump(ruleset), encoding="utf-8")
    image = "stoplight/spectral:1.2.3@sha256:" + "a" * 64
    workflow = {
        "jobs": {
            "spectral-lint": {
                "steps": [
                    {"name": name, "run": f"docker run {image} lint fixture.json"}
                    for name in ("Run Spectral lint", "Fail if errors found")
                ]
            }
        }
    }
    workflow_dir = tmp_path / ".github/workflows"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "contract-validation.yml"
    workflow_path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    return tmp_path, ruleset, workflow, image


def _diagnostics():
    return [
        {
            "code": spectral.RULE,
            "path": ["paths", f"/responses-{case}", verb, "responses"],
            "severity": 1,
        }
        for case in ("200", "default")
        for verb in spectral.VERBS
    ] + [
        {
            "code": "pii-field-marker",
            "path": ["components", "schemas", "Person", "properties", "email"],
            "severity": 1,
        },
        {"code": "oas3-api-servers", "path": [], "severity": 1},
    ]


def test_spectral_fixture_preserves_selected_and_unselected_operations():
    fixture = spectral.fixture()
    paths = fixture["paths"]
    assert len(paths) == 5
    for case in spectral.CASES:
        operations = paths[f"/responses-{case.lower()}"]
        assert set(operations) == set(spectral.VERBS)
        assert all(
            set(operation["responses"]) == {case} for operation in operations.values()
        )
    assert set(paths["/outside-selector"]) == {"head", "options", "trace"}
    assert "servers" not in fixture
    assert fixture["components"]["schemas"]["Person"]["properties"] == {
        "email": {"type": "string"}
    }


def test_spectral_image_uses_both_existing_identical_pins(spectral_workspace):
    assert spectral.image() == spectral_workspace[3]


@pytest.mark.parametrize("case", ["missing-command", "missing-pin", "different-pin"])
def test_spectral_image_refuses_unproven_pin(spectral_workspace, case):
    root, _ruleset, workflow, _image = spectral_workspace
    steps = workflow["jobs"]["spectral-lint"]["steps"]
    if case == "missing-command":
        steps.pop()
    elif case == "missing-pin":
        steps[0]["run"] = "docker run stoplight/spectral:latest lint fixture.json"
    else:
        steps[0]["run"] = steps[0]["run"].replace("a" * 64, "b" * 64)
    path = root / ".github/workflows/contract-validation.yml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")

    with pytest.raises(ValueError):
        spectral.image()


def test_spectral_checker_accepts_only_complete_expected_evidence(
    spectral_workspace, capsys
):
    path = spectral_workspace[0] / "diagnostics.json"
    path.write_text(json.dumps(_diagnostics()), encoding="utf-8")

    spectral.check(path)

    summary = json.loads(capsys.readouterr().out)
    assert len(summary["response_paths"]) == 10
    assert summary["pii_paths"] == [
        ["components", "schemas", "Person", "properties", "email"]
    ]


@pytest.mark.parametrize(
    "case",
    [
        "not-list",
        "non-object",
        "path-not-list",
        "path-non-string",
        "severity-info",
        "severity-bool",
        "duplicate",
        "missing",
        "unexpected",
        "pii-missing",
        "pii-wrong",
        "oas-missing",
        "extension",
        "selector",
        "rule-severity",
    ],
)
def test_spectral_checker_refuses_incomplete_or_drifted_evidence(
    spectral_workspace, case
):
    root, ruleset, _workflow, _image = spectral_workspace
    diagnostics = _diagnostics()
    if case == "not-list":
        diagnostics = {}
    elif case == "non-object":
        diagnostics = [None]
    elif case == "path-not-list":
        diagnostics[0]["path"] = None
    elif case == "path-non-string":
        diagnostics[0]["path"] = [1]
    elif case == "severity-info":
        diagnostics[0]["severity"] = 2
    elif case == "severity-bool":
        diagnostics[0]["severity"] = True
    elif case == "duplicate":
        diagnostics.append(dict(diagnostics[0]))
    elif case == "missing":
        diagnostics.pop(0)
    elif case == "unexpected":
        diagnostics[0]["path"][1] = "/responses-400"
    elif case == "pii-missing":
        diagnostics.pop(-2)
    elif case == "pii-wrong":
        diagnostics[-2]["path"][-1] = "other"
    elif case == "oas-missing":
        diagnostics.pop()
    elif case == "extension":
        ruleset["extends"] = []
    elif case == "selector":
        ruleset["rules"][spectral.RULE]["given"] = "$.paths.*"
    else:
        ruleset["rules"][spectral.RULE]["severity"] = "info"
    (root / ".spectral.yml").write_text(yaml.safe_dump(ruleset), encoding="utf-8")
    path = root / "diagnostics.json"
    path.write_text(json.dumps(diagnostics), encoding="utf-8")

    with pytest.raises(ValueError):
        spectral.check(path)


@pytest.mark.parametrize("command", ["image", "fixture", "check", "invalid"])
def test_spectral_cli_modes(spectral_workspace, monkeypatch, capsys, command):
    args = ["spectral-contract", command]
    if command == "check":
        path = spectral_workspace[0] / "diagnostics.json"
        path.write_text(json.dumps(_diagnostics()), encoding="utf-8")
        args.append(str(path))
    monkeypatch.setattr(sys, "argv", args)

    if command == "invalid":
        with pytest.raises(SystemExit, match="Expected image, fixture, or check"):
            spectral.main()
        return
    spectral.main()
    output = capsys.readouterr().out
    if command == "image":
        assert output.strip() == spectral_workspace[3]
    elif command == "fixture":
        assert json.loads(output) == spectral.fixture()
    else:
        assert len(json.loads(output)["response_paths"]) == 10
