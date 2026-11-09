"""Exercise the real Trivy path matcher against the repository KSV policy.

Run with ``python3 -m scripts.quality.prove_aud245_trivy_path_scope``. The
proof requires Trivy 0.75.0 on PATH and fails if it is unavailable. It uses
the binary's embedded checks and an isolated cache.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.quality import validate_trivy_kyverno_fixture as fixture_validator

ROOT = Path(__file__).resolve().parents[2]
SCOPED_PATHS = (
    fixture_validator.EXPECTED_FIXTURE.as_posix(),
    "k8s/spire/spire-agent.yaml",
    "k8s/spire/spire-rbac.yaml",
)
TRIVY = shutil.which("trivy")


def _policy_scopes() -> dict[str, frozenset[str]]:
    """Read path lists from the pinned policy's restricted, known layout."""
    policy_path = ROOT / ".trivyignore.yaml"
    fixture_validator._check_sha256(
        policy_path,
        fixture_validator.EXPECTED_IGNORE_POLICY_SHA256,
        "Trivy ignore policy",
    )
    text = policy_path.read_text(encoding="utf-8")
    if (
        not text.startswith("misconfigurations:\n")
        or text.count("\nvulnerabilities:\n") != 1
    ):
        raise ValueError("unexpected Trivy ignore policy layout")
    section = text.split("\nvulnerabilities:\n", 1)[0]
    entries = list(re.finditer(r"(?m)^  - id: (KSV-[0-9]{4})$", section))
    if not entries or len(entries) != len(re.findall(r"(?m)^  - id: ", section)):
        raise ValueError("unexpected misconfiguration entry")
    scopes: dict[str, frozenset[str]] = {}
    for index, entry in enumerate(entries):
        end = entries[index + 1].start() if index + 1 < len(entries) else len(section)
        lines = section[entry.start() : end].splitlines()
        if len(lines) < 3 or lines[1] != "    paths:":
            raise ValueError("misconfiguration entry has no explicit paths")
        paths: list[str] = []
        for line in lines[2:]:
            if not line.startswith("      - "):
                break
            path = line[len("      - ") :]
            if (
                re.fullmatch(r"[A-Za-z0-9_./-]+", path) is None
                or PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts
                or PurePosixPath(path).as_posix() != path
            ):
                raise ValueError("misconfiguration path is not an exact relative path")
            paths.append(path)
        if not paths or len(paths) != len(set(paths)) or entry[1] in scopes:
            raise ValueError("missing or duplicate policy identity")
        scopes[entry[1]] = frozenset(paths)
    return scopes


def _run(
    command: list[str], *, cwd: Path, environment: dict[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    async def execute() -> subprocess.CompletedProcess[str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    return asyncio.run(execute())


class TrivyPathScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(TRIVY, "Trivy 0.75.0 is required for the path-scope proof")
        fixture_validator._check_sha256(
            ROOT / fixture_validator.EXPECTED_FIXTURE.as_posix(),
            fixture_validator.EXPECTED_FIXTURE_SHA256,
            "fixture",
        )
        fixture_validator.validate_expiry()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp_root = Path(self.temporary.name)
        self.scan_root = self.temp_root / "scan"
        self.scan_root.mkdir()
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("TRIVY_")
        }
        for relative in SCOPED_PATHS:
            for destination in (relative, f"probe/{relative}"):
                target = self.scan_root / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
        shutil.copyfile(
            ROOT / ".trivyignore.yaml", self.scan_root / ".trivyignore.yaml"
        )
        fixture_validator._check_sha256(
            self.scan_root / ".trivyignore.yaml",
            fixture_validator.EXPECTED_IGNORE_POLICY_SHA256,
            "copied Trivy ignore policy",
        )
        shutil.copyfile(
            ROOT / "security/trivy-university-config.yaml",
            self.scan_root / "trivy-config.yaml",
        )

    def scan(self, *, ignorefile: str, severity: str) -> dict[str, Counter[Any]]:
        completed = _run(
            [
                str(TRIVY),
                "config",
                "--cache-dir",
                str(self.temp_root / "cache"),
                "--skip-check-update",
                "--skip-version-check",
                "--config",
                "trivy-config.yaml",
                f"--ignorefile={ignorefile}",
                "--severity",
                severity,
                "--format",
                "json",
                "--exit-code",
                "1",
                ".",
            ],
            cwd=self.scan_root,
            environment=self.environment,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        report = json.loads(completed.stdout)
        results = report["Results"]
        self.assertEqual(len(results), len(SCOPED_PATHS) * 2)
        findings: dict[str, Counter[Any]] = {}
        for result in results:
            target = result["Target"].replace("\\", "/")
            self.assertNotIn(target, findings)
            values = result.get("Misconfigurations", [])
            self.assertIsInstance(values, list)
            findings[target] = Counter(
                fixture_validator._finding_from_json(value) for value in values
            )
        self.assertEqual(
            set(findings),
            set(SCOPED_PATHS) | {f"probe/{path}" for path in SCOPED_PATHS},
        )
        return findings

    def test_scoped_findings_do_not_hide_identical_outside_files(self) -> None:
        version = _run(
            [str(TRIVY), "--version"],
            cwd=self.scan_root,
            environment=self.environment,
            timeout=30,
        )
        version.check_returncode()
        self.assertIn("Version: 0.75.0", version.stdout.splitlines())

        scopes = _policy_scopes()
        raw = self.scan(ignorefile="", severity="UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL")
        filtered = self.scan(
            ignorefile=".trivyignore.yaml", severity="UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
        )
        high = self.scan(ignorefile=".trivyignore.yaml", severity="CRITICAL,HIGH")

        raw_fixture_high = Counter(
            {
                finding: count
                for finding, count in raw[SCOPED_PATHS[0]].items()
                if finding[1] in {"CRITICAL", "HIGH"}
            }
        )
        self.assertEqual(raw_fixture_high, fixture_validator.EXPECTED_RAW_FINDINGS)
        exercised: set[str] = set()
        for path in SCOPED_PATHS:
            allowed = {rule for rule, paths in scopes.items() if path in paths}
            observed = {finding[0] for finding in raw[path]}
            self.assertTrue(allowed & observed, path)
            exercised.update(allowed & observed)
            self.assertEqual(raw[f"probe/{path}"], raw[path])
            self.assertEqual(filtered[f"probe/{path}"], raw[path])
            self.assertEqual(
                filtered[path],
                Counter(
                    {
                        finding: count
                        for finding, count in raw[path].items()
                        if finding[0] not in allowed
                    }
                ),
            )
            self.assertFalse(high[path])
            self.assertEqual(
                high[f"probe/{path}"],
                Counter(
                    {
                        finding: count
                        for finding, count in raw[path].items()
                        if finding[1] in {"CRITICAL", "HIGH"}
                    }
                ),
            )
        self.assertEqual(exercised, set(scopes))


if __name__ == "__main__":
    unittest.main()
