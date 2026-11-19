from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests import test_live_stand as live_stand_tests

live_stand = live_stand_tests.live_stand
_SKIP_SOURCE = live_stand_tests._source_derived_live_skip_identities()[0][1]
_FAILURE_SOURCE = "tests/e2e-live/activity-dashboard.live.spec.ts"
_MISSING_FAILURE_SOURCE = "tests/e2e-live/totp-recovery.live.spec.ts"
_PUSH_FAILURE_SOURCE = "tests/e2e-live/push-delivery.live.spec.ts"


def _skip_row(
    index: int,
    *,
    source: str = _SKIP_SOURCE,
    line: int = 1,
    column: int = 1,
    project: str = "desktop",
    title: str = "reporter title withheld",
) -> str:
    return (
        f"  -  {index:>3} [{project}] \u203a {source}:{line}:{column} \u203a {title}\n"
    )


def _failure_header(
    index: int,
    *,
    source: str = _FAILURE_SOURCE,
    line: int = 1,
    column: int = 1,
    project: str = "desktop",
    title: str = "failure title withheld",
) -> str:
    return f"  {index}) [{project}] \u203a {source}:{line}:{column} \u203a {title}\n"


def _write_frontend_source(root: Path, source: str, lines: list[str]) -> Path:
    path = root / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_skip_parser_fails_closed_for_missing_root_and_scan_limit(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "frontend-that-is-not-present"
    assert live_stand._live_playwright_skipped_identities(
        _skip_row(1), cwd=missing_root
    ) == ([], 0, True)

    fixture_identity = live_stand_tests._source_derived_live_skip_identities()[0]
    canonical_row = live_stand_tests._live_skip_reporter_rows(
        [fixture_identity], title="bounded reporter fixture"
    )
    noisy_report = "ordinary reporter output\n" * 8192 + canonical_row
    assert live_stand._live_playwright_skipped_identities(
        noisy_report, cwd=live_stand_tests.ROOT / "frontend"
    ) == ([], 0, True)


def test_skip_parser_accepts_crlf_and_rejects_untrusted_reporter_rows() -> None:
    identity = live_stand_tests._source_derived_live_skip_identities()[0]
    canonical_row = live_stand_tests._live_skip_reporter_rows(
        [identity], title="skip reason withheld"
    )
    accepted = live_stand._live_playwright_skipped_identities(
        canonical_row.replace("\n", "\r\n"),
        cwd=live_stand_tests.ROOT / "frontend",
    )
    assert accepted == ([identity], 0, False)

    overlong_row = "  -    1 " + ("x" * 4090) + "\n"
    nonprintable_row = canonical_row.replace(
        "skip reason withheld", "skip reason\x01withheld"
    )
    malformed_header = (
        f"  -    2 [tablet] \u203a {_SKIP_SOURCE}:1:1 \u203a unsupported project\n"
    )
    assert live_stand._live_playwright_skipped_identities(
        overlong_row + nonprintable_row + malformed_header,
        cwd=live_stand_tests.ROOT / "frontend",
    ) == ([], 3, False)


@pytest.mark.parametrize(
    "source_fault",
    [
        "symlink",
        "outside-root",
        "invalid-utf8",
        "line-out-of-range",
        "not-a-test-declaration",
        "wrong-column",
    ],
)
def test_skip_parser_rejects_untrusted_source_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source_fault: str,
) -> None:
    source_path = _write_frontend_source(
        tmp_path, _SKIP_SOURCE, ['test("fixture", () => {})']
    )
    row_line = 1
    row_column = 1

    if source_fault == "symlink":
        original_is_symlink = Path.is_symlink

        def report_symlink(path: Path) -> bool:
            return path == source_path or original_is_symlink(path)

        monkeypatch.setattr(Path, "is_symlink", report_symlink)
    elif source_fault == "outside-root":
        original_resolve = Path.resolve
        escaped_path = tmp_path.parent / "outside-frontend-source.ts"

        def resolve_outside_source(path: Path, strict: bool = False) -> Path:
            if path == source_path:
                return escaped_path
            return original_resolve(path, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve_outside_source)
    elif source_fault == "invalid-utf8":
        source_path.write_bytes(b"\xff")
    elif source_fault == "line-out-of-range":
        row_line = 2
    elif source_fault == "not-a-test-declaration":
        source_path.write_text("const value = 1\n", encoding="utf-8")
    elif source_fault == "wrong-column":
        row_column = 2

    parsed = live_stand._live_playwright_skipped_identities(
        _skip_row(1, line=row_line, column=row_column), cwd=tmp_path
    )
    assert parsed == ([], 1, False)


def test_failure_diagnostics_retain_only_public_categories_and_matchers(
    tmp_path: Path,
) -> None:
    _write_frontend_source(tmp_path, _FAILURE_SOURCE, ["public fixture line"] * 3)
    markers = (
        "failure-title-withheld",
        "diagnostic detail withheld",
        "account label withheld",
    )
    output = (
        _failure_header(1, title=markers[0])
        + f"    Error: expect(unexpected).toHaveText() failed {markers[1]}\n"
        + _failure_header(2, line=2, project="mobile", title=markers[0])
        + "    Call log:\n"
        + f'      - waiting for page.getByText("{markers[2]}")\n'
        + "      - reporter detail withheld\n"
        + f"    Error: page.goto: {markers[1]}\n"
        + _failure_header(3, line=3, title=markers[0])
        + f"    Error: locator.click: {markers[1]}\n"
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)

    assert diagnostics == [
        ("desktop", _FAILURE_SOURCE, 1, "assertion", "other", "none"),
        ("mobile", _FAILURE_SOURCE, 2, "navigation", "none", "text"),
        ("desktop", _FAILURE_SOURCE, 3, "locator", "none", "none"),
    ]
    assert all(marker not in repr(diagnostics) for marker in markers)
    assert "reporter detail withheld" not in repr(diagnostics)


@pytest.mark.parametrize("project", ["desktop", "mobile"])
@pytest.mark.parametrize(
    "error_name",
    [
        "Error",
        "TimeoutError",
        "TargetClosedError",
        "AbortError",
        "TypeError",
        "RangeError",
    ],
)
@pytest.mark.parametrize(
    ("method", "category"),
    [
        ("launch", "browser_launch"),
        ("launchPersistentContext", "browser_persistent_launch"),
    ],
)
def test_push_failure_diagnostics_classify_bounded_browser_headers(
    tmp_path: Path, project: str, error_name: str, method: str, category: str
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    private = "private-browser-launch-detail"
    output = (
        _failure_header(1, source=_PUSH_FAILURE_SOURCE, project=project, title=private)
        + "\n"
        + f"    {error_name}: browserType.{method}: {private}\n"
        + f"    Browser logs: {private}\n"
        + f"        at {private}\n"
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)

    assert diagnostics == [(project, _PUSH_FAILURE_SOURCE, 1, category, "none", "none")]
    assert private not in repr(diagnostics)


@pytest.mark.parametrize(
    "line",
    [
        "    Error: browserType.launchPersistentContextExtra: private\n",
        "    Error: browserType.launchX: private\n",
        "    Error: browserType.launch private\n",
        "    Error: unrelated browserType.launch: private\n",
        "     Error: browserType.launch: private\n",
        "    Error: browserType.launch: \n",
        "    Error: browserType.launch: " + "x" * 1025 + "\n",
        "    Error: browserType.launch: unterminated",
        "    Error: unrelated\n    Error: browserType.launch: forged\n",
        "    Call log:\n    Error: browserType.launch: forged\n",
    ],
)
def test_push_failure_diagnostics_reject_browser_header_lookalikes(
    tmp_path: Path, line: str
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    output = _failure_header(1, source=_PUSH_FAILURE_SOURCE) + line

    assert live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path) == [
        ("desktop", _PUSH_FAILURE_SOURCE, 1, "unknown", "none", "none")
    ]


def test_push_failure_diagnostics_are_source_scoped_and_bound_private_reasons(
    tmp_path: Path,
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    _write_frontend_source(tmp_path, _FAILURE_SOURCE, ["public fixture line"])
    private = "private" + "x" * (1024 - len("private"))
    output = (
        _failure_header(1, source=_FAILURE_SOURCE)
        + f"    Error: browserType.launch: {private}\n"
        + _failure_header(2, source=_PUSH_FAILURE_SOURCE.replace("/", "\\"))
        + f"    Error: browserType.launchPersistentContext: {private}\n"
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)

    assert diagnostics == [
        ("desktop", _FAILURE_SOURCE, 1, "unknown", "none", "none"),
        (
            "desktop",
            _PUSH_FAILURE_SOURCE,
            1,
            "browser_persistent_launch",
            "none",
            "none",
        ),
    ]
    assert private not in repr(diagnostics)


def test_push_failure_diagnostics_classify_aggregate_launch_child(
    tmp_path: Path,
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    private = "private-aggregate-detail"
    output = (
        _failure_header(1, source=_PUSH_FAILURE_SOURCE, title=private)
        + "    AggregateError: \n"
        + f"        at {private}\n"
        + "\n"
        + f"    Error: browserType.launchPersistentContext: {private}\n"
        + f"    Browser logs: {private}\n"
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)

    assert diagnostics == [
        (
            "desktop",
            _PUSH_FAILURE_SOURCE,
            1,
            "browser_persistent_launch",
            "none",
            "none",
        )
    ]
    assert private not in repr(diagnostics)


@pytest.mark.parametrize(
    "body",
    [
        "    AggregateError: private\n\n"
        "    Error: browserType.launchPersistentContext: forged\n",
        "    AggregateError: \n"
        "    Error: browserType.launchPersistentContext: forged\n",
        "    AggregateError: \n\n    Error: browserType.launch: forged\n",
        "    AggregateError: \n\n"
        "    Error: browserType.launchPersistentContext: " + "x" * 1025 + "\n",
        "    AggregateError: \n\n"
        "    Error: another failure\n\n"
        "    Error: browserType.launchPersistentContext: forged\n",
        "    AggregateError: \n\n"
        "    Call log:\n\n"
        "    Error: browserType.launchPersistentContext: forged\n",
        "    AggregateError: \n\n"
        "    ordinary indented detail\n\n"
        "    Error: browserType.launchPersistentContext: forged\n",
        "    AggregateError: \n"
        "    ordinary indented detail\n\n"
        "    Error: browserType.launchPersistentContext: forged\n",
    ],
)
def test_push_failure_diagnostics_reject_aggregate_lookalikes(
    tmp_path: Path, body: str
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    output = _failure_header(1, source=_PUSH_FAILURE_SOURCE) + body

    assert live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path) == [
        ("desktop", _PUSH_FAILURE_SOURCE, 1, "runtime", "none", "none")
    ]


@pytest.mark.parametrize("control", ["\x00", "\r", "\x1b[31m"])
def test_push_failure_diagnostics_reject_control_characters(
    tmp_path: Path, control: str
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    output = (
        _failure_header(1, source=_PUSH_FAILURE_SOURCE)
        + f"    Error: browserType.launch: private{control}\n"
    )

    assert live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path) == []


def test_push_failure_diagnostic_runner_never_emits_private_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_frontend_source(tmp_path, _PUSH_FAILURE_SOURCE, ["public fixture line"])
    private = "private-path-or-token-detail"
    output = (
        _failure_header(1, source=_PUSH_FAILURE_SOURCE, title=private)
        + f"    Error: browserType.launch: {private}\n"
        + f"    Browser logs: {private}\n"
        + "1 failed\n"
    )
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(), 1, stdout=output.encode(), stderr=b""
    )
    live_stand_tests._patch_live_playwright_result(monkeypatch, completed)

    with pytest.raises(live_stand.StandError, match="exit code 1"):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="full")

    printed = capsys.readouterr()
    assert (
        f"live E2E diagnostic project=desktop source={_PUSH_FAILURE_SOURCE} line=1 "
        "category=browser_launch matcher=none locator=none"
    ) in printed.out.splitlines()
    assert private not in printed.out + printed.err
    assert printed.err == ""


def test_failure_diagnostics_clear_invalid_headers_and_locations(
    tmp_path: Path,
) -> None:
    _write_frontend_source(tmp_path, _FAILURE_SOURCE, ["short source line"])
    output = (
        _failure_header(1, source="tests/e2e-live/not-allowlisted.live.spec.ts")
        + "    Error: locator.click: unsupported source\n"
        + _failure_header(2, source=_MISSING_FAILURE_SOURCE)
        + "    Error: locator.click: missing source file\n"
        + _failure_header(3, line=99)
        + "    Error: locator.click: invalid line\n"
        + _failure_header(4, column=99)
        + "    Error: locator.click: invalid column\n"
        + _failure_header(5, title="valid header after rejected evidence")
        + "    Error: page.waitForURL: private destination omitted\n"
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)

    assert diagnostics == [
        ("desktop", _FAILURE_SOURCE, 1, "navigation", "none", "none")
    ]
    assert "unsupported source" not in repr(diagnostics)
    assert "missing source file" not in repr(diagnostics)
    assert "invalid line" not in repr(diagnostics)
    assert "invalid column" not in repr(diagnostics)
    assert "valid header after rejected evidence" not in repr(diagnostics)


def test_failure_diagnostics_stop_at_the_public_record_limit(
    tmp_path: Path,
) -> None:
    _write_frontend_source(tmp_path, _FAILURE_SOURCE, ["public fixture line"])
    output = "".join(
        _failure_header(index, title="bounded title withheld")
        + "    Error: locator.click: private detail withheld\n"
        for index in range(1, 258)
    )

    diagnostics = live_stand._live_playwright_failure_diagnostics(output, cwd=tmp_path)

    expected = ("desktop", _FAILURE_SOURCE, 1, "locator", "none", "none")
    assert len(diagnostics) == 256
    assert diagnostics[0] == expected
    assert diagnostics[-1] == expected
    assert "bounded title withheld" not in repr(diagnostics)
    assert "private detail withheld" not in repr(diagnostics)
