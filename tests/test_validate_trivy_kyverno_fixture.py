from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = TEST_ROOT / "scripts" / "quality" / "validate_trivy_kyverno_fixture.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_trivy_kyverno_fixture", VALIDATOR_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load fixture validator")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

SOURCE_ROOT = TEST_ROOT
SOURCE_FIXTURE = SOURCE_ROOT / validator.EXPECTED_FIXTURE.as_posix()
SOURCE_POLICY = SOURCE_ROOT / ".trivyignore.yaml"


def _entry(finding: tuple[str, str, int, int]) -> dict[str, object]:
    rule_id, severity, start, end = finding
    return {
        "ID": rule_id,
        "Severity": severity,
        "CauseMetadata": {"StartLine": start, "EndLine": end},
    }


class TrivyFixtureValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        fixture = self.root / validator.EXPECTED_FIXTURE.as_posix()
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(SOURCE_FIXTURE.read_bytes())
        (self.root / ".trivyignore.yaml").write_bytes(SOURCE_POLICY.read_bytes())
        self.target = fixture
        self.report = Path(self.temp.name) / "trivy.json"
        self.write_report()

    def write_report(self, findings=None, target="host-access.yaml") -> None:
        if findings is None:
            findings = list(validator.EXPECTED_RAW_FINDINGS.elements())
        payload = {
            "Results": [
                {
                    "Target": target,
                    "Misconfigurations": [_entry(item) for item in findings],
                }
            ]
        }
        self.report.write_text(json.dumps(payload), encoding="utf-8")

    def validate(self, today=date(2026, 10, 23), target=None) -> None:
        validator.validate_preflight(
            self.root,
            self.target if target is None else target,
            self.report,
            today=today,
        )

    def test_exact_source_policy_and_report_pass(self) -> None:
        self.validate()

    def test_expiry_must_be_live_and_within_30_days(self) -> None:
        validator.validate_expiry(date(2026, 10, 23))
        with self.assertRaisesRegex(validator.ValidationError, "expired"):
            validator.validate_expiry(date(2026, 11, 22))
        with self.assertRaisesRegex(validator.ValidationError, "30 days"):
            validator.validate_expiry(date(2026, 10, 22))

    def test_malformed_json_fails(self) -> None:
        self.report.write_text("{not-json", encoding="utf-8")
        with self.assertRaisesRegex(validator.ValidationError, "malformed"):
            self.validate()

    def test_malformed_finding_location_fails(self) -> None:
        findings = list(validator.EXPECTED_RAW_FINDINGS.elements())
        findings[0] = ("KSV-0008", "HIGH", 0, 35)
        self.write_report(findings)
        payload = json.loads(self.report.read_text(encoding="utf-8"))
        payload["Results"][0]["Misconfigurations"][0]["CauseMetadata"]["StartLine"] = (
            "30"
        )
        self.report.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(validator.ValidationError, "malformed line range"):
            self.validate()

    def test_missing_finding_fails(self) -> None:
        findings = list(validator.EXPECTED_RAW_FINDINGS.elements())
        findings.pop()
        self.write_report(findings)
        with self.assertRaisesRegex(validator.ValidationError, "multiset differs"):
            self.validate()

    def test_duplicate_finding_fails(self) -> None:
        findings = list(validator.EXPECTED_RAW_FINDINGS.elements())
        findings.append(findings[0])
        self.write_report(findings)
        with self.assertRaisesRegex(validator.ValidationError, "multiset differs"):
            self.validate()

    def test_appended_extra_finding_fails(self) -> None:
        findings = list(validator.EXPECTED_RAW_FINDINGS.elements())
        findings.append(("KSV-9999", "HIGH", 103, 105))
        self.write_report(findings)
        with self.assertRaisesRegex(validator.ValidationError, "multiset differs"):
            self.validate()

    def test_changed_fixture_fails(self) -> None:
        self.target.write_bytes(self.target.read_bytes() + b"\n# changed\n")
        with self.assertRaisesRegex(validator.ValidationError, "fixture SHA-256"):
            self.validate()

    def test_altered_ignore_policy_fails(self) -> None:
        policy = self.root / ".trivyignore.yaml"
        policy.write_bytes(policy.read_bytes() + b"# changed\n")
        with self.assertRaisesRegex(validator.ValidationError, "ignore policy SHA-256"):
            self.validate()

    def test_target_outside_root_fails(self) -> None:
        outside = Path(self.temp.name) / "outside.yaml"
        outside.write_bytes(SOURCE_FIXTURE.read_bytes())
        with self.assertRaisesRegex(
            validator.ValidationError, "outside repository root"
        ):
            self.validate(target=outside)

    def test_report_target_path_traversal_fails(self) -> None:
        self.write_report(target="../host-access.yaml")
        with self.assertRaisesRegex(validator.ValidationError, "single-file target"):
            self.validate()

    def test_report_must_have_one_result(self) -> None:
        self.write_report()
        payload = json.loads(self.report.read_text(encoding="utf-8"))
        payload["Results"].append(payload["Results"][0])
        self.report.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            validator.ValidationError, "exactly the single-file"
        ):
            self.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
