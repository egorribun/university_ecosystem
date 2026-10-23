"""Safety ordering and evidence contracts; no Docker, HTTP, SQL or NATS."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from scripts.owned_nats_coordinator import (
    BrokerErrorEvidence,
    ChatParticipantRow,
    ChatRow,
    CommandEvidence,
    CorrelationRows,
    LoginEvidence,
    MessagePostEvidence,
    OutageCheckpoint,
    OutageOutcome,
    OutageResult,
    OutageStage,
    ParticipantEvidence,
    PgRoleRow,
    WaitVerdict,
    run_owned_outage,
    wait_for_poll,
)
from scripts.owned_nats_outage import (
    Deadline,
    MessageEvidence,
    StoredEventState,
    WorkerPolicy,
)
from tests.helpers.owned_nats_coordinator import (
    ADMIN,
    CHAT,
    CONTENT,
    EVENT,
    MESSAGE,
    OTHER,
    PEER,
    FakeClock,
    FakePorts,
    FakeSleeper,
)


def run(ports: FakePorts):
    result = run_owned_outage(ports, clock=ports.clock, sleep=ports.sleep)
    assert ports.contract_errors == []
    return result


def names(ports: FakePorts) -> list[str]:
    return [call.name for call in ports.calls]


def assert_failed(
    ports: FakePorts, *, sends: int | None = 0, restores: int = 0
) -> OutageResult:
    result = run(ports)
    assert result.outcome is OutageOutcome.FAILED
    trace = names(ports)
    if sends is None:
        assert trace.count("send_message_once") <= 1
    else:
        assert trace.count("send_message_once") == sends
    assert trace.count("start_container") == restores
    assert trace[-2:] == ["close_clients", "release_lock"]
    return result


def test_valid_path_binds_exact_event_and_restores_before_drain() -> None:
    ports = FakePorts()
    result = run(ports)
    trace = names(ports)

    assert result.outcome is OutageOutcome.ACCEPTED
    assert result.stage is OutageStage.COMPLETE
    assert result.checkpoint is None
    assert ports.owner.repository.startswith("/")
    assert ports.owner.worktree.startswith(
        "/fixtures/system-temp/ue-live-acceptance/run-"
    )
    assert ports.owner.repository != ports.owner.worktree
    assert trace.count("stop_container") == trace.count("send_message_once") == 1
    assert trace.count("create_dm_once") == trace.count("start_container") == 1
    stop = trace.index("stop_container")
    start = trace.index("start_container")
    correlation = trace.index("read_correlation")
    states = [index for index, name in enumerate(trace) if name == "outbox_state"]
    assert trace[stop - 1] == "pending_count"
    assert stop < trace.index("send_message_once") < correlation < states[0] < start
    assert start < states[-1] < trace.index("broker_last_message")
    assert trace[-2:] == ["close_clients", "release_lock"]
    assert ports.sleep.calls == []
    for call in ports.calls:
        if call.name == "create_dm_once":
            assert call.args == (PEER,)
        if call.name == "send_message_once":
            assert call.args == (CHAT, CONTENT)
        if call.name == "login_admin":
            assert call.args == (ports.owner, ADMIN)
        if call.name == "read_correlation":
            assert call.args[-1] == MESSAGE
        service = {
            "read_policy": "outbox-worker",
            "read_admission": "postgres",
            "read_dm": "postgres",
            "pending_count": "postgres",
            "read_correlation": "postgres",
            "outbox_state": "postgres",
            "broker_last_message": "backend",
        }.get(call.name)
        if service is not None:
            assert call.args[0] == ports.owner
            assert call.args[1] == next(
                record for record in ports.records if record.service == service
            )
        if call.name == "outbox_state":
            assert call.args[-1] == EVENT
        if call.name == "broker_last_message":
            assert call.args[-1] == f"chat.{CHAT}"
        maximum = 15 if call.name == "stop_container" else 10
        assert call.deadline.expires_at is not None
        assert 0 < call.deadline.expires_at - call.started_at <= maximum


@pytest.mark.parametrize(
    "operation",
    [
        "read_signed_owner",
        "observe_runtime",
        "read_policy",
        "read_admission",
        "login_admin",
    ],
)
def test_preflight_exception_never_stops_or_sends(operation: str) -> None:
    ports = FakePorts()
    ports.script[operation] = [RuntimeError("private probe details")]
    assert_failed(ports)
    assert "stop_container" not in names(ports)


@pytest.mark.parametrize("count", [1, -1, True, None])
def test_pending_count_must_be_exact_integer_zero(count: object) -> None:
    ports = FakePorts()
    ports.script["pending_count"] = [count]
    assert_failed(ports)
    assert "stop_container" not in names(ports)


@pytest.mark.parametrize(
    "command",
    [
        CommandEvidence(1, False),
        CommandEvidence(None, True),
        TimeoutError("private stop"),
    ],
)
def test_uncertain_stop_never_sends_but_restores(command: object) -> None:
    ports = FakePorts()
    ports.script["stop_container"] = [command]
    assert_failed(ports, restores=1)


def test_exit_zero_without_stopped_target_never_sends() -> None:
    ports = FakePorts()
    ports.keep_running_after_stop = True
    assert_failed(ports, restores=1)


@pytest.mark.parametrize(
    "response",
    [
        TimeoutError("private HTTP body"),
        MessagePostEvidence(500, None),
        MessagePostEvidence(201, MessageEvidence(MESSAGE, CHAT, ADMIN, CONTENT)),
    ],
)
def test_ambiguous_send_is_never_retried(response: object) -> None:
    ports = FakePorts()
    ports.script["send_message_once"] = [response]
    assert_failed(ports, sends=1, restores=1)


@pytest.mark.parametrize(
    "state",
    [
        None,
        StoredEventState(OTHER, False, 1, 0),
        StoredEventState(EVENT, True, 1, 0),
        StoredEventState(EVENT, False, 5, 0),
        StoredEventState(EVENT, False, 1, 1),
    ],
)
def test_invalid_or_terminal_retry_restores_without_delivery_poll(
    state: object,
) -> None:
    ports = FakePorts()
    ports.script["outbox_state"] = [state]
    assert_failed(ports, sends=1, restores=1)
    assert "broker_last_message" not in names(ports)


def test_no_retry_observed_expires_and_restores_with_fresh_budget() -> None:
    ports = FakePorts()
    ports.script["outbox_state"] = [StoredEventState(EVENT, False, 0, 0)]
    assert_failed(ports, sends=1, restores=1)
    assert 0 < len(ports.sleep.calls) <= 30
    start = next(call for call in ports.calls if call.name == "start_container")
    assert start.started_at >= 30
    assert start.deadline.expires_at > start.started_at


def test_owner_drift_restores_verified_original_but_fails_acceptance() -> None:
    ports = FakePorts()
    ports.owner_after_stop = replace(ports.owner, source_sha="b" * 40)
    assert_failed(ports, sends=None, restores=1)
    assert names(ports).count("stop_container") == 1
    assert "broker_last_message" not in names(ports)


def test_resource_drift_restores_original_but_fails_acceptance() -> None:
    ports = FakePorts()
    ports.resource_after_stop = "f" * 64
    assert_failed(ports, restores=1)


def test_daemon_drift_never_starts_an_unverified_target() -> None:
    ports = FakePorts()
    ports.daemon_drift_after_stop = True
    assert_failed(ports, restores=0)


@pytest.mark.parametrize("target", [None, "replacement"])
def test_missing_or_changed_original_identity_is_never_started(target: object) -> None:
    ports = FakePorts()
    ports.inspection_after_stop = (
        None if target is None else replace(ports.nats, identity="f" * 64)
    )
    assert_failed(ports, sends=None, restores=0)
    assert names(ports).count("stop_container") == 1


def test_primary_expiry_does_not_prevent_safe_restoration() -> None:
    ports = FakePorts()
    ports.advance["send_message_once"] = 181
    assert_failed(ports, sends=1, restores=1)
    assert "read_correlation" not in names(ports)
    assert "broker_last_message" not in names(ports)
    start = next(call for call in ports.calls if call.name == "start_container")
    assert start.started_at == 181
    assert start.deadline.expires_at > 181


def test_primary_expiry_during_restore_does_not_extend_drain() -> None:
    ports = FakePorts()
    ports.advance["read_admission"] = 9
    ports.advance["create_dm_once"] = 9
    ports.advance["read_dm"] = 9
    ports.advance["read_policy"] = 9
    ports.advance["login_admin"] = 9
    ports.advance["pending_count"] = 9
    ports.advance["send_message_once"] = 9
    ports.advance["read_correlation"] = 9
    ports.advance["outbox_state"] = 9
    ports.advance["observe_runtime"] = 9
    ports.restored_healthy_at = 185
    assert_failed(ports, sends=1, restores=1)
    assert ports.restore_started
    assert ports.clock.now >= 185
    assert names(ports).count("outbox_state") == 1
    assert "broker_last_message" not in names(ports)


def test_client_close_failure_cannot_consume_lock_release_reserve() -> None:
    ports = FakePorts()
    ports.script["close_clients"] = [TimeoutError("private close")]
    ports.advance["close_clients"] = 11
    assert_failed(ports, sends=1, restores=1)
    close, release = ports.calls[-2:]
    assert close.name == "close_clients"
    assert release.name == "release_lock"
    assert release.started_at >= close.started_at + 11
    assert release.deadline.expires_at == release.started_at + 10


def test_successful_poll_and_exact_missing_broker_message_can_wait() -> None:
    ports = FakePorts()
    ports.script["outbox_state"] = [
        StoredEventState(EVENT, False, 0, 0),
        StoredEventState(EVENT, False, 1, 0),
        StoredEventState(EVENT, True, 1, 0),
    ]
    ports.script["broker_last_message"] = [
        BrokerErrorEvidence(404, 10037),
        ports.broker,
    ]
    result = run(ports)
    assert result.outcome is OutageOutcome.ACCEPTED
    assert ports.sleep.calls == [1, 1]


@pytest.mark.parametrize(
    "error",
    [BrokerErrorEvidence(404, 10059), BrokerErrorEvidence(401, 10037)],
)
def test_nonpollable_broker_error_fails_without_wait(
    error: BrokerErrorEvidence,
) -> None:
    ports = FakePorts()
    ports.script["broker_last_message"] = [error]
    assert_failed(ports, sends=1, restores=1)
    assert ports.sleep.calls == []


def test_public_result_and_logs_contain_only_closed_labels(capsys) -> None:
    ports = FakePorts()
    private = f"password=private cookie=private token=private {MESSAGE} {CONTENT}"
    ports.script["send_message_once"] = [RuntimeError(private)]
    result = run(ports)
    captured = capsys.readouterr()
    assert result.outcome is OutageOutcome.FAILED
    assert {field.name for field in fields(result)} == {
        "outcome",
        "stage",
        "checkpoint",
        "runtime_diagnostic",
    }
    assert result.checkpoint is None
    assert result.runtime_diagnostic is None
    output = repr(result) + captured.out + captured.err
    for forbidden in (private, MESSAGE, CONTENT, "password=", "cookie=", "token="):
        assert forbidden not in output


@pytest.mark.parametrize(
    ("remaining", "interval", "expected", "slept"),
    [
        (5, 2, WaitVerdict.WAITED, [2]),
        (2.5, 10, WaitVerdict.EXPIRED, [2.5]),
        (5, 0, WaitVerdict.INVALID, []),
    ],
)
def test_poll_wait_uses_only_positive_remaining_budget(
    remaining: float, interval: float, expected: WaitVerdict, slept: list[float]
) -> None:
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    deadline = Deadline.after(remaining, clock=clock)
    assert wait_for_poll(deadline, interval, sleep=sleeper) is expected
    assert sleeper.calls == slept


def test_nonadvancing_sleeper_cannot_create_infinite_polling() -> None:
    clock = FakeClock()
    sleeper = FakeSleeper(clock, advances=False)
    deadline = Deadline.after(5, clock=clock)
    assert wait_for_poll(deadline, 1, sleep=sleeper) is WaitVerdict.INVALID
    assert sleeper.calls == [1]


@pytest.mark.parametrize(
    "case",
    ["wrong-stack", "wrong-daemon", "missing-service", "unhealthy-worker", "oom-nats"],
)
def test_raw_owner_and_inventory_evidence_are_not_assumed_valid(case: str) -> None:
    ports = FakePorts()
    if case == "wrong-stack":
        ports.owner = replace(ports.owner, stack="full")
    elif case == "wrong-daemon":
        ports.runtime_daemon = "f" * 64
    elif case == "missing-service":
        ports.records = tuple(row for row in ports.records if row.service != "backend")
    elif case == "unhealthy-worker":
        ports.records = tuple(
            replace(row, health="unhealthy") if row.service == "outbox-worker" else row
            for row in ports.records
        )
    else:
        ports.nats = replace(ports.nats, oom_killed=True)
    assert_failed(ports)
    assert "login_admin" not in names(ports)
    assert "stop_container" not in names(ports)


@pytest.mark.parametrize(
    "policy",
    [WorkerPolicy(0, 20, 5), WorkerPolicy(1, 1, 5), WorkerPolicy(1, 20, 6)],
)
def test_unsuitable_effective_worker_policy_aborts_before_login(
    policy: WorkerPolicy,
) -> None:
    ports = FakePorts()
    ports.script["read_policy"] = [policy]
    assert_failed(ports)
    assert "login_admin" not in names(ports)


@pytest.mark.parametrize(
    "case",
    [
        "session-role",
        "role-name",
        "not-superuser",
        "missing-peer",
        "duplicate-admin",
        "inactive-admin",
        "wrong-admin-role",
        "inactive-peer",
        "wrong-peer-key",
        "wrong-peer-email",
        "invalid-peer-id",
        "existing-dm",
    ],
)
def test_raw_actor_and_pair_admission_fail_closed(case: str) -> None:
    ports = FakePorts()
    admission = ports.admission
    admin, peer = admission.users
    if case == "session-role":
        admission = replace(
            admission,
            principal=replace(admission.principal, current_user="different_role"),
        )
    elif case == "role-name":
        admission = replace(
            admission,
            principal=replace(admission.principal, pg_role=PgRoleRow("other", True)),
        )
    elif case == "not-superuser":
        admission = replace(
            admission,
            principal=replace(
                admission.principal, pg_role=PgRoleRow("fixture_owner", False)
            ),
        )
    elif case == "missing-peer":
        admission = replace(admission, users=(admin,))
    elif case == "duplicate-admin":
        admission = replace(admission, users=(admin, admin, peer))
    elif case == "inactive-admin":
        admission = replace(admission, users=(replace(admin, is_active=False), peer))
    elif case == "wrong-admin-role":
        admission = replace(admission, users=(replace(admin, role="student"), peer))
    elif case == "inactive-peer":
        admission = replace(admission, users=(admin, replace(peer, is_active=False)))
    elif case == "wrong-peer-key":
        admission = replace(admission, users=(admin, replace(peer, demo_seed_key=None)))
    elif case == "wrong-peer-email":
        admission = replace(
            admission, users=(admin, replace(peer, email="unrelated@example.com"))
        )
    elif case == "invalid-peer-id":
        admission = replace(admission, users=(admin, replace(peer, id="invalid")))
    else:
        admission = replace(
            admission,
            chats=(ChatRow(CHAT, "dm", None),),
            participants=ports.chat_rows.participants,
        )
    ports.admission = admission
    assert_failed(ports)
    assert "login_admin" not in names(ports)
    assert "create_dm_once" not in names(ports)
    assert "stop_container" not in names(ports)


def test_group_chat_is_not_adopted_as_the_absent_direct_pair() -> None:
    ports = FakePorts()
    ports.admission = replace(
        ports.admission,
        chats=(ChatRow(OTHER, "group", None),),
        participants=(
            ChatParticipantRow(OTHER, ADMIN),
            ChatParticipantRow(OTHER, PEER),
        ),
    )
    assert run(ports).outcome is OutageOutcome.ACCEPTED
    assert names(ports).count("create_dm_once") == 1


@pytest.mark.parametrize(
    "login",
    [
        LoginEvidence(202, None),
        LoginEvidence(200, OTHER),
        LoginEvidence(401, None),
        LoginEvidence(201, ADMIN),
    ],
)
def test_mfa_or_wrong_effective_actor_cannot_create_chat(login: LoginEvidence) -> None:
    ports = FakePorts()
    ports.script["login_admin"] = [login]
    assert_failed(ports)
    assert "create_dm_once" not in names(ports)


@pytest.mark.parametrize(
    "case",
    [
        "http-status",
        "chat-id",
        "chat-type",
        "participants",
        "db-chat",
        "db-participants",
    ],
)
def test_exact_http_and_database_dm_evidence_is_required(case: str) -> None:
    ports = FakePorts()
    if case == "http-status":
        ports.chat = replace(ports.chat, status_code=201)
    elif case == "chat-id":
        ports.chat = replace(ports.chat, id=None)
    elif case == "chat-type":
        ports.chat = replace(ports.chat, chat_type="group")
    elif case == "participants":
        ports.chat = replace(
            ports.chat, participants=(ParticipantEvidence(ADMIN, True),)
        )
    elif case == "db-chat":
        ports.chat_rows = replace(ports.chat_rows, chat=None)
    else:
        ports.chat_rows = replace(
            ports.chat_rows, participants=(ChatParticipantRow(CHAT, OTHER),)
        )
    assert_failed(ports)
    assert names(ports).count("create_dm_once") == 1
    assert "stop_container" not in names(ports)


@pytest.mark.parametrize(
    "case", ["missing", "duplicate", "payload", "database-message"]
)
def test_coordinator_uses_raw_exact_message_and_event_correlation(
    case: str,
) -> None:
    ports = FakePorts()
    rows = CorrelationRows(ports.message, (ports.event,))
    if case == "missing":
        rows = replace(rows, stored_events=())
    elif case == "duplicate":
        rows = replace(rows, stored_events=(ports.event, ports.event))
    elif case == "payload":
        rows = replace(
            rows, stored_events=(replace(ports.event, payload={"message_id": OTHER}),)
        )
    else:
        rows = replace(
            rows, database_message=replace(ports.message, content="different")
        )
    ports.script["read_correlation"] = [rows]
    assert_failed(ports, sends=1, restores=1)
    assert "broker_last_message" not in names(ports)


@pytest.mark.parametrize(
    "state",
    [
        None,
        StoredEventState(OTHER, True, 1, 0),
        StoredEventState(EVENT, True, 0, 0),
        StoredEventState(EVENT, True, 5, 1),
    ],
)
def test_drain_cannot_substitute_or_reset_the_retained_event(state: object) -> None:
    ports = FakePorts()
    ports.script["outbox_state"] = [StoredEventState(EVENT, False, 1, 0), state]
    assert_failed(ports, sends=1, restores=1)
    assert "broker_last_message" not in names(ports)


@pytest.mark.parametrize("field", ["restart_count", "oom_killed", "health", "status"])
def test_non_target_runtime_changes_fail_restoration(field: str) -> None:
    ports = FakePorts()
    values = {
        "restart_count": 1,
        "oom_killed": True,
        "health": "unhealthy",
        "status": "exited",
    }
    ports.records_after_start = tuple(
        replace(row, **{field: values[field]}) if row.service == "backend" else row
        for row in ports.records
    )
    assert_failed(ports, sends=1, restores=1)
    assert "broker_last_message" not in names(ports)


@pytest.mark.parametrize("case", ["subject", "sequence", "envelope"])
def test_coordinator_requires_exact_raw_broker_receipt(case: str) -> None:
    ports = FakePorts()
    if case == "subject":
        ports.broker = replace(ports.broker, subject=f"chat.{OTHER}")
    elif case == "sequence":
        ports.broker = replace(ports.broker, sequence=0)
    else:
        ports.broker = replace(ports.broker, envelope={"type": "new_message"})
    result = assert_failed(ports, sends=1, restores=1)
    assert result.stage is OutageStage.BROKER
    assert result.checkpoint is OutageCheckpoint.BROKER_RECEIPT


def test_invalid_broker_probe_has_distinct_finite_checkpoint() -> None:
    ports = FakePorts()
    ports.broker = BrokerErrorEvidence(status=503, error_code=None)

    result = assert_failed(ports, sends=1, restores=1)

    assert result.stage is OutageStage.BROKER
    assert result.checkpoint is OutageCheckpoint.BROKER_PROBE


@pytest.mark.parametrize(
    "command",
    [
        CommandEvidence(1, False),
        CommandEvidence(None, True),
        RuntimeError("private start details"),
    ],
)
def test_failed_restore_start_never_allows_drain_or_broker(command: object) -> None:
    ports = FakePorts()
    ports.script["start_container"] = [command]
    assert_failed(ports, sends=1, restores=1)
    assert names(ports).count("outbox_state") == 1
    assert "broker_last_message" not in names(ports)


def test_restoration_health_wait_expires_within_independent_reserve() -> None:
    ports = FakePorts()
    ports.restored_healthy_at = 1000
    assert_failed(ports, sends=1, restores=1)
    assert 120 <= ports.clock.now <= 140
    assert "broker_last_message" not in names(ports)


def test_lock_release_failure_downgrades_an_otherwise_accepted_result() -> None:
    ports = FakePorts()
    ports.script["release_lock"] = [RuntimeError("private lock details")]
    assert_failed(ports, sends=1, restores=1)


def test_lock_acquisition_failure_does_not_release_an_unowned_lease() -> None:
    ports = FakePorts()
    ports.script["acquire_lock"] = [TimeoutError("private lock details")]
    result = run(ports)
    assert result.outcome is OutageOutcome.FAILED
    assert "release_lock" not in names(ports)
    assert "stop_container" not in names(ports)
    assert "send_message_once" not in names(ports)


def test_expired_preflight_operation_cannot_start_a_later_mutation() -> None:
    ports = FakePorts()
    ports.advance["read_admission"] = 11
    assert_failed(ports)
    assert "login_admin" not in names(ports)
    assert "stop_container" not in names(ports)


@pytest.mark.parametrize(
    ("drained_count", "expected"),
    [(4, OutageOutcome.ACCEPTED), (3, OutageOutcome.FAILED)],
)
def test_drain_uses_the_actual_observed_retry_counter(
    drained_count: int, expected: OutageOutcome
) -> None:
    ports = FakePorts()
    ports.script["outbox_state"] = [
        StoredEventState(EVENT, False, 4, 0),
        StoredEventState(EVENT, True, drained_count, 0),
    ]
    result = run(ports)
    assert result.outcome is expected
    assert names(ports).count("start_container") == 1
    assert ports.sleep.calls == []
    if expected is OutageOutcome.FAILED:
        assert "broker_last_message" not in names(ports)


def test_expiry_before_stop_invocation_does_not_start_an_untouched_target() -> None:
    ports = FakePorts()
    reads_after_pending = 0

    def expire_before_stop() -> float:
        nonlocal reads_after_pending
        if ports.calls and ports.calls[-1].name == "pending_count":
            reads_after_pending += 1
            # The fake's call check and caller's post-check must both succeed.
            if reads_after_pending >= 3:
                ports.clock.now = 181
        return ports.clock.now

    result = run_owned_outage(ports, clock=expire_before_stop, sleep=ports.sleep)
    assert ports.contract_errors == []
    assert result.outcome is OutageOutcome.FAILED
    assert reads_after_pending >= 3
    assert names(ports).count("pending_count") == 1
    assert "stop_container" not in names(ports)
    assert "start_container" not in names(ports)
    assert "send_message_once" not in names(ports)
    assert names(ports)[-2:] == ["close_clients", "release_lock"]


def test_late_acquired_lease_is_released_without_starting_preflight() -> None:
    ports = FakePorts()
    ports.advance["acquire_lock"] = 11
    assert_failed(ports)
    assert "read_signed_owner" not in names(ports)
    assert names(ports).count("release_lock") == 1
    assert ports.calls[-1].args == (ports.lease,)


@pytest.mark.parametrize(
    "drift", ["owner", "resource", "non-target", "nats-health", "target-identity"]
)
def test_broker_receipt_cannot_hide_final_owner_or_inventory_drift(
    drift: str, monkeypatch
) -> None:
    ports = FakePorts()
    original_receipt = ports.broker_last_message

    def receipt_then_drift(*args: object, deadline: Deadline):
        receipt = original_receipt(*args, deadline=deadline)
        if drift == "owner":
            ports.owner_after_stop = replace(ports.owner, source_sha="b" * 40)
        elif drift == "resource":
            ports.resource_after_stop = "f" * 64
        elif drift == "nats-health":
            ports.nats = replace(ports.nats, health="unhealthy")
        elif drift == "target-identity":
            ports.nats = replace(ports.nats, identity="f" * 64)
        else:
            ports.records_after_start = tuple(
                replace(row, restart_count=1) if row.service == "backend" else row
                for row in ports.records
            )
        return receipt

    monkeypatch.setattr(ports, "broker_last_message", receipt_then_drift)
    result = assert_failed(ports, sends=1, restores=1)
    trace = names(ports)
    assert trace.count("broker_last_message") == 1
    receipt_index = trace.index("broker_last_message")
    assert trace.index("start_container") < receipt_index
    assert "read_signed_owner" in trace[receipt_index + 1 :]
    if drift != "owner":
        assert "observe_runtime" in trace[receipt_index + 1 :]
    assert result.stage.value == "final_revalidation"


@pytest.mark.parametrize(
    ("case", "expected_phase"),
    [
        ("callback-error", "runtime_binding"),
        ("daemon-mismatch", "runtime_binding"),
        ("resource-mismatch", "runtime_binding"),
        ("selection", "inventory_invalid_selection"),
        ("identity", "inventory_invalid_identity"),
        ("runtime", "inventory_invalid_runtime"),
        ("health", "inventory_unhealthy"),
        ("valid", None),
    ],
)
def test_runtime_checkpoint_distinguishes_callback_and_inventory_rejection(
    capsys, case, expected_phase
):
    from scripts.owned_nats_coordinator import (
        OutageCheckpoint,
        RuntimeObservationPhase,
    )

    ports = FakePorts()
    if case == "callback-error":
        ports.script["observe_runtime"] = [RuntimeError("private-observation-error")]
    elif case == "daemon-mismatch":
        ports.runtime_daemon = "f" * 64
    elif case == "resource-mismatch":
        ports.script["observe_runtime"] = [
            replace(ports.runtime(), resource_fingerprint="f" * 64)
        ]
    elif case == "selection":
        ports.owner = replace(
            ports.owner,
            selected_services=tuple(
                service
                for service in ports.owner.selected_services
                if service != "backend"
            ),
        )
    elif case == "identity":
        ports.records = tuple(
            replace(row, identity="not-a-digest") if row.service == "backend" else row
            for row in ports.records
        )
    elif case == "runtime":
        ports.records = tuple(
            replace(row, exit_code=1) if row.service == "backend" else row
            for row in ports.records
        )
    elif case == "health":
        ports.records = tuple(
            replace(row, health="starting") if row.service == "backend" else row
            for row in ports.records
        )
    else:
        assert case == "valid"

    result = run(ports)
    trace = names(ports)
    if expected_phase is None:
        assert result.outcome is OutageOutcome.ACCEPTED
        assert result.stage is OutageStage.COMPLETE
        assert result.runtime_diagnostic is None
    else:
        assert result.outcome is OutageOutcome.FAILED
        assert result.stage is OutageStage.PREFLIGHT
        assert result.checkpoint is OutageCheckpoint.OBSERVE_RUNTIME
        assert type(result.runtime_diagnostic) is RuntimeObservationPhase
        assert result.runtime_diagnostic.value == expected_phase
        assert "stop_container" not in trace
        assert "send_message_once" not in trace
    assert trace[-2:] == ["close_clients", "release_lock"]
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert "private-observation-error" not in repr(result)
