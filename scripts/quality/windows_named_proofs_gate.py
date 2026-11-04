"""Fail-closed JUnit gate for the named native Windows audit proofs."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

OWNER = "tests.test_start_docker_live_owner_key_paths"
STATE = "tests.test_start_docker_live_stand_state_root"
PROBE = "tests.test_symlink_privilege_probe_contract"
TIMEOUT = "tests.test_live_stand_subprocess_timeouts"
REQUIRED = frozenset(
    {
        (OWNER, "test_common_git_metadata_rejects_reparse_directory_when_supported"),
        (OWNER, "test_worktree_owner_rejects_reparse_common_key_when_supported"),
        (
            STATE,
            "test_live_stand_uses_system32_acl_tools_when_git_usr_bin_precedes_path",
        ),
        (PROBE, "test_file_symlink_probe_reports_unprivileged_creation_as_unsupported"),
        (
            PROBE,
            "test_directory_symlink_probe_reports_unprivileged_creation_as_unsupported",
        ),
        (PROBE, "test_probe_flags_match_the_native_symlink_capability"),
        (PROBE, "test_every_when_supported_symlink_test_is_probe_gated"),
        (PROBE, "test_census_detects_an_ungated_when_supported_symlink_test"),
        (TIMEOUT, "test_every_live_stand_subprocess_call_declares_a_timeout"),
        (TIMEOUT, "test_generic_live_stand_command_timeout_becomes_a_stand_error"),
        (TIMEOUT, "test_git_probe_timeout_becomes_a_stand_error"),
        (TIMEOUT, "test_playwright_timeout_becomes_a_stand_error"),
        (
            TIMEOUT,
            "test_native_lifecycle_lock_contends_and_recovers_after_release[worktree]",
        ),
        (
            TIMEOUT,
            "test_native_lifecycle_lock_contends_and_recovers_after_release[in-place]",
        ),
        (TIMEOUT, "test_windows_lifecycle_lock_wait_is_bounded"),
        (
            "tests.test_windows_live_native_subprocess",
            "test_subprocess_timeout_terminates_native_child",
        ),
        (
            "tests.test_windows_live_native_subprocess",
            "test_subprocess_success_completes_native_child",
        ),
    }
)


def validate(path: Path) -> int:
    root = SafeElementTree.parse(path).getroot()
    if root.tag == "testsuite":
        suites = [root]
    elif (
        root.tag == "testsuites"
        and len(root)
        and all(item.tag == "testsuite" for item in root)
    ):
        suites = list(root)
    else:
        raise ValueError("invalid JUnit root")
    seen: set[tuple[str, str]] = set()
    for suite in suites:
        counts: dict[str, int] = {}
        for field in ("tests", "skipped", "failures", "errors"):
            value = suite.get(field)
            if value is None or not value.isascii() or not value.isdecimal():
                raise ValueError("invalid JUnit count")
            counts[field] = int(value)
        if counts["skipped"] or counts["failures"] or counts["errors"]:
            raise ValueError("JUnit reports non-passing tests")
        if any(
            child.tag not in {"testcase", "properties", "system-out", "system-err"}
            for child in suite
        ):
            raise ValueError("invalid JUnit suite child")
        cases = suite.findall("testcase")
        if counts["tests"] != len(cases):
            raise ValueError("JUnit testcase count mismatch")
        for case in cases:
            identity = (case.get("classname", ""), case.get("name", ""))
            if not all(identity) or identity in seen:
                raise ValueError("missing or duplicate testcase identity")
            if any(child.tag in {"skipped", "failure", "error"} for child in case):
                raise ValueError("JUnit testcase did not pass")
            seen.add(identity)
    if not REQUIRED.issubset(seen):
        raise ValueError("named Windows proof is missing")
    return len(seen)


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("exactly one JUnit path is required")
        count = validate(Path(sys.argv[1]))
    except (OSError, ET.ParseError, DefusedXmlException, ValueError) as error:
        print(f"Windows named proof gate failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Windows named proof gate: {count} passed, all {len(REQUIRED)} named cases present."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
