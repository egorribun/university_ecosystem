"""Fail-closed boundaries for the live Playwright evidence protocols."""

from __future__ import annotations

from scripts import live_stand_playwright_evidence as evidence
from tests import test_live_stand as contracts


def test_map_zoom_diagnostics_accept_only_bounded_phase_and_duration_records() -> None:
    rows = (
        "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=1 total=2 "
        "step=0 phase=0 duration_ms=50\n"
        "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=2 total=2 "
        "step=2 phase=3 duration_ms=63\r\n"
        "UE_LIVE_MAP_ZOOM_V1 project=mobile attempt=1 sample=1 total=1 "
        "step=3 phase=4 duration_ms=60000\n"
    )
    assert evidence._live_playwright_map_zoom_tasks(rows) == [
        ("desktop", 0, 1, 2, 0, 0, 50),
        ("desktop", 0, 2, 2, 2, 3, 63),
        ("mobile", 1, 1, 1, 3, 4, 60000),
    ]


def test_map_zoom_diagnostics_reject_malformed_or_private_fields() -> None:
    row = (
        "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=1 total=2 "
        "step=2 phase=3 duration_ms=63\n"
    )
    replacements = (
        ("project=desktop", "project=other"),
        ("attempt=0", "attempt=2"),
        ("sample=1", "sample=9"),
        ("total=2", "total=0"),
        ("total=2", "total=1000"),
        ("sample=1 total=2", "sample=2 total=1"),
        ("step=2", "step=4"),
        ("step=2 phase=3", "step=0 phase=3"),
        ("step=2 phase=3", "step=2 phase=0"),
        ("step=2 phase=3", "step=2 phase=4"),
        ("phase=3", "phase=5"),
        ("duration_ms=63", "duration_ms=49"),
        ("duration_ms=63", "duration_ms=60001"),
        ("duration_ms=63", "duration_ms=063"),
        ("\n", " private-value\n"),
        ("\n", " " + "x" * 200 + "\n"),
        ("\n", ""),
        ("UE_LIVE", "private\rUE_LIVE"),
    )
    for old, new in replacements:
        assert evidence._live_playwright_map_zoom_tasks(row.replace(old, new)) == []


def test_map_zoom_diagnostics_deduplicate_by_attempt_and_sample() -> None:
    rows = []
    for project in ("desktop", "mobile"):
        for attempt in range(2):
            for sample in range(1, 9):
                row = (
                    f"UE_LIVE_MAP_ZOOM_V1 project={project} attempt={attempt} "
                    f"sample={sample} total=8 step=1 phase=1 duration_ms={50 + sample}\n"
                )
                rows.extend((row, row))
    parsed = evidence._live_playwright_map_zoom_tasks("".join(rows))
    assert len(parsed) == 32
    assert parsed[0] == ("desktop", 0, 1, 8, 1, 1, 51)
    assert parsed[-1] == ("mobile", 1, 8, 8, 1, 1, 58)


def test_map_zoom_diagnostics_reject_conflicting_totals_within_attempt() -> None:
    rows = (
        "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=1 total=2 "
        "step=1 phase=1 duration_ms=51\n"
        "UE_LIVE_MAP_ZOOM_V1 project=desktop attempt=0 sample=2 total=3 "
        "step=1 phase=2 duration_ms=52\n"
    )
    assert evidence._live_playwright_map_zoom_tasks(rows) == [
        ("desktop", 0, 1, 2, 1, 1, 51)
    ]


def test_story_memory_cycle_rejects_a_malformed_nested_sample() -> None:
    valid = contracts._story_memory_cycle_trace_record()
    samples = dict(valid["samples"])
    samples["baseline"] = []
    malformed = {**valid, "samples": samples}

    assert evidence._validated_story_memory_cycle_trace(malformed) is None
    rows = contracts._story_memory_cycle_trace_row(malformed)
    rows += contracts._story_memory_cycle_trace_row(valid)
    assert evidence._live_playwright_story_memory_cycle_trace_diagnostics(rows) == [
        valid
    ]


def test_story_memory_cycle_deduplicates_before_applying_its_record_cap() -> None:
    records = []
    for value in range(1, 6):
        record = contracts._story_memory_cycle_trace_record()
        samples = {
            name: dict(sample) if isinstance(sample, dict) else sample
            for name, sample in record["samples"].items()
        }
        samples["baseline"]["nodes"] = value
        record["samples"] = samples
        records.append(record)

    output = "".join(
        contracts._story_memory_cycle_trace_row(record)
        for record in (records[0], records[0], *records[1:])
    )

    parsed = evidence._live_playwright_story_memory_cycle_trace_diagnostics(output)
    assert parsed == records[:4]
    assert len(parsed) == 4


def test_password_forgot_stats_reject_impossible_request_outcomes() -> None:
    base = contracts._password_forgot_record()["forgot"]
    no_request_with_response = {
        **base,
        "responses": "1",
        "status": "2xx",
        "responsePhase": "after-click",
    }
    conflicting_single_request = {
        **base,
        "requests": "1",
        "responses": "1",
        "completed": "1",
        "failed": "1",
        "status": "mixed",
        "responsePhase": "mixed",
    }

    assert evidence._validated_password_forgot_stat(no_request_with_response) is None
    assert evidence._validated_password_forgot_stat(conflicting_single_request) is None


def test_password_forgot_record_rejects_unconfirmed_requests_and_orphan_submit_state() -> (
    None
):
    unconfirmed = contracts._password_forgot_record()
    unconfirmed["scope"] = "unconfirmed"
    unconfirmed["forgot"] = {
        **unconfirmed["forgot"],
        "requests": "1",
        "responses": "1",
        "failed": "1",
        "status": "429",
        "responsePhase": "after-click",
    }

    snapshot_without_submit = contracts._password_forgot_record()
    snapshot_without_submit["snapshot"] = {
        "forgotRoute": True,
        "hydrated": True,
        "formPresent": True,
        "formInvalid": False,
        "formAlert": False,
        "submitPresent": False,
        "submitDisabled": False,
        "submitBusy": True,
        "successMarkerVisible": False,
    }

    assert evidence._validated_password_forgot_record(unconfirmed) is None
    assert evidence._validated_password_forgot_record(snapshot_without_submit) is None


def test_registration_admission_diagnostics_deduplicate_and_cap_records() -> None:
    stages = ("deadline", "origin", "state-root", "owner-read", "ledger-read")
    records = [
        contracts._registration_admission_diag_record(stage=stage) for stage in stages
    ]
    output = "".join(
        contracts._registration_admission_diag_row(record)
        for record in (records[0], records[0], *records[1:])
    )

    parsed = evidence._live_playwright_registration_admission_diagnostics(output)
    assert parsed == records[:4]
    assert len(parsed) == 4


def test_pwa_bundle_route_rejects_service_worker_without_any_route() -> None:
    invalid = contracts._pwa_bundle_route_diag_record(
        routeEntries=0,
        originMatches=0,
        bundlePathMatches=0,
        serviceWorkerRequestSeen=True,
    )
    valid = contracts._pwa_bundle_route_diag_record()

    assert evidence._validated_pwa_bundle_route_diag(invalid) is None
    rows = contracts._pwa_bundle_route_diag_row(invalid)
    rows += contracts._pwa_bundle_route_diag_row(valid)
    assert evidence._live_playwright_pwa_bundle_route_diagnostics(rows) == [valid]


def test_pwa_update_lifecycle_diagnostics_deduplicate_and_cap_records() -> None:
    records = [
        contracts._pwa_update_lifecycle_diag_record(controllerChangeCount=count)
        for count in range(5)
    ]
    output = "".join(
        contracts._pwa_update_lifecycle_diag_row(record)
        for record in (records[0], records[0], *records[1:])
    )

    parsed = evidence._live_playwright_pwa_update_lifecycle_diagnostics(output)
    assert parsed == records[:4]
    assert len(parsed) == 4
