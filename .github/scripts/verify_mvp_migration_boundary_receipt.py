import os
import stat
import sys
from pathlib import Path

from defusedxml import ElementTree as ET

path = Path(sys.argv[1])
max_receipt_bytes = 1_048_576
try:
    receipt_fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(receipt_fd, "rb") as receipt_file:
        opened_stat = os.fstat(receipt_file.fileno())
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_size > max_receipt_bytes
        ):
            raise ValueError
        receipt_bytes = receipt_file.read(max_receipt_bytes + 1)
        final_stat = os.fstat(receipt_file.fileno())
    if (
        len(receipt_bytes) > max_receipt_bytes
        or len(receipt_bytes) != opened_stat.st_size
        or final_stat.st_size != opened_stat.st_size
        or final_stat.st_mtime_ns != opened_stat.st_mtime_ns
        or final_stat.st_ctime_ns != opened_stat.st_ctime_ns
    ):
        raise ValueError
except (OSError, ValueError):
    raise SystemExit("Baseline boundary receipt missing or oversized") from None
root = ET.fromstring(
    receipt_bytes,
    forbid_dtd=True,
    forbid_entities=True,
    forbid_external=True,
)
suites = list(root.iter("testsuite"))
cases = list(root.iter("testcase"))
expected = "test_baseline_upgrades_an_empty_database_and_refuses_its_downgrade"
if (
    len(suites) != 1
    or suites[0].get("tests") != "1"
    or any(suites[0].get(key) != "0" for key in ("failures", "errors", "skipped"))
    or len(cases) != 1
    or cases[0].get("classname") != "tests.integration.test_migration_roundtrip"
    or cases[0].get("name") != expected
    or any(list(root.iter(tag)) for tag in ("failure", "error", "skipped"))
):
    raise SystemExit("Baseline boundary receipt incomplete or unsuccessful")
print("MVP_BASELINE_BOUNDARY_VERIFIED_PASS 1")
