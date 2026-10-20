"""Behavioral contracts for the shipped Spectral response rule."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
VERBS = ("get", "post", "put", "patch", "delete")
CASES = ("200", "default", "400", "4XX")
RULE = "operation-4xx-response"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def image() -> str:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/contract-validation.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["spectral-lint"]["steps"]
    commands = [
        step["run"]
        for step in steps
        if step.get("name") in {"Run Spectral lint", "Fail if errors found"}
    ]
    _require(len(commands) == 2, "Expected both existing Spectral commands")
    images = [
        re.findall(
            r"(?<!\S)(stoplight/spectral:\d+\.\d+\.\d+"
            r"@sha256:[0-9a-f]{64})(?=\s)",
            command,
        )
        for command in commands
    ]
    _require(
        all(len(matches) == 1 for matches in images),
        "Each existing command must contain one immutable Spectral image",
    )
    _require(images[0] == images[1], "Existing Spectral image pins disagree")
    pinned_image: str = images[0][0]
    return pinned_image


def fixture() -> dict[str, object]:
    paths = {
        f"/responses-{case.lower()}": {
            verb: {
                "operationId": f"{verb}_{case.lower()}",
                "description": "Synthetic operation.",
                "responses": {case: {"description": "Synthetic response."}},
            }
            for verb in VERBS
        }
        for case in CASES
    }
    paths["/outside-selector"] = {
        verb: {
            "operationId": f"outside_{verb}",
            "description": "Preserve the current custom-rule selector.",
            "responses": {"200": {"description": "Synthetic response."}},
        }
        for verb in ("head", "options", "trace")
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Spectral response regression",
            "version": "1.0.0",
            "description": "Synthetic response contracts.",
        },
        "paths": paths,
        "components": {
            "schemas": {
                "Person": {
                    "type": "object",
                    "properties": {"email": {"type": "string"}},
                }
            }
        },
    }


def check(path: Path) -> None:
    ruleset = yaml.safe_load((ROOT / ".spectral.yml").read_text(encoding="utf-8"))
    _require(ruleset["extends"] == ["spectral:oas"], "Preserve the OAS extension")
    rule = ruleset["rules"][RULE]
    _require(rule["severity"] == "warn", "Preserve custom warning severity")
    _require(
        rule["given"] == "$.paths.*[get,post,put,patch,delete]",
        "Preserve the existing operation selector",
    )

    diagnostics = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(diagnostics, list), "Diagnostics must be a JSON array")
    _require(
        all(isinstance(item, dict) for item in diagnostics),
        "Each diagnostic must be an object",
    )
    matching = [item for item in diagnostics if item.get("code") == RULE]
    pii = [item for item in diagnostics if item.get("code") == "pii-field-marker"]
    for item in [*matching, *pii]:
        _require(
            isinstance(item.get("path"), list)
            and all(isinstance(part, str) for part in item["path"]),
            "Custom diagnostic paths must contain property names",
        )
        _require(
            type(item.get("severity")) is int and item["severity"] == 1,
            "Custom diagnostics must remain warnings",
        )
    print(
        json.dumps(
            {
                "response_paths": [item["path"] for item in matching],
                "pii_paths": [item["path"] for item in pii],
            }
        )
    )
    expected = {
        ("paths", f"/responses-{case}", verb, "responses")
        for case in ("200", "default")
        for verb in VERBS
    }
    actual = [tuple(item["path"]) for item in matching]
    _require(len(actual) == len(set(actual)), "Duplicate custom-rule diagnostics")
    _require(
        set(actual) == expected,
        f"Response diagnostics mismatch: missing={sorted(expected - set(actual))}; "
        f"unexpected={sorted(set(actual) - expected)}",
    )
    _require(len(pii) == 1, "Expected the preserved PII marker warning")
    _require(
        pii[0]["path"][:5]
        == ["components", "schemas", "Person", "properties", "email"],
        "PII warning must identify the synthetic email property",
    )
    _require(
        any(item.get("code") == "oas3-api-servers" for item in diagnostics),
        "Expected the preserved recommended OAS server diagnostic",
    )


def main() -> None:
    args = sys.argv[1:]
    if args == ["image"]:
        print(image())
    elif args == ["fixture"]:
        print(json.dumps(fixture()))
    elif len(args) == 2 and args[0] == "check":
        check(Path(args[1]))
    else:
        raise SystemExit("Expected image, fixture, or check DIAGNOSTICS")


if __name__ == "__main__":
    main()
