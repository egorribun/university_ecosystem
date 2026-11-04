"""Behavioral tests for the isolated Caddy vulnerability gate."""

import copy
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = "github.com/university-ecosystem/caddy"


def messages():
    return [
        {
            "config": {
                "protocol_version": "v1.0.0",
                "scanner_name": "govulncheck",
                "scanner_version": "v1.8.0",
                "scan_level": "symbol",
                "scan_mode": "source",
                "go_version": "go1.26.10",
                "db": "https://vuln.go.dev",
            }
        },
        {
            "SBOM": {
                "go_version": "go1.26.10",
                "roots": [MODULE],
                "modules": [{"path": MODULE}],
            }
        },
    ]


def finding(
    alias="GHSA-mgcc-cww5-fp2q",
    module="github.com/go-jose/go-jose/v3",
    version="v3.0.5",
    function="ParseSigned",
):
    frame = {"module": module, "version": version}
    if function is not None:
        frame.update(package=module, function=function)
    return [
        {"osv": {"id": "GO-2099-1000", "aliases": [alias]}},
        {"finding": {"osv": "GO-2099-1000", "trace": [frame]}},
    ]


class CaddyReportTests(unittest.TestCase):
    def validator(self):
        self.assertTrue(
            (ROOT / "scripts/quality/check_caddy_govulncheck.py").is_file(),
            "Caddy has no fail-closed vulnerability report validator",
        )
        return importlib.import_module("scripts.quality.check_caddy_govulncheck")

    def check(self, records=None, status=0, today=date(2026, 11, 4)):
        gate = self.validator()
        text = "\n".join(json.dumps(record) for record in records or messages())
        return gate.validate_report(text, status, today=today)

    def reject(self, records, status=0):
        gate = self.validator()
        with self.assertRaises(gate.ReportError):
            self.check(records, status)

    def test_clean_symbol_scan_passes(self):
        self.assertEqual(self.check(), {"reachable": 0, "accepted": 0})

    def test_each_existing_exception_is_bounded(self):
        for alias in (
            "GHSA-mgcc-cww5-fp2q",
            "GHSA-4w3g-jfj2-cw2q",
            "GHSA-vvm8-gf78-28g4",
        ):
            with self.subTest(alias=alias):
                self.assertEqual(
                    self.check(messages() + finding(alias)),
                    {"reachable": 1, "accepted": 1},
                )

    def test_exception_expiry_is_exclusive(self):
        records = messages() + finding()
        self.assertEqual(self.check(records, today=date(2027, 1, 9))["accepted"], 1)
        gate = self.validator()
        with self.assertRaises(gate.ReportError):
            self.check(records, today=date(2027, 1, 10))

    def test_other_advisory_package_or_version_blocks(self):
        for kwargs in (
            {"alias": "GHSA-abcd-1234-5678"},
            {"module": "example.com/other"},
            {"version": "v3.0.4"},
        ):
            with self.subTest(kwargs=kwargs):
                self.reject(messages() + finding(**kwargs))

    def test_unreachable_module_finding_is_not_a_symbol_failure(self):
        self.assertEqual(
            self.check(
                messages() + finding(alias="GHSA-abcd-1234-5678", function=None)
            ),
            {"reachable": 0, "accepted": 0},
        )

    def test_operational_exit_cannot_be_accepted_even_with_valid_exception(self):
        for status in (1, 2, 3, 124, -9):
            with self.subTest(status=status):
                self.reject(messages() + finding(), status=status)

    def test_bad_config_never_proves_symbol_scan(self):
        for key, value in (
            ("scan_level", "package"),
            ("scan_mode", "query"),
            ("protocol_version", "v2"),
            ("scanner_name", "other"),
            ("scanner_version", "v1.7.0"),
            ("go_version", "go1.25"),
            ("db", "https://example.com"),
        ):
            records = messages()
            records[0]["config"][key] = value
            with self.subTest(key=key):
                self.reject(records)

    def test_truncated_or_empty_report_blocks(self):
        gate = self.validator()
        for raw in ("", " ", "{", '{"config":', "null", "[]"):
            with self.subTest(raw=raw), self.assertRaises(gate.ReportError):
                gate.validate_report(raw, 0)

    def test_config_only_report_blocks(self):
        self.reject(messages()[:1])

    def test_wrong_scan_root_blocks(self):
        for roots in ([], ["example.com/other"], [MODULE, "example.com/extra"]):
            records = messages()
            records[1]["SBOM"]["roots"] = roots
            self.reject(records)

    def test_missing_module_or_wrong_toolchain_blocks(self):
        for key, value in (("modules", []), ("go_version", "go1.25")):
            records = messages()
            records[1]["SBOM"][key] = value
            self.reject(records)

    def test_missing_or_conflicting_osv_blocks(self):
        pair = finding()
        self.reject(messages() + pair[1:])
        conflicting = copy.deepcopy(pair[0])
        conflicting["osv"]["summary"] = "Different upstream record"
        self.reject(messages() + pair + [conflicting])

    def test_official_emitter_repeats_identical_osv_across_module_versions(self):
        pair = finding()
        records = [*messages(), pair[0], copy.deepcopy(pair[0]), pair[1]]
        self.assertEqual(self.check(records), {"reachable": 1, "accepted": 1})

    def test_conflicting_advisory_error_is_bounded_and_identifiable(self):
        pair = finding()
        conflict = copy.deepcopy(pair[0])
        conflict["osv"]["summary"] = "sensitive raw text not for logs"
        gate = self.validator()
        with self.assertRaises(gate.ReportError) as caught:
            self.check([*messages(), *pair, conflict])
        self.assertEqual(str(caught.exception), "Conflicting advisory: GO-2099-1000")

    def test_duplicate_never_merges_changed_advisory_fields(self):
        for field, value in (
            ("aliases", ["GHSA-abcd-1234-5678"]),
            ("affected", []),
            ("modified", "2099-01-01T00:00:00Z"),
        ):
            pair = finding()
            conflict = copy.deepcopy(pair[0])
            conflict["osv"][field] = value
            self.reject([*messages(), *pair, conflict])

    def test_identical_duplicates_do_not_accept_unknown_finding(self):
        pair = finding(alias="GHSA-abcd-1234-5678")
        self.reject([*messages(), pair[0], copy.deepcopy(pair[0]), pair[1]])

    def test_duplicate_compares_parsed_objects_not_key_order(self):
        pair = finding()
        reordered = {"osv": dict(reversed(list(pair[0]["osv"].items())))}
        self.assertEqual(self.check([*messages(), *pair, reordered])["accepted"], 1)

    def test_duplicate_keeps_json_value_types_distinct(self):
        for left, right in ((True, 1), (1, 1.0)):
            pair = finding()
            pair[0]["osv"]["database_specific"] = {"value": left}
            conflict = copy.deepcopy(pair[0])
            conflict["osv"]["database_specific"]["value"] = right
            self.reject([*messages(), *pair, conflict])

    def test_unknown_alias_cannot_expand_existing_exception(self):
        pair = finding()
        pair[0]["osv"]["aliases"].append("GHSA-abcd-1234-5678")
        self.reject(messages() + pair)

    def test_empty_or_malformed_trace_blocks(self):
        for trace in ([], None, [None], [{}], [{"module": "x", "function": 1}]):
            records = messages() + finding()
            records[-1]["finding"]["trace"] = trace
            self.reject(records)

    def test_progress_is_optional_and_osv_order_independent(self):
        pair = finding()
        self.assertEqual(
            self.check(
                [*messages(), {"progress": {"message": "Scanning"}}, *pair[::-1]]
            )["accepted"],
            1,
        )

    def test_duplicate_config_sbom_and_unknown_messages_block(self):
        for extra in (
            messages()[0],
            messages()[1],
            {"error": "load failed"},
            {"progress": {}, "finding": {}},
            {},
        ):
            self.reject([*messages(), extra])

    def test_duplicate_json_keys_block(self):
        gate = self.validator()
        with self.assertRaises(gate.ReportError):
            gate.validate_report('{"config": {}, "config": {}}', 0)

    def test_wrong_message_payload_and_order_block(self):
        self.reject(messages()[::-1])
        for payload in (None, [], "error"):
            self.reject([*messages(), {"progress": payload}])

    def test_untyped_status_is_not_success(self):
        for status in (False, True, "0", None):
            self.reject(messages(), status=status)

    def test_malformed_advisory_metadata_blocks(self):
        for key, value in (
            ("id", None),
            ("id", "other"),
            ("aliases", "GHSA-x"),
            ("aliases", [None]),
            ("aliases", [""]),
        ):
            records = messages() + finding()
            records[2]["osv"][key] = value
            self.reject(records)

    def test_missing_alias_cannot_authorize_exception(self):
        records = messages() + finding()
        records[2]["osv"].pop("aliases")
        self.reject(records)

    def test_oversized_report_is_not_accepted(self):
        gate = self.validator()
        with self.assertRaises(gate.ReportError):
            gate.validate_report(" " * (gate.MAX_REPORT_BYTES + 1), 0)

    def test_all_trace_frames_are_validated(self):
        records = messages() + finding()
        records[-1]["finding"]["trace"].append({"module": ""})
        self.reject(records)

    def test_mixed_lower_level_trace_cannot_hide_reachable_symbol(self):
        records = messages() + finding(function=None)
        records[-1]["finding"]["trace"].append(
            {"module": MODULE, "package": MODULE, "function": "main"}
        )
        self.reject(records)

    def test_symbol_without_package_blocks(self):
        records = messages() + finding()
        del records[-1]["finding"]["trace"][0]["package"]
        self.reject(records)

    def test_nonfinite_json_constants_block(self):
        gate = self.validator()
        for constant in ("NaN", "Infinity", "-Infinity"):
            text = "\n".join(map(json.dumps, messages()))
            text += '\n{"progress": {"time": ' + constant + "}}"
            with self.subTest(constant=constant), self.assertRaises(gate.ReportError):
                gate.validate_report(text, 0)

    def test_failure_diagnostics_are_useful_bounded_and_redacted(self):
        gate = self.validator()
        records = messages() + finding(alias="GHSA-abcd-1234-5678")
        trace = records[-1]["finding"]["trace"]
        trace[0]["position"] = {"filename": "/private/credential-source.py"}
        trace.extend([{"module": MODULE, "package": MODULE, "function": "main"}] * 40)
        records[-1]["finding"]["fixed_version"] = "v3.0.6"
        with self.assertRaises(gate.ReportError) as caught:
            self.check(records)
        diagnostic = str(caught.exception)
        self.assertIn('"fixed_version": "v3.0.6"', diagnostic)
        self.assertIn('"module": "github.com/go-jose/go-jose/v3"', diagnostic)
        self.assertIn('"trace_frames": 41', diagnostic)
        self.assertNotIn("credential-source", diagnostic)
        self.assertLess(len(diagnostic), 6000)
        records[-1]["finding"]["fixed_version"] = "unsafe\n::warning::payload"
        with self.assertRaises(gate.ReportError) as caught:
            self.check(records)
        self.assertNotIn("::warning::", str(caught.exception))

    def test_cli_rejects_missing_report(self):
        self.validator()
        result = subprocess.run(  # noqa: S603  # Fixed local validator, no external data in command.
            [
                sys.executable,
                "-m",
                "scripts.quality.check_caddy_govulncheck",
                "--report",
                "does-not-exist.json",
                "--scanner-status",
                "0",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Caddy vulnerability gate failed", result.stdout)

    def test_workflow_runs_isolated_gate_and_preserves_operational_failure(self):
        workflow_path = ROOT / ".github/workflows/reusable-security-audit.yml"
        self.assertTrue(workflow_path.is_file(), "Isolated Caddy scan is not wired")
        workflow = yaml.safe_load(workflow_path.read_text())
        steps = workflow["jobs"]["govulncheck"]["steps"]
        step = next(s for s in steps if s["name"] == "Scan isolated Caddy module")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            # The double is a POSIX launcher that re-execs the current interpreter,
            # so it runs under bash on Linux and Git Bash on Windows alike.
            scanner_py = temp / "govulncheck_double.py"
            scanner_py.write_text(
                "import json, os, sys\n"
                'assert os.environ["GOWORK"] == "off"\n'
                'assert os.environ["GOTOOLCHAIN"] == "local"\n'
                'assert os.environ["GOFLAGS"] == "-mod=readonly"\n'
                'assert os.environ["CGO_ENABLED"] == "0"\n'
                'assert sys.argv[1:] == ["-C", "services/caddy", "-format=json", '
                '"-mode=source", "-scan=symbol", "-tags=nobadger,nomysql,nopgx", "./..."]\n'
                'print(os.environ["FAKE_REPORT"])\n'
                'sys.exit(int(os.environ["FAKE_STATUS"]))\n',
                encoding="utf-8",
            )
            interpreter = Path(sys.executable).as_posix()
            scanner = temp / "govulncheck"
            scanner.write_text(
                f"#!/bin/sh\nexec '{interpreter}' '{scanner_py.as_posix()}' \"$@\"\n",
                encoding="utf-8",
                newline="\n",
            )
            scanner.chmod(0o700)
            # The step's report parser is invoked as `python3`; bind that name to
            # the interpreter running this test (the Windows Store alias is not one).
            python3 = temp / "python3"
            python3.write_text(
                f"#!/bin/sh\nexec '{interpreter}' \"$@\"\n",
                encoding="utf-8",
                newline="\n",
            )
            python3.chmod(0o700)
            bash = shutil.which("bash")
            if bash is None:
                self.fail(
                    "bash is required to execute the reviewed Caddy scan step; "
                    "install bash (Git Bash on Windows) and retry"
                )
            for status, expected in ((0, 0), (1, 1), (124, 1)):
                with self.subTest(status=status):
                    env = {
                        "PATH": f"{temp}{os.pathsep}{os.environ['PATH']}",
                        "RUNNER_TEMP": directory,
                        "FAKE_STATUS": str(status),
                        "FAKE_REPORT": "\n".join(map(json.dumps, messages())),
                    }
                    env.update(step["env"])
                    result = subprocess.run(  # noqa: S603  # fixed argv: resolved bash runs the reviewed workflow step
                        [bash, "-e"],
                        input=step["run"],
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode, expected, result.stdout + result.stderr
                    )


if __name__ == "__main__":
    unittest.main()
