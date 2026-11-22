"""Offline contracts for the bounded, uncorrelated Push worker sample."""

from __future__ import annotations

import json
import logging
import runpy
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import yaml

from scripts import live_push_worker_observation as observation

SOURCE_SHA = "a" * 40
WORKER_ID = "b" * 64
WORKER_IDENTITY = "c" * 64
PRIVATE = "private-endpoint-user-token-and-payload"


def _event(status: str = "sent", *, stage: object = None, code: object = None) -> bytes:
    extra = {"event": "send", "status": status, "endpoint": PRIVATE, "user_id": PRIVATE}
    if stage is not None:
        extra["error_stage"] = stage
    if code is not None:
        extra["status_code"] = code
    return (
        json.dumps(
            {
                "logger": "app.services.webpush",
                "message": "webpush.send",
                "extra": extra,
                "private": PRIVATE,
            }
        ).encode()
        + b"\n"
    )


def test_projects_only_closed_marginal_counts_and_caps_them() -> None:
    duplicate_root = (
        json.dumps(
            {
                "logger": "root",
                "message": "webpush.send",
                "extra": {"event": "send", "status": "sent"},
            }
        ).encode()
        + b"\n"
    )
    ordinary_error = (
        json.dumps(
            {
                "logger": "app.services.webpush",
                "message": "webpush.send",
                "extra": {"error": PRIVATE},
            }
        ).encode()
        + b"\n"
    )
    sample = (
        _event() * 12
        + _event("gone", stage="webpush_request", code=410)
        + duplicate_root
        + ordinary_error
        + b"unstructured unrelated output\n"
    )

    result = observation.project_worker_logs(
        sample, _event("error", stage="dns_resolution", code=503)
    )

    assert result is not None
    assert result.statuses == (9, 1, 1)
    assert result.stages == (0, 0, 1, 0, 0, 1, 9)
    assert result.http_classes == (0, 0, 0, 1, 1, 9)
    rendered = observation.render_summary(result)
    assert rendered.startswith("live E2E worker push sample=tail ")
    assert "sent=9 gone=1 error=1" in rendered
    assert PRIVATE not in rendered and PRIVATE not in repr(result)


def test_empty_sample_is_a_bounded_tail_not_absence_proof() -> None:
    result = observation.project_worker_logs(b'{"unrelated":1.5}\n', b"")
    assert result is not None
    assert result.statuses == (0, 0, 0)
    assert "sample=tail" in observation.render_summary(result)


def test_success_http_details_are_saturated_run_level_marginals() -> None:
    sample = (
        _event("sent", code=201) * 12
        + _event("sent", code=200) * 6
        + _event("sent", code=202) * 6
        + _event("sent")
        + _event("gone", code=201)
        + _event("error", code=200)
    )
    summary = observation.project_worker_logs(sample, b"")
    assert summary is not None
    assert summary.statuses == (9, 1, 1)
    assert summary.http_classes == (0, 9, 0, 0, 0, 1)
    assert summary.success_http == (9, 9)
    rendered = observation.render_summary(summary)
    assert "http_2xx=9" in rendered.split()
    details = observation.render_success_summary(summary)
    assert "sent_http_201=9" in details.split()
    assert "sent_http_other_2xx=9" in details.split()
    assert PRIVATE not in rendered + details


def test_legacy_worker_rows_and_summaries_have_no_success_status_details() -> None:
    summary = observation.project_worker_logs(
        _event("sent") + _event("gone", code=410), b""
    )
    assert summary is not None
    assert summary.success_http == (0, 0)
    assert "http_none=1" in observation.render_summary(summary).split()
    legacy = observation.WorkerSummary((1, 0, 0), (0,) * 7, (0, 0, 0, 0, 0, 1))
    assert observation.render_summary(legacy) == (
        "live E2E worker push sample=tail sent=1 gone=0 error=0 "
        "stage_url=0 stage_host=0 stage_dns=0 stage_address=0 "
        "stage_session=0 stage_request=0 stage_none=0 "
        "http_1xx=0 http_2xx=0 http_3xx=0 http_4xx=0 http_5xx=0 http_none=1"
    )
    assert "sent_http_201=0" in observation.render_success_summary(legacy).split()
    assert "sent_http_other_2xx=0" in observation.render_success_summary(legacy).split()


def test_success_details_exclude_non_success_and_non_2xx_rows() -> None:
    sample = (
        _event("sent", code=199)
        + _event("sent", code=300)
        + _event("gone", code=201)
        + _event("error", code=202)
        + _event("sent", code=201)
        + _event("sent", code=202)
    )
    summary = observation.project_worker_logs(sample, b"")
    assert summary is not None
    assert summary.statuses == (4, 1, 1)
    assert summary.http_classes == (1, 4, 1, 0, 0, 0)
    assert summary.success_http == (1, 1)


@pytest.mark.parametrize("bad", [(10, 0), (-1, 0), (True, 0), (0,), (PRIVATE, 0)])
def test_summary_rejects_invalid_success_status_counts(bad: tuple[object, ...]) -> None:
    summary = observation.WorkerSummary(
        (0,) * 3, (0,) * 7, (0,) * 6, cast(tuple[int, int], bad)
    )
    with pytest.raises(ValueError):
        observation.render_summary(summary)


@pytest.mark.parametrize(
    "stage,field",
    [
        ("endpoint_url_validation", "stage_url"),
        ("endpoint_host_validation", "stage_host"),
        ("dns_resolution", "stage_dns"),
        ("resolved_address_validation", "stage_address"),
        ("pinned_session_creation", "stage_session"),
        ("webpush_request", "stage_request"),
        (None, "stage_none"),
    ],
)
def test_all_worker_stages_map_to_closed_fields(stage: str | None, field: str) -> None:
    summary = observation.project_worker_logs(_event("error", stage=stage), b"")
    assert summary is not None
    assert sum(summary.stages) == 1
    assert f"{field}=1" in observation.render_summary(summary).split()


@pytest.mark.parametrize(
    "code,field",
    [
        (199, "http_1xx"),
        (200, "http_2xx"),
        (399, "http_3xx"),
        (400, "http_4xx"),
        (599, "http_5xx"),
        (None, "http_none"),
    ],
)
def test_http_codes_map_only_to_classes(code: int | None, field: str) -> None:
    summary = observation.project_worker_logs(_event("error", code=code), b"")
    assert summary is not None
    assert sum(summary.http_classes) == 1
    assert f"{field}=1" in observation.render_summary(summary).split()


@pytest.mark.parametrize(
    "stdout,stderr",
    [
        (b"{bad}\n", b""),
        (b'{"logger":"one","logger":"two"}\n', b""),
        (b'{"private":NaN}\n', b""),
        (b'{"private":1e999}\n', b""),
        (b"unstructured\r" + _event(), b""),
        (b"[]\n", b""),
        (b'{"logger":"app.services.webpush","message":"webpush.send"}\n', b""),
        (
            b'{"logger":"app.services.webpush","message":"webpush.send","extra":{"event":"other"}}\n',
            b"",
        ),
        (b"\xff\n", b""),
        (b'{"a":1}', b""),
        (b"x" * 8193 + b"\n", b""),
        (b"x\n" * 257, b""),
        (_event("unexpected"), b""),
        (_event("error", stage="private-stage"), b""),
        (_event("error", stage="none"), b""),
        (_event("error", code=True), b""),
        (_event("error", code=600), b""),
        (_event("error", code="500"), b""),
        (_event("sent", code=201.0), b""),
        (
            b'{"logger":"app.services.webpush","message":"webpush.send",'
            b'"extra":{"event":"send","status":"sent","status_code":null}}\n',
            b"",
        ),
    ],
)
def test_malformed_or_unbounded_samples_fail_closed(
    stdout: bytes, stderr: bytes
) -> None:
    assert observation.project_worker_logs(stdout, stderr) is None


def test_summary_renderer_rejects_unbounded_or_private_values() -> None:
    invalid = observation.WorkerSummary((PRIVATE, 0, 0), (0,) * 7, (0,) * 6)
    with pytest.raises(ValueError):
        observation.render_summary(invalid)


def test_projector_accepts_the_actual_structured_worker_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services.webpush import _log_event

    with caplog.at_level(logging.INFO, logger="app.services.webpush"):
        _log_event(
            "send", status="error", error_stage="dns_resolution", status_code=503
        )
    rows = [
        record.msg
        for record in caplog.records
        if record.name == "app.services.webpush" and isinstance(record.msg, dict)
    ]
    assert len(rows) == 1
    summary = observation.project_worker_logs(
        (json.dumps(rows[0]) + "\n").encode(), b""
    )
    assert summary is not None
    assert summary.statuses == (0, 0, 1)
    assert summary.stages == (0, 0, 1, 0, 0, 0, 0)
    assert summary.http_classes == (0, 0, 0, 0, 1, 0)


def _stand(monkeypatch: pytest.MonkeyPatch):
    stand = observation.live_stand
    owner = SimpleNamespace(stack=stand.LIVE_STACK_CORE, source_sha=SOURCE_SHA)
    worker = SimpleNamespace(
        service="outbox-worker",
        identity=WORKER_IDENTITY,
        running=True,
        status="running",
    )
    evidence = object()
    records = {WORKER_ID: worker}
    context = object()
    source_checks = []
    monkeypatch.setattr(stand, "_configure_state_mode", lambda args: None)
    monkeypatch.setattr(stand, "stand_lifecycle_lock", nullcontext)
    monkeypatch.setattr(stand, "load_stand_owner", lambda path: owner)
    monkeypatch.setattr(
        stand,
        "_assert_in_place_source_current",
        lambda checked_owner: source_checks.append(checked_owner) or SOURCE_SHA,
    )
    monkeypatch.setattr(stand, "_new_live_docker_read_context", lambda: context)
    monkeypatch.setattr(stand, "_assert_core_owner_unchanged", lambda *a, **kw: None)
    monkeypatch.setattr(
        stand, "_verify_stand_owner_compose_resources", lambda *a, **kw: evidence
    )
    monkeypatch.setattr(
        stand, "_live_core_caddy_container_inventory", lambda *a, **kw: records
    )
    monkeypatch.setattr(stand, "_assert_live_docker_read_context", lambda *a: None)
    monkeypatch.setattr(stand, "_live_probe_remaining", lambda *a: 1.0)
    reads: list[tuple[list[str], dict[str, object]]] = []

    def read(command, **kwargs):
        reads.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=_event(), stderr=b"")

    monkeypatch.setattr(stand, "_run_live_bounded_read", read)
    return owner, worker, evidence, records, reads, source_checks


def test_collector_pins_owner_worker_and_bounded_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, _, _, reads, source_checks = _stand(monkeypatch)

    result = observation.collect_worker_sample("synthetic-state", SOURCE_SHA)

    assert result.statuses == (1, 0, 0)
    assert len(reads) == 1
    command, options = reads[0]
    assert command == ["docker", "logs", "--tail", "256", WORKER_ID]
    assert options["maximum_bytes"] == observation.MAX_BYTES
    assert options["command_timeout_seconds"] == observation.READ_TIMEOUT_SECONDS
    assert source_checks == [owner, owner]


@pytest.mark.parametrize(
    "fault",
    [
        "source",
        "source_drift_before",
        "source_drift_after",
        "stack",
        "worker_missing",
        "worker_stopped",
        "worker_status",
        "worker_invalid",
        "worker_id_invalid",
        "worker_changed",
        "evidence_changed",
        "read_failure",
        "bad_log",
    ],
)
def test_collector_refuses_unverified_or_changed_evidence(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    owner, worker, evidence, records, _, _ = _stand(monkeypatch)
    stand = observation.live_stand
    source_sha = SOURCE_SHA
    if fault == "source":
        source_sha = "d" * 40
    elif fault == "source_drift_before":
        monkeypatch.setattr(
            stand, "_assert_in_place_source_current", lambda *a: "d" * 40
        )
    elif fault == "source_drift_after":
        source_checks = iter((SOURCE_SHA, "d" * 40))
        monkeypatch.setattr(
            stand, "_assert_in_place_source_current", lambda *a: next(source_checks)
        )
    elif fault == "stack":
        owner.stack = stand.LIVE_STACK_FULL
    elif fault == "worker_missing":
        records.clear()
    elif fault == "worker_stopped":
        worker.running = False
    elif fault == "worker_status":
        worker.status = "exited"
    elif fault == "worker_invalid":
        worker.identity = "private-invalid"
    elif fault == "worker_id_invalid":
        records["invalid"] = records.pop(WORKER_ID)
    elif fault == "worker_changed":
        calls = iter(
            (
                records,
                {
                    WORKER_ID: SimpleNamespace(
                        service="outbox-worker",
                        identity="d" * 64,
                        running=True,
                        status="running",
                    )
                },
            )
        )
        monkeypatch.setattr(
            stand, "_live_core_caddy_container_inventory", lambda *a, **kw: next(calls)
        )
    elif fault == "evidence_changed":
        calls = iter((evidence, object()))
        monkeypatch.setattr(
            stand, "_verify_stand_owner_compose_resources", lambda *a, **kw: next(calls)
        )
    elif fault == "read_failure":
        monkeypatch.setattr(
            stand,
            "_run_live_bounded_read",
            lambda *a, **kw: subprocess.CompletedProcess([], 1, b"", b""),
        )
    elif fault == "bad_log":
        monkeypatch.setattr(
            stand,
            "_run_live_bounded_read",
            lambda *a, **kw: subprocess.CompletedProcess([], 0, b"{bad}\n", b""),
        )

    with pytest.raises(ValueError):
        observation.collect_worker_sample("synthetic-state", source_sha)


@pytest.mark.parametrize("state,source", [("", SOURCE_SHA), ("synthetic-state", "bad")])
def test_collector_rejects_unbound_input(state: str, source: str) -> None:
    with pytest.raises(ValueError):
        observation.collect_worker_sample(state, source)


def test_cli_fails_closed_without_printing_exceptions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args):
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(observation, "collect_worker_sample", fail)
    assert observation.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "live E2E worker push sample=unavailable\n"
    assert captured.err == ""


def test_cli_emits_only_closed_summary_and_survives_closed_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = observation.WorkerSummary((1, 0, 0), (0,) * 7, (0,) * 6)
    monkeypatch.setattr(observation, "collect_worker_sample", lambda *args: summary)
    assert observation.main() == 0
    assert capsys.readouterr().out == (
        observation.render_summary(summary)
        + "\n"
        + observation.render_success_summary(summary)
        + "\n"
    )

    def broken_print(*args, **kwargs):
        raise OSError(PRIVATE)

    monkeypatch.setattr("builtins.print", broken_print)
    assert observation.main() == 0


def test_module_entrypoint_without_owned_state_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LIVE_STATE_DIR", raising=False)
    monkeypatch.delenv("LIVE_OBSERVATION_SOURCE_SHA", raising=False)
    monkeypatch.delitem(
        sys.modules, "scripts.live_push_worker_observation", raising=False
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_module("scripts.live_push_worker_observation", run_name="__main__")
    assert result.value.code == 0
    assert capsys.readouterr().out == "live E2E worker push sample=unavailable\n"


def test_core_workflow_runs_diagnostic_after_failure_before_stop() -> None:
    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1]
            / ".github/workflows/live-acceptance.yml"
        ).read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["live-acceptance"]
    assert job["env"]["LIVE_E2E_MODE"] == (
        "${{ github.event_name == 'pull_request' && 'smoke' || 'full' }}"
    )
    steps = job["steps"]
    by_id = {
        step.get("id"): index for index, step in enumerate(steps) if step.get("id")
    }
    assert (
        by_id["core-e2e"]
        < by_id["nats-outage"]
        < by_id["push-worker-diagnostic"]
        < by_id["stop-stand"]
    )
    assert "github.event_name == 'pull_request'" in steps[by_id["nats-outage"]]["if"]
    step = steps[by_id["push-worker-diagnostic"]]
    assert (
        step["if"]
        == "${{ !cancelled() && env.LIVE_E2E_MODE == 'full' && steps.start-stand.outcome == 'success' && steps.core-e2e.outcome == 'failure' }}"
    )
    assert not step.get("continue-on-error", False)
    assert step["timeout-minutes"] == 1
    assert (
        step["env"]["LIVE_OBSERVATION_SOURCE_SHA"]
        == "${{ steps.verify-event-commit.outputs.checked_out_sha }}"
    )
    assert (
        step["run"]
        == "uv run --frozen --no-sync python -m scripts.live_push_worker_observation"
    )


_NO_AGE = object()


def _gone_row(
    endpoint: object,
    *,
    code: object = 410,
    stage: str = "webpush_request",
    age: object = _NO_AGE,
) -> bytes:
    extra: dict[str, object] = {
        "event": "send",
        "status": "gone",
        "status_code": code,
        "error_stage": stage,
        "endpoint": endpoint,
        "user_id": PRIVATE,
    }
    if age is not _NO_AGE:
        extra["subscription_age"] = age
    return (
        json.dumps(
            {
                "logger": "app.services.webpush",
                "message": "webpush.send",
                "extra": extra,
            }
        )
        + "\n"
    ).encode()


def test_410_projection_uses_the_real_masked_worker_event_without_exposing_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from hashlib import sha256

    from app.core.logging import _redact_pii
    from app.services.webpush import _log_event

    endpoint = "https://push.example.invalid/private-token"
    with caplog.at_level(logging.INFO, logger="app.services.webpush"):
        _log_event(
            "send",
            status="gone",
            status_code=410,
            error_stage="webpush_request",
            endpoint=endpoint,
            subscription_age="lt_10s",
        )
    rows = [
        r.msg
        for r in caplog.records
        if r.name == "app.services.webpush" and isinstance(r.msg, dict)
    ]
    assert len(rows) == 1
    redacted = _redact_pii(None, None, rows[0])
    result = observation.project_worker_logs(
        (json.dumps(redacted) + "\n").encode(), b""
    )
    assert result is not None
    prefix = sha256(endpoint.encode()).hexdigest()[:10]
    assert result.gone_410_prefixes == (prefix,)
    assert result.gone_410_ages == ("lt_10s",)
    assert observation.render_410_prefixes(result) == [
        "live E2E worker push 410 sample=tail incomplete=false truncated=false",
        "live E2E worker push 410 sample=tail endpoint_sha256="
        + prefix
        + " subscription_age=lt_10s",
    ]
    assert "private" not in repr(result) + "".join(
        observation.render_410_prefixes(result)
    )
    assert "example" not in repr(result) + "".join(
        observation.render_410_prefixes(result)
    )


def test_410_projection_rejects_invalid_masks_and_does_not_attribute_other_statuses() -> (
    None
):
    result = observation.project_worker_logs(
        _gone_row("https://provider.invalid/…#0123456789") * 2
        + _gone_row("https://provider.invalid/…#aaaaaaaaaa", code=404)
        + _gone_row("https://provider.invalid/…#bbbbbbbbbb", stage="dns_resolution")
        + _gone_row("https://provider.invalid/raw-private#cccccccccc")
        + _gone_row(None),
        b"",
    )
    assert result is not None
    assert result.gone_410_prefixes == ("0123456789",)
    assert result.gone_410_incomplete is True
    output = "\n".join(observation.render_410_prefixes(result))
    assert "incomplete=true" in output
    assert "aaaaaaaaaa" not in output and "bbbbbbbbbb" not in output
    assert "raw-private" not in output and "provider.invalid" not in output


def test_410_projection_caps_distinct_prefixes_and_rejects_renderer_spoofing() -> None:
    sample = b"".join(_gone_row("…#" + format(i, "010x")) for i in range(17))
    result = observation.project_worker_logs(sample, b"")
    assert result is not None
    assert len(result.gone_410_prefixes) == 16
    assert result.gone_410_truncated is True
    assert "truncated=true" in observation.render_410_prefixes(result)[0]
    for prefixes, seen, incomplete, truncated, ages in [
        ((PRIVATE,), True, False, False, ("unknown",)),
        (("aaaaaaaaaa", "aaaaaaaaaa"), True, False, False, ("unknown",) * 2),
        (("aaaaaaaaaa",), False, False, False, ("unknown",)),
        ((), True, "private", False, ()),
        (
            tuple(format(i, "010x") for i in range(17)),
            True,
            False,
            False,
            ("unknown",) * 17,
        ),
        (("aaaaaaaaaa",), True, False, False, ()),
        (("aaaaaaaaaa",), True, False, False, ["unknown"]),
        (("aaaaaaaaaa",), True, False, False, (PRIVATE,)),
        (("aaaaaaaaaa",), True, False, False, (10,)),
    ]:
        invalid = observation.WorkerSummary(
            (0,) * 3,
            (0,) * 7,
            (0,) * 6,
            (0, 0),
            prefixes,
            seen,
            incomplete,
            truncated,
            cast(tuple[str, ...], ages),
        )
        with pytest.raises(ValueError):
            observation.render_410_prefixes(invalid)


def test_410_projection_keeps_the_first_closed_age_of_each_prefix() -> None:
    result = observation.project_worker_logs(
        _gone_row("…#0123456789", age="lt_60s")
        + _gone_row("…#0123456789", age="ge_600s")
        + _gone_row("…#aaaaaaaaaa")
        + _gone_row("…#bbbbbbbbbb", code=404, age=PRIVATE),
        b"",
    )
    assert result is not None
    assert result.gone_410_prefixes == ("0123456789", "aaaaaaaaaa")
    assert result.gone_410_ages == ("lt_60s", "unknown")
    assert observation.render_410_prefixes(result)[1:] == [
        "live E2E worker push 410 sample=tail endpoint_sha256=0123456789"
        " subscription_age=lt_60s",
        "live E2E worker push 410 sample=tail endpoint_sha256=aaaaaaaaaa"
        " subscription_age=unknown",
    ]


@pytest.mark.parametrize("age", [PRIVATE, "", "lt_5s", 10, None, True])
def test_410_projection_rejects_an_open_age_value(age: object) -> None:
    assert (
        observation.project_worker_logs(_gone_row("…#0123456789", age=age), b"") is None
    )


def test_cli_emits_bounded_410_prefixes_after_existing_summaries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = observation.project_worker_logs(_gone_row("…#0123456789"), b"")
    assert summary is not None
    monkeypatch.setattr(observation, "collect_worker_sample", lambda *args: summary)
    assert observation.main() == 0
    output = capsys.readouterr().out
    assert output.splitlines() == [
        observation.render_summary(summary),
        observation.render_success_summary(summary),
        *observation.render_410_prefixes(summary),
    ]
    assert PRIVATE not in output
