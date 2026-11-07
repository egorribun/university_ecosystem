"""Fail-closed boundaries for the live Playwright evidence protocols."""

from __future__ import annotations

from scripts import live_stand_playwright_evidence as evidence
from tests import test_live_stand as contracts


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
