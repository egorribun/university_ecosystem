import json
import sys
from pathlib import Path

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

try:
    report = Path(sys.argv[1])
    if (
        report.is_symlink()
        or not report.is_file()
        or not 0 < report.stat().st_size <= 1_048_576
    ):
        raise ValueError
    root = ElementTree.parse(
        report,
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    ).getroot()
    suites = list(root.iter("testsuite"))
    if len(suites) != 1:
        raise ValueError
    counts = {
        key: int(suites[0].get(key, "-1"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    if any(value < 0 or value > 7 for value in counts.values()):
        raise ValueError
    print("OWNED_RENDERER_POSTGRES_COUNTS " + json.dumps(counts, sort_keys=True))
    cases = list(root.iter("testcase"))
    identities = {(case.get("classname"), case.get("name")) for case in cases}
    names = {
        "test_owned_renderer_catalog_rejects_user_objects[" + kind + "]"
        for kind in ("relation", "routine", "type", "schema", "extension")
    }
    names.update(
        {
            "test_owned_live_renderer_root_lifecycle_cleans_up",
            "test_owned_live_renderer_create_collision_preserves_existing_database",
        }
    )
    expected_identities = {
        ("tests.test_alembic_live_sql_render", name) for name in names
    }
    expected = {"tests": 7, "failures": 0, "errors": 0, "skipped": 0}
    if len(cases) != 7 or identities != expected_identities or counts != expected:
        raise ValueError
    if any(list(root.iter(tag)) for tag in ("failure", "error", "skipped")):
        raise ValueError
except (OSError, ValueError, ElementTree.ParseError, DefusedXmlException):
    print("OWNED_RENDERER_POSTGRES_RECEIPT_REJECTED")
    raise SystemExit(1) from None
print("OWNED_RENDERER_POSTGRES_VERIFIED_PASS 7")
