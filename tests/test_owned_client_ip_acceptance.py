"""RED-stage, offline behavioral contracts; no live stand or credentials are used.

Counterfactuals exercise the real admission/decoder/verdict functions, not mock
network behavior. GREEN for these tests will prove only the harness contract.
It cannot close AUD-164/AUD-167 or establish a deployed forwarding chain.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scripts.owned_client_ip_acceptance import (
    AdmissionPins,
    ClientRoute,
    decode_observations,
    evaluate_observations,
    validate_admission,
)
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessResult,
    ProcessOutcome,
)

SHA = "a" * 40
RUN_ID = "b" * 64


def _pins() -> AdmissionPins:
    return AdmissionPins(
        source_sha=SHA,
        owner_identity="c" * 64,
        daemon_identity="d" * 64,
        resource_identity="e" * 64,
        container_ids=tuple(character * 64 for character in "1234"),
        image_ids=tuple("sha256:" + character * 64 for character in "5678"),
        routes=(
            ClientRoute(
                "public", "9" * 64, "172.23.0.0/24", "172.23.0.10", "172.23.0.20"
            ),
            ClientRoute(
                "frontend_net",
                "f" * 64,
                "172.24.0.0/24",
                "172.24.0.10",
                "172.24.0.20",
            ),
        ),
        trusted_proxies=(
            ("172.23.0.20", "172.24.0.20", "172.23.0.30"),
            ("172.23.0.20",),
            ("172.23.0.20",),
        ),
        limits=(60, 5, 5, 3, 10),
        backend_command=(
            "gunicorn",
            "app.main:app",
            "--worker-class",
            "uvicorn.workers.UvicornWorker",
            "--workers",
            "2",
            "--bind",
            "0.0.0.0:8000",
            "--graceful-timeout",
            "30",
            "--timeout",
            "60",
            "--keep-alive",
            "5",
            "--error-logfile",
            "-",
        ),
    )


def _admitted(expected: AdmissionPins, current: AdmissionPins) -> bool:
    return validate_admission(expected, current, now_ms=1000, deadline_ms=121000)


def _case(name: str, count: int, status: int, elapsed_ms: int) -> dict[str, object]:
    return {
        "case": name,
        "allowed": [status] * count,
        "blocked": 429,
        "other_client": status,
        # X-Forwarded-For, X-Real-IP, Forwarded; no caller-supplied case names.
        "spoofed": [429, 429, 429],
        "direct_untrusted": 429,
        "backend_direct_untrusted": None if name == "ws_hub" else 429,
        "elapsed_ms": elapsed_ms,
    }


def _wire() -> dict[str, object]:
    return {
        "schema": "ue-owned-client-ip-v2",
        "source_sha": SHA,
        "run_id": RUN_ID,
        "closed": True,
        # The fixed producer must verify bound socket addresses before attesting.
        "sources_verified": True,
        "anonymous": True,
        "source_labels": ["public", "frontend_net"],
        "csrf_ready": [True, True],
        "setup_requests": 2,
        "http_requests": 119,
        "elapsed_ms": 60000,
        "cases": [
            _case("login", 60, 422, 1000),
            _case("register", 5, 422, 1000),
            _case("mfa", 5, 422, 1000),
            _case("forgot", 3, 422, 1000),
            _case("ws_hub", 10, 401, 1000),
        ],
    }


def _result(wire: object) -> PrivateProcessResult:
    return PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        (json.dumps(wire, separators=(",", ":")) + "\n").encode(),
        b"",
        LocalCleanup.CONFIRMED,
    )


def _decode(result: PrivateProcessResult):
    return decode_observations(
        result,
        expected_source_sha=SHA,
        expected_run_id=RUN_ID,
        now_ms=61000,
        deadline_ms=121000,
    )


def _rows(wire: dict[str, object]) -> list[dict[str, object]]:
    rows = wire["cases"]
    assert isinstance(rows, list)
    return rows


def test_admission_accepts_only_the_unchanged_owned_two_interface_configuration():
    pins = _pins()
    assert _admitted(pins, pins)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha", "0" * 40),
        ("owner_identity", "0" * 64),
        ("daemon_identity", "0" * 64),
        ("resource_identity", "0" * 64),
        ("container_ids", tuple(character * 64 for character in "1235")),
        ("image_ids", tuple("sha256:" + character * 64 for character in "5679")),
        ("limits", (61, 5, 5, 3, 10)),
        ("backend_command", ("uvicorn", "app.main:app")),
    ],
)
def test_admission_rejects_changed_source_owner_runtime_or_limits(field, value):
    pins = _pins()
    assert not _admitted(pins, replace(pins, **{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha", "not-a-sha"),
        ("owner_identity", ""),
        ("daemon_identity", "D" * 64),
        ("resource_identity", True),
        ("container_ids", ("1" * 64,) * 4),
        ("image_ids", ("latest",) * 4),
        ("limits", (60, 5, True, 3, 10)),
        ("limits", (60, 5, 5, 3, 11)),
        ("backend_command", ("gunicorn", "other:app")),
        ("trusted_proxies", (("0.0.0.0/0",), (), ())),
        ("trusted_proxies", (("172.23.0.0/24",), (), ())),
        ("trusted_proxies", ((), (), ())),
        ("trusted_proxies", (("172.23.0.10",), (), ())),
    ],
)
def test_admission_does_not_accept_identically_invalid_pins(field, value):
    invalid = replace(_pins(), **{field: value})
    assert not _admitted(invalid, invalid)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("network", "arbitrary"),
        ("network_id", ""),
        ("subnet", "0.0.0.0/0"),
        ("source_ip", "127.0.0.1"),
        ("source_ip", "203.0.113.10"),
        ("source_ip", "172.23.0.10:80"),
        ("source_ip", "172.23.0.20"),
        ("source_ip", "172.24.0.10"),
        ("caddy_ip", "172.23.0.10"),
        ("caddy_ip", "172.24.0.20"),
    ],
)
def test_admission_rejects_wrong_networks_sources_or_target_addresses(field, value):
    pins = _pins()
    route = replace(pins.routes[0], **{field: value})
    invalid = replace(pins, routes=(route, pins.routes[1]))
    assert not _admitted(invalid, invalid)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_admission_rejects_a_client_address_trusted_by_any_service(index):
    pins = _pins()
    trust = list(pins.trusted_proxies)
    trust[index] += ("172.24.0.10",)
    invalid = replace(pins, trusted_proxies=tuple(trust))
    assert not _admitted(invalid, invalid)


def test_admission_rejects_reused_interfaces_instead_of_header_simulated_clients():
    pins = _pins()
    invalid = replace(pins, routes=(pins.routes[0], pins.routes[0]))
    assert not _admitted(invalid, invalid)


@pytest.mark.parametrize(
    ("now", "deadline"),
    [(1000, 1000), (1001, 1000), (True, 121000), (1000, True), (-1, 120000)],
)
def test_admission_rejects_expired_or_invalid_deadlines(now, deadline):
    pins = _pins()
    assert not validate_admission(pins, pins, now_ms=now, deadline_ms=deadline)


def test_private_admission_repr_does_not_publish_network_or_owner_metadata():
    pins = _pins()
    rendered = repr(pins) + repr(pins.routes[0])
    for private in ("172.23.0.10", "172.23.0.20", "c" * 64, "1" * 64):
        assert private not in rendered


def test_complete_status_evidence_passes_only_backend_and_ws_hub_subsets():
    observed = _decode(_result(_wire()))
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend is True
    assert verdict.ws_hub is True
    assert verdict.gateway == "not_assessed"
    assert verdict.deployment == "not_assessed"


@pytest.mark.parametrize("case_index", range(5))
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("blocked", 422),
        ("other_client", 429),
        ("spoofed", [422, 429, 429]),
        ("spoofed", [429, 422, 429]),
        ("spoofed", [429, 429, 422]),
        ("direct_untrusted", 422),
    ],
)
def test_collapsed_clients_or_spoof_bypass_cannot_pass(case_index, field, value):
    wire = _wire()
    _rows(wire)[case_index][field] = value
    observed = _decode(_result(wire))
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend is (case_index == 4)
    assert verdict.ws_hub is (case_index != 4)


@pytest.mark.parametrize("case_index", range(5))
@pytest.mark.parametrize("wrong_status", [200, 302, 400, 403, 429, 500, 503])
def test_csrf_failure_redirect_early_limit_or_outage_cannot_masquerade_as_validation(
    case_index, wrong_status
):
    wire = _wire()
    allowed = _rows(wire)[case_index]["allowed"]
    assert isinstance(allowed, list)
    allowed[0] = wrong_status
    observed = _decode(_result(wire))
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend is (case_index == 4)
    assert verdict.ws_hub is (case_index != 4)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "other"),
        ("source_sha", "0" * 40),
        ("run_id", "0" * 64),
        ("closed", False),
        ("closed", 1),
        ("sources_verified", False),
        ("sources_verified", 1),
        ("anonymous", False),
        ("anonymous", 1),
        ("source_labels", ["public", "public"]),
        ("source_labels", ["frontend_net", "public"]),
        ("csrf_ready", [False, True]),
        ("csrf_ready", [True, 1]),
        ("setup_requests", 3),
        ("http_requests", 114),
        ("http_requests", 116),
        ("http_requests", 161),
        ("http_requests", True),
        ("elapsed_ms", 120001),
        ("elapsed_ms", -1),
        ("elapsed_ms", True),
        ("cases", []),
    ],
)
def test_decoder_rejects_unbound_incomplete_or_over_budget_observations(field, value):
    wire = _wire()
    wire[field] = value
    assert _decode(_result(wire)) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case", "gateway"),
        ("allowed", []),
        ("allowed", [422] * 61),
        ("allowed", [True] * 60),
        ("blocked", True),
        ("blocked", "429"),
        ("other_client", 600),
        ("spoofed", [429, 429]),
        ("spoofed", [429, 429, 429, 429]),
        ("direct_untrusted", None),
        ("elapsed_ms", 45001),
        ("elapsed_ms", -1),
    ],
)
def test_decoder_rejects_unbounded_or_wrongly_typed_case_rows(field, value):
    wire = _wire()
    _rows(wire)[0][field] = value
    assert _decode(_result(wire)) is None


def test_decoder_rejects_ws_refill_ambiguity_and_duplicate_or_reordered_cases():
    wire = _wire()
    _rows(wire)[4]["elapsed_ms"] = 5001
    assert _decode(_result(wire)) is None
    wire = _wire()
    _rows(wire)[1] = dict(_rows(wire)[0])
    assert _decode(_result(wire)) is None
    wire = _wire()
    _rows(wire).reverse()
    assert _decode(_result(wire)) is None


@pytest.mark.parametrize("location", ["root", "case"])
@pytest.mark.parametrize("extra", ["cookie", "headers", "source_ip", "body", "url"])
def test_decoder_rejects_unexpected_private_data_instead_of_echoing_it(location, extra):
    wire = _wire()
    target = wire if location == "root" else _rows(wire)[0]
    target[extra] = "private-sentinel"
    assert _decode(_result(wire)) is None


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"{}\n{}\n",
        b"\xff\n",
        b"null\n",
        b"[]\n",
        b'{"closed":true,"closed":true}\n',
        b'{"elapsed_ms":NaN}\n',
        b'{"elapsed_ms":Infinity}\n',
        b"[" * 1000 + b"\n",
        b"x" * 4097,
    ],
)
def test_decoder_rejects_truncation_duplicate_keys_non_json_and_output_overflow(raw):
    assert _decode(replace(_result(_wire()), stdout=raw)) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", ProcessOutcome.TIMED_OUT),
        ("outcome", ProcessOutcome.OUTPUT_LIMIT),
        ("outcome", ProcessOutcome.CLEANUP_UNCERTAIN),
        ("returncode", 1),
        ("returncode", None),
        ("returncode", False),
        ("stdout", "not-bytes"),
        ("stderr", b"private-sentinel"),
        ("local_cleanup", LocalCleanup.UNPROVEN),
        ("local_cleanup", LocalCleanup.NOT_STARTED),
    ],
)
def test_decoder_requires_complete_private_execution_and_confirmed_local_cleanup(
    field, value
):
    assert _decode(replace(_result(_wire()), **{field: value})) is None


def test_decoder_does_not_confuse_local_reaping_with_remote_socket_closure():
    wire = _wire()
    del wire["closed"]
    assert _decode(_result(wire)) is None


def test_decoder_rejects_success_received_after_the_outer_deadline():
    assert (
        decode_observations(
            _result(_wire()),
            expected_source_sha=SHA,
            expected_run_id=RUN_ID,
            now_ms=121000,
            deadline_ms=121000,
        )
        is None
    )


@pytest.mark.parametrize(
    ("case_index", "wrong_status"),
    [(0, 401), (1, 401), (2, 401), (3, 401), (4, 422)],
)
def test_wrong_service_response_cannot_prove_the_target_handler(
    case_index, wrong_status
):
    wire = _wire()
    allowed = _rows(wire)[case_index]["allowed"]
    assert isinstance(allowed, list)
    allowed[0] = wrong_status
    observed = _decode(_result(wire))
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend is (case_index == 4)
    assert verdict.ws_hub is (case_index != 4)


@pytest.mark.parametrize("case_index", range(5))
def test_a_spoofed_request_reaching_the_real_handler_fails_the_affected_subset(
    case_index,
):
    wire = _wire()
    _rows(wire)[case_index]["spoofed"] = (
        [401, 429, 429] if case_index == 4 else [422, 429, 429]
    )
    observed = _decode(_result(wire))
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert verdict.backend is (case_index == 4)
    assert verdict.ws_hub is (case_index != 4)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b'"closed":true', b'"closed":true,"closed":true'),
        (b'"case":"login"', b'"case":"login","case":"login"'),
    ],
)
def test_duplicate_keys_are_rejected_even_when_the_remaining_frame_is_valid(
    before, after
):
    result = _result(_wire())
    assert before in result.stdout
    duplicated = replace(result, stdout=result.stdout.replace(before, after, 1))
    assert _decode(duplicated) is None


@pytest.mark.parametrize(
    ("field", "value"), [("source_sha", "invalid"), ("run_id", "invalid")]
)
def test_matching_but_malformed_expected_bindings_are_not_admitted(field, value):
    wire = _wire()
    wire[field] = value
    assert (
        decode_observations(
            _result(wire),
            expected_source_sha=value if field == "source_sha" else SHA,
            expected_run_id=value if field == "run_id" else RUN_ID,
            now_ms=61000,
            deadline_ms=121000,
        )
        is None
    )


def test_decoder_rejects_a_total_elapsed_time_shorter_than_its_case_observations():
    wire = _wire()
    wire["elapsed_ms"] = 4999
    assert _decode(_result(wire)) is None


def test_admission_rejects_current_network_attachment_drift():
    pins = _pins()
    current_route = replace(pins.routes[0], network_id="0" * 64)
    current = replace(pins, routes=(current_route, pins.routes[1]))
    assert not _admitted(pins, current)
