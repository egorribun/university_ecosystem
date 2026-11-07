"""Safe Temporal inspect diagnostics using real PowerShell and fake Docker only."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/temporal/bootstrap-functions.ps1"
PREFIX = "TEMPORAL_BOOTSTRAP_RUNTIME_INSPECT"
ARGUMENTS = ["image", "inspect", "--format", '{"Id":{{json .Id}}}', "fixture-only"]
PRIVATE = "private-test-marker-never-output"
DOCKER_ENV = (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_TLS_VERIFY",
    "DOCKER_API_VERSION",
)
RUNNER = r"""
param([string]$Helper, [string]$FixturePath)
. $Helper
$script:fixture = Get-Content -LiteralPath $FixturePath -Raw | ConvertFrom-Json
$PSNativeCommandUseErrorActionPreference = [bool]$fixture.nativeErrors
$ErrorActionPreference = [string]$fixture.errorAction
$global:LASTEXITCODE = 77
$script:calls = 0
if ($fixture.kind -ceq 'function') {
    function docker {
        $script:calls++
        $actual = ConvertTo-Json -InputObject @($args) -Compress
        $expected = ConvertTo-Json -InputObject @($script:fixture.arguments) -Compress
        if ($actual -cne $expected) { throw 'synthetic arguments mismatch' }
        if ($script:fixture.throws) { throw 'private-test-marker-never-output' }
        foreach ($message in @($script:fixture.errors)) {
            Write-Error ([string]$message) -ErrorAction Continue
        }
        foreach ($line in @($script:fixture.stdout)) { Write-Output $line }
        $global:LASTEXITCODE = [int]$script:fixture.exitCode
    }
} elseif ($fixture.kind -ceq 'native-alias') {
    Set-Location -LiteralPath $fixture.nativeDirectory
    Set-Alias -Name docker -Value $fixture.nativeExecutable
}
if ($fixture.classifierFailure) {
    function Add-TemporalBootstrapDockerErrorClass { throw 'private-test-marker-never-output' }
}
if ($fixture.writerFailure) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
public sealed class SyntheticBrokenErrorWriter : TextWriter {
    public override Encoding Encoding => Encoding.UTF8;
    public override void WriteLine(string value) { throw new IOException("private-test-marker-never-output"); }
}
'@
    $savedError = [Console]::Error
    [Console]::SetError([SyntheticBrokenErrorWriter]::new())
}
$accepted = $false
$fixedThrow = $false
try {
    $value = Get-TemporalBootstrapDockerObject -Phase 'temporal-server-image' -Arguments @($fixture.arguments)
    $accepted = $value.ok -eq $true
} catch {
    $fixedThrow = $_.Exception.Message -cin @('Cannot inspect Temporal bootstrap runtime identity.', 'Cannot parse Temporal bootstrap runtime identity.')
} finally {
    if ($fixture.writerFailure) { [Console]::SetError($savedError) }
}
[Console]::Out.WriteLine((@{
    accepted=$accepted; fixedThrow=$fixedThrow; calls=$script:calls;
    lastExitCode=$global:LASTEXITCODE; nativeErrors=$PSNativeCommandUseErrorActionPreference;
    errorAction=[string]$ErrorActionPreference
} | ConvertTo-Json -Compress))
"""
FAKE_NATIVE = r"""
import json
import os
import sys
from pathlib import Path
fixture = json.loads(Path(os.environ["TEMPORAL_SYNTHETIC_DOCKER_FIXTURE"]).read_text())
# The unchanged first Docker argument selects this private Python script.
if sys.argv != fixture["arguments"]:
    sys.exit(91)
with Path(os.environ["TEMPORAL_SYNTHETIC_DOCKER_CALLS"]).open("a") as calls:
    calls.write("called\n")
for message in fixture["errors"]:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
for line in fixture["stdout"]:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
sys.exit(fixture["exitCode"])
"""


async def run(arguments: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    return process.returncode, stdout.decode(), stderr.decode()


class InspectDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        executable = shutil.which("pwsh")
        if executable is None:
            raise RuntimeError("PowerShell is required")
        cls.pwsh = str(Path(executable).resolve(strict=True))

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="temporal-diagnostic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = self.root / "runner.ps1"
        self.runner.write_text(RUNNER)
        self.fixture = self.root / "fixture.json"
        self.calls = self.root / "calls.txt"
        self.native = self.root / ARGUMENTS[0]
        self.native.write_text(FAKE_NATIVE)

    def check(self, *, kind: str = "function", **changes) -> tuple[dict, dict]:
        fixture = {
            "kind": kind,
            "nativeExecutable": sys.executable,
            "nativeDirectory": str(self.root),
            "nativeErrors": False,
            "errorAction": "Stop",
            "arguments": ARGUMENTS,
            "errors": [],
            "stdout": ['{"ok":true}'],
            "exitCode": 0,
            "throws": False,
            "writerFailure": False,
            "classifierFailure": False,
        }
        fixture.update(changes)
        self.fixture.write_text(json.dumps(fixture))
        if self.calls.exists():
            self.calls.unlink()
        env = os.environ.copy()
        for variable in DOCKER_ENV:
            env.pop(variable, None)
        env["PATH"] = str(self.root)
        env["XDG_CACHE_HOME"] = str(self.root / "cache")
        env["XDG_CONFIG_HOME"] = str(self.root / "config")
        env["TEMPORAL_SYNTHETIC_DOCKER_FIXTURE"] = str(self.fixture)
        env["TEMPORAL_SYNTHETIC_DOCKER_CALLS"] = str(self.calls)
        if fixture.get("environmentSet"):
            env.update({name: PRIVATE for name in DOCKER_ENV})
        code, stdout, stderr = asyncio.run(
            run(
                [
                    self.pwsh,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(self.runner),
                    str(HELPER),
                    str(self.fixture),
                ],
                env,
            )
        )
        self.assertEqual(code, 0, stdout + stderr)
        self.assertNotIn(PRIVATE, stdout + stderr)
        self.assertNotIn(str(self.root), stdout + stderr)
        self.assertNotIn(ARGUMENTS[-1], stdout + stderr)
        result = json.loads(stdout)
        self.assertEqual(result["nativeErrors"], fixture["nativeErrors"])
        self.assertEqual(result["errorAction"], fixture["errorAction"])
        self.assertEqual(result["calls"], 1 if kind == "function" else 0)
        if kind == "native-alias":
            self.assertEqual(self.calls.read_text(), "called\n")
        if not stderr:
            return result, {}
        lines = stderr.splitlines()
        self.assertEqual(len(lines), 1, stderr)
        self.assertTrue(lines[0].startswith(PREFIX + " "), stderr)
        fields = dict(item.split("=", 1) for item in lines[0].split()[1:])
        allowed = {
            "phase": {"temporal-server-image"},
            "result": {"command-failed", "invalid-output-shape", "invalid-json"},
            "error_class": {
                "none",
                "unknown",
                "format-template",
                "missing-object",
                "daemon-unreachable",
                "access-denied",
                "context-unavailable",
                "client-api",
                "tls",
                "multiple",
                "bounded",
                "command-unavailable",
            },
            "error_present": {"True", "False"},
            "error_capped": {"True", "False"},
            "command_threw": {"True", "False"},
            "exit": {"zero", "nonzero", "unavailable"},
            "platform": {"windows", "linux", "macos", "other"},
            "edition": {"core", "desktop", "other"},
            "native_errors": {"enabled", "disabled", "unavailable"},
            "error_action": {"stop", "continue", "other"},
            "docker_command": {
                "application",
                "function",
                "alias",
                "other",
                "unresolved",
            },
            **{name.lower() + "_set": {"True", "False"} for name in DOCKER_ENV},
        }
        self.assertEqual(set(fields), set(allowed))
        for name, value in fields.items():
            self.assertIn(value, allowed[name], (name, value))
        return result, fields

    def test_function_diagnostics_classify_errors_without_changing_arguments(
        self,
    ) -> None:
        cases = {
            "format-template": "template parsing error: can't evaluate field Id in type fixture",
            "missing-object": "Error response from daemon: No such image: fixture",
            "daemon-unreachable": "Cannot connect to the Docker daemon. Is the docker daemon running?",
            "access-denied": "permission denied while trying to connect",
            "context-unavailable": "context fixture does not exist",
            "client-api": "client version is too old",
            "tls": "x509: certificate signed by unknown authority",
            "unknown": "unrecognized daemon message",
        }
        for expected, message in cases.items():
            with self.subTest(expected=expected):
                result, fields = self.check(
                    errors=[message + " " + PRIVATE], exitCode=5
                )
                self.assertFalse(result["accepted"])
                self.assertTrue(result["fixedThrow"])
                self.assertEqual(result["lastExitCode"], 5)
                self.assertEqual(fields["error_class"], expected)
                self.assertEqual(fields["result"], "command-failed")
                self.assertEqual(fields["docker_command"], "function")

    def test_warning_stderr_does_not_change_success(self) -> None:
        for errors in ([PRIVATE], [PRIVATE] * 10, [PRIVATE + "x" * 9000]):
            with self.subTest(length=len(errors)):
                result, fields = self.check(errors=errors)
                self.assertTrue(result["accepted"])
                self.assertEqual(result["lastExitCode"], 0)
                self.assertEqual(fields, {})

    def test_stdout_shape_and_json_failures_stay_separate_from_stderr(self) -> None:
        for stdout, expected in (
            ([], "invalid-output-shape"),
            (["{}", "{}"], "invalid-output-shape"),
            ([PRIVATE], "invalid-json"),
        ):
            with self.subTest(expected=expected, stdout=stdout):
                result, fields = self.check(stdout=stdout, errors=[PRIVATE])
                self.assertFalse(result["accepted"])
                self.assertTrue(result["fixedThrow"])
                self.assertEqual(fields["result"], expected)
                self.assertEqual(result["lastExitCode"], 0)

    def test_bounded_records_characters_and_ambiguous_categories(self) -> None:
        for errors, expected in (
            ([PRIVATE] * 9, "bounded"),
            ([PRIVATE + "x" * 2048], "bounded"),
            (["x" * 2048] * 5, "bounded"),
            (["No such image: " + PRIVATE, "permission denied " + PRIVATE], "multiple"),
        ):
            with self.subTest(expected=expected, records=len(errors)):
                result, fields = self.check(errors=errors, exitCode=5)
                self.assertTrue(result["fixedThrow"])
                self.assertEqual(fields["error_class"], expected)
                self.assertEqual(fields["error_capped"], str(expected == "bounded"))

    def test_context_reports_only_presence_not_environment_values(self) -> None:
        for present in (False, True):
            with self.subTest(present=present):
                _, fields = self.check(exitCode=5, environmentSet=present)
                for variable in DOCKER_ENV:
                    self.assertEqual(fields[variable.lower() + "_set"], str(present))

    def test_terminating_mock_error_is_fixed_and_does_not_report_stale_exit(
        self,
    ) -> None:
        result, fields = self.check(throws=True)
        self.assertFalse(result["accepted"])
        self.assertTrue(result["fixedThrow"])
        self.assertEqual(result["lastExitCode"], 77)
        self.assertEqual(fields["command_threw"], "True")
        self.assertEqual(fields["exit"], "unavailable")

    def test_classifier_failure_cannot_change_acceptance_or_fixed_failure(self) -> None:
        for exit_code in (0, 5):
            with self.subTest(exit_code=exit_code):
                result, fields = self.check(
                    exitCode=exit_code, errors=[PRIVATE], classifierFailure=True
                )
                self.assertEqual(result["accepted"], exit_code == 0)
                self.assertEqual(result["fixedThrow"], exit_code != 0)
                self.assertEqual(result["lastExitCode"], exit_code)
                if fields:
                    self.assertEqual(fields["error_class"], "unknown")

        result, fields = self.check(throws=True, classifierFailure=True)
        self.assertFalse(result["accepted"])
        self.assertTrue(result["fixedThrow"])
        self.assertEqual(result["lastExitCode"], 77)
        self.assertEqual(fields["error_class"], "unknown")
        self.assertEqual(fields["exit"], "unavailable")

    def test_broken_diagnostic_writer_cannot_change_fixed_failure(self) -> None:
        result, fields = self.check(exitCode=5, errors=[PRIVATE], writerFailure=True)
        self.assertFalse(result["accepted"])
        self.assertTrue(result["fixedThrow"])
        self.assertEqual(result["lastExitCode"], 5)
        self.assertEqual(fields, {})

    def test_native_stderr_success_and_failure_preserve_all_preference_modes(
        self,
    ) -> None:
        for native_errors in (False, True):
            for error_action in ("Stop", "Continue"):
                for exit_code in (0, 17):
                    with self.subTest(
                        native_errors=native_errors,
                        error_action=error_action,
                        exit_code=exit_code,
                    ):
                        result, fields = self.check(
                            kind="native-alias",
                            nativeErrors=native_errors,
                            errorAction=error_action,
                            exitCode=exit_code,
                            errors=["template parsing error " + PRIVATE],
                        )
                        self.assertEqual(result["accepted"], exit_code == 0)
                        self.assertEqual(result["fixedThrow"], exit_code != 0)
                        self.assertEqual(result["lastExitCode"], exit_code)
                        if exit_code == 0:
                            self.assertEqual(fields, {})
                        else:
                            self.assertEqual(fields["error_class"], "format-template")
                            self.assertEqual(fields["docker_command"], "alias")
                            self.assertEqual(
                                fields["command_threw"],
                                str(native_errors and error_action == "Stop"),
                            )

    def test_native_multiline_and_oversized_unknown_stderr(self) -> None:
        for errors, expected in (
            (["No such image: " + PRIVATE] * 2, "missing-object"),
            ([PRIVATE], "unknown"),
            ([PRIVATE + "x" * 9000], "bounded"),
            ([PRIVATE] * 9, "bounded"),
        ):
            with self.subTest(expected=expected):
                result, fields = self.check(
                    kind="native-alias", errors=errors, exitCode=17, nativeErrors=True
                )
                self.assertTrue(result["fixedThrow"])
                self.assertEqual(fields["error_class"], expected)


if __name__ == "__main__":
    unittest.main()
