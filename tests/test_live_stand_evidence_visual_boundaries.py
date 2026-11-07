"""Focused acceptance boundaries for the extracted Playwright evidence parsers."""

from __future__ import annotations

from pathlib import Path

from scripts import live_stand_playwright_evidence as evidence
from tests import test_live_stand as contracts


def _contrast_row(project: str, route: str, foreground: str, ratio: int) -> str:
    return (
        f"UE_LIVE_A11Y_CONTRAST_V1 project={project} route={route} "
        f"fg={foreground} bg=#000000 ratio_milli={ratio}\n"
    )


def test_a11y_contrasts_normalize_duplicates_and_stop_at_the_protocol_cap() -> None:
    rows: list[str] = []
    expected: list[tuple[str, str, str, str, int]] = []
    for project in ("desktop", "mobile"):
        for route in ("dashboard", "settings"):
            for ratio in range(1000, 1004):
                foreground = "#AABBCC" if not expected else "#aabbcc"
                row = _contrast_row(project, route, foreground, ratio)
                rows.append(row)
                expected.append((project, route, "#aabbcc", "#000000", ratio))
                if len(expected) == 1:
                    # Color case is normalized before duplicate identity is checked.
                    rows.append(_contrast_row(project, route, "#aabbcc", ratio))

    parsed = evidence._live_playwright_a11y_contrasts("".join(rows))

    assert parsed == expected
    assert len(parsed) == 16


def test_a11y_paint_states_accept_each_route_cap_and_stop_at_global_cap() -> None:
    rows: list[str] = []
    expected: list[tuple[str, str, int]] = []
    for project in ("desktop", "mobile"):
        for route in ("dashboard", "settings"):
            for ratio in range(3040, 3044):
                rows.append(
                    contracts._a11y_paint_row(
                        project=project, route=route, ratio_milli=str(ratio)
                    )
                )
                expected.append((project, route, ratio))

    parsed = evidence._live_playwright_a11y_paint_states("".join(rows))

    assert [(record[0], record[1], record[4]) for record in parsed] == expected
    assert len(parsed) == 16


def test_a11y_phase_states_accept_each_closed_route_phase_once() -> None:
    rows: list[str] = []
    expected: list[tuple[str, str, str, bool, int, int, int, str, int]] = []
    for project in ("desktop", "mobile"):
        for route in ("dashboard", "settings"):
            before = contracts._a11y_phase_row(project=project, route=route)
            rows.append(before)
            expected.append(
                (project, route, "before_axe", True, 900, 1000, 800, "opacity", 2)
            )
            # The first sample is authoritative for this route and phase.
            rows.append(
                contracts._a11y_phase_row(
                    project=project,
                    route=route,
                    page_opacity_milli="700",
                )
            )
            rows.append(
                contracts._a11y_phase_row(
                    project=project,
                    route=route,
                    phase="after_axe",
                    page_opacity_milli="1000",
                    animation="none",
                    active_animations="0",
                )
            )
            expected.append(
                (project, route, "after_axe", True, 1000, 1000, 800, "none", 0)
            )

    parsed = evidence._live_playwright_a11y_phase_states("".join(rows))

    assert parsed == expected
    assert len(parsed) == 8


def test_footer_geometries_skip_duplicates_and_stop_at_the_protocol_cap() -> None:
    widths = [390_000 + offset * 1_000 for offset in range(16)]
    rows = [
        contracts._footer_geometry_row(
            req_w_milli=str(widths[0]),
            inner_w_milli=str(widths[0]),
            client_w_milli=str(widths[0]),
            scroll_w_milli=str(widths[0]),
            nav_right_milli=str(widths[0]),
            nav_width_milli=str(widths[0]),
        )
    ]
    rows.append(rows[0])
    rows.extend(
        contracts._footer_geometry_row(
            req_w_milli=str(width),
            inner_w_milli=str(width),
            client_w_milli=str(width),
            scroll_w_milli=str(width),
            nav_right_milli=str(width),
            nav_width_milli=str(width),
        )
        for width in widths[1:]
    )
    overflow_width = 406_000
    rows.append(
        contracts._footer_geometry_row(
            req_w_milli=str(overflow_width),
            inner_w_milli=str(overflow_width),
            client_w_milli=str(overflow_width),
            scroll_w_milli=str(overflow_width),
            nav_right_milli=str(overflow_width),
            nav_width_milli=str(overflow_width),
        )
    )

    parsed = evidence._live_playwright_footer_geometries("".join(rows))

    assert [record[1] for record in parsed] == widths
    assert len(parsed) == 16


def test_news_viewports_keep_first_geometry_per_project_language_width() -> None:
    first = contracts._news_viewport_row()
    duplicate_key = contracts._news_viewport_row(scrollY="15", top="6", bottom="40")
    invalid = contracts._news_viewport_row(bottom="-5")
    second_key = contracts._news_viewport_row(language="en")

    parsed = evidence._live_playwright_news_viewports(
        first + duplicate_key + invalid + second_key
    )

    assert parsed == [
        ("desktop", "ru", 390, 900, -12, -4, 22, 0, 390),
        ("desktop", "en", 390, 900, -12, -4, 22, 0, 390),
    ]


def test_retry_decisions_skip_invalid_and_duplicate_records_before_the_cap() -> None:
    rows = [
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout "
        "retry_after_seconds=1 decision=not-retried remaining_ms=1\n"
    ]
    expected: list[tuple[str, str, int, str, int]] = []
    for remaining in range(1, 33):
        row = (
            "UE_LIVE_RETRY_V1 project=desktop check=auth-logout "
            f"retry_after_seconds=1 decision=retry remaining_ms={remaining}\n"
        )
        rows.append(row)
        expected.append(("desktop", "auth-logout", 1, "retry", remaining))
        if remaining == 1:
            rows.append(row)
    rows.append(
        "UE_LIVE_RETRY_V1 project=desktop check=auth-logout "
        "retry_after_seconds=1 decision=retry remaining_ms=33\n"
    )

    parsed = evidence._live_playwright_retry_decisions("".join(rows))

    assert parsed == expected
    assert len(parsed) == 32


def test_rate_limit_headers_reject_inconsistent_pairs_and_deduplicate() -> None:
    rows = [
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout "
        "x_ratelimit_limit=5 x_ratelimit_remaining=6\n"
    ]
    expected: list[tuple[str, int, int]] = []
    for limit in range(1, 33):
        row = (
            "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout "
            f"x_ratelimit_limit={limit} x_ratelimit_remaining=0\n"
        )
        rows.append(row)
        expected.append(("desktop", limit, 0))
        if limit == 1:
            rows.append(row)
    rows.append(
        "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout "
        "x_ratelimit_limit=33 x_ratelimit_remaining=0\n"
    )

    parsed = evidence._live_playwright_rate_limit_headers("".join(rows))

    assert parsed == expected
    assert len(parsed) == 32


def test_page_error_details_require_nonzero_source_location_for_known_sources() -> None:
    summary = (
        "UE_LIVE_PAGE_ERROR_V1 project=desktop check=map-gesture page=map "
        "type=type-error count=2\n"
    )
    valid = contracts._page_error_detail_row()
    zero_line = contracts._page_error_detail_row(line="0")

    assert evidence._live_playwright_page_error_details(summary + valid) == [
        ("desktop", "map-gesture", "map", "type-error", "map-worker", 17, 4, 2)
    ]
    assert evidence._live_playwright_page_error_details(summary + zero_line) == []


def test_failure_locations_deduplicate_public_headers_and_keep_later_location(
    tmp_path: Path,
) -> None:
    source_name = contracts.live_stand.LIVE_E2E_SMOKE_FILES[0]
    source = tmp_path / source_name
    source.parent.mkdir(parents=True)
    source.write_text(
        "export const first = 1;\nexport const second = 2;\n", encoding="utf-8"
    )
    first = f"  1) [desktop] › {source_name}:1:1 › private title\n"
    second = f"  2) [mobile] › {source_name}:2:1 › another private title\n"

    parsed = evidence._live_playwright_failure_locations(
        first + first + second, cwd=tmp_path
    )

    assert parsed == [
        ("desktop", source_name, 1, "declaration"),
        ("mobile", source_name, 2, "declaration"),
    ]
