import sys
from pathlib import Path

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

try:
    receipt = Path(sys.argv[1])
    if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 131072:
        raise SystemExit(1)
    root = ET.parse(
        receipt,
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    ).getroot()
    if root.tag != "testsuites" or len(root) != 1:
        raise SystemExit(1)
    suite = root[0]
    if suite.tag != "testsuite" or any(
        suite.get(key) != value
        for key, value in {
            "tests": "1",
            "failures": "0",
            "errors": "0",
            "skipped": "0",
        }.items()
    ):
        raise SystemExit(1)
    cases = list(root.iter("testcase"))
    if len(cases) != 1 or (cases[0].get("classname"), cases[0].get("name")) != (
        "tests.aud178_449_gunicorn_proof",
        "test_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets",
    ):
        raise SystemExit(1)
    if any(list(root.iter(tag)) for tag in ("failure", "error", "skipped")):
        raise SystemExit(1)
except (OSError, ValueError, ET.ParseError, DefusedXmlException):
    raise SystemExit(1) from None
