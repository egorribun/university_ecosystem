from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scripts import live_stand
from scripts import owned_nats_sql_adapter as sql
from scripts.live_stand import ComposeResourceEvidence
from scripts.owned_nats_coordinator import (
    AdmissionEvidence,
    ChatParticipantRow,
    ChatRow,
    ChatRowsEvidence,
    CorrelationRows,
    CorrelationVerdict,
    MessageEvidence,
    MessageIntent,
    OwnerEvidence,
    PgRoleRow,
    PrincipalEvidence,
    StoredEventState,
    StoredMessageEvent,
    validate_message_correlation,
)
from scripts.owned_nats_docker import (
    ComposeConfigPins,
    ComposeMetadataResult,
    ComposeMetadataStatus,
    DaemonMetadataResult,
    DaemonMetadataStatus,
    DockerReadPins,
)
from scripts.owned_nats_outage import ContainerSnapshot, Deadline
from scripts.owned_nats_owner_adapter import SignedOwnerLeasePort
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    PrivateProcessResult,
    ProcessOutcome,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _deadline(clock: FakeClock | None = None) -> Deadline:
    return Deadline.after(30.0, clock=clock or FakeClock())


def _owner() -> OwnerEvidence:
    ports = {
        name: 20_000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    return OwnerEvidence(
        repository="/opt/ue/repository",
        worktree="/opt/ue/worktree",
        project_name="ue-live-0123456789abcdef",
        published_ports=live_stand._validate_published_ports(ports),
        schema_version=11,
        daemon_fingerprint="1" * 64,
        compose_resource_fingerprint="2" * 64,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha="a" * 40,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )


def _postgres() -> ContainerSnapshot:
    return ContainerSnapshot(
        container_id="b" * 64,
        service="postgres",
        identity="c" * 64,
        running=True,
        status="running",
        health="healthy",
        restart_count=0,
        exit_code=0,
        oom_killed=False,
    )


def _pins(
    owner: OwnerEvidence | None = None,
) -> tuple[DockerReadPins, ComposeConfigPins]:
    admitted = owner or _owner()
    return (
        DockerReadPins(
            executable="/opt/docker/bin/docker",
            endpoint="unix:///var/run/docker.sock",
            config_directory="/opt/docker/config",
            cwd=admitted.worktree,
            environment=(("LANG", "C"),),
            daemon_fingerprint=admitted.daemon_fingerprint or "",
        ),
        ComposeConfigPins(
            project_directory=admitted.repository,
            env_file=f"{admitted.worktree}/.env.docker",
            compose_files=(
                f"{admitted.repository}/{live_stand.COMPOSE_FILES[0]}",
                f"{admitted.repository}/{live_stand.OVERLAY}",
                f"{admitted.worktree}/{live_stand.IN_PLACE_OVERLAY}",
            ),
        ),
    )


def _evidence(owner: OwnerEvidence | None = None) -> ComposeResourceEvidence:
    admitted = owner or _owner()
    return ComposeResourceEvidence(
        fingerprint=admitted.compose_resource_fingerprint or "",
        managed_volumes=(),
        declared_volume_names=(),
        managed_networks=(),
        managed_services=admitted.selected_services,
        stack=admitted.stack,
        service_roots=admitted.service_roots,
        selected_services=admitted.selected_services,
        network_bindings=(),
        service_networks=(),
        service_mounts=(),
    )


def _process_result(stdout: bytes, *, stderr: bytes = b"") -> PrivateProcessResult:
    return PrivateProcessResult(
        ProcessOutcome.EXITED,
        0,
        stdout,
        stderr,
        LocalCleanup.CONFIRMED,
    )


def _admission_payload() -> dict[str, object]:
    return {
        "principal": {
            "session_user": "postgres",
            "current_user": "postgres",
            "rolname": "postgres",
            "rolsuper": True,
        },
        "users": [
            {
                "id": "00000000-0000-7000-8000-000000000001",
                "email": "admin@university.dev",
                "role": "admin",
                "is_active": True,
                "demo_seed_key": None,
            },
            {
                "id": "00000000-0000-7000-8000-000000000002",
                "email": "demo.peer@example.com",
                "role": "student",
                "is_active": True,
                "demo_seed_key": "ue-demo-v1:user:primary-peer",
            },
        ],
        "chats": [],
        "participants": [],
    }


def _admission_bytes() -> bytes:
    return json.dumps(_admission_payload(), separators=(",", ":")).encode()


def _valid_compose_bytes(user: str = "postgres", database: str = "university") -> bytes:
    return json.dumps(
        {
            "services": {
                "postgres": {
                    "environment": {
                        "POSTGRES_USER": user,
                        "POSTGRES_DB": database,
                    }
                }
            }
        },
        separators=(",", ":"),
    ).encode()


def _make_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[sql.OwnedNatsSqlAdapter, OwnerEvidence, ContainerSnapshot]:
    owner = _owner()
    docker_pins, compose_pins = _pins(owner)
    owner_port = object.__new__(SignedOwnerLeasePort)
    monkeypatch.setattr(
        SignedOwnerLeasePort,
        "read_signed_owner",
        lambda _self, *, deadline: owner,
    )
    adapter = sql.OwnedNatsSqlAdapter(owner_port, docker_pins, compose_pins)
    return adapter, owner, _postgres()


def test_psql_request_is_fixed_stdin_on_exact_captured_container() -> None:
    owner = _owner()
    pins, _compose = _pins(owner)
    postgres = _postgres()
    request = sql.prepare_psql_request(
        pins,
        postgres,
        "pending_count",
        {},
        deadline=_deadline(),
    )

    assert type(request) is PrivateProcessRequest
    assert request.argv[:5] == (
        pins.executable,
        "--config",
        pins.config_directory,
        "--host",
        pins.endpoint,
    )
    assert request.argv[5:8] == ("exec", "--interactive", postgres.container_id)
    assert "psql" in request.argv
    psql_index = request.argv.index("psql")
    assert request.argv[psql_index:] == (
        "psql",
        "-X",
        "--no-password",
        "--quiet",
        "--no-align",
        "--tuples-only",
        "-U",
        "postgres",
        "-d",
        "university",
        "--set=ON_ERROR_STOP=1",
    )
    assert (
        "-U" in request.argv
        and request.argv[request.argv.index("-U") + 1] == "postgres"
    )
    assert (
        "-d" in request.argv
        and request.argv[request.argv.index("-d") + 1] == "university"
    )
    assert "-c" not in request.argv
    assert request.stdin == sql.SQL_STATEMENTS["pending_count"]
    assert b"BEGIN READ ONLY" in request.stdin
    assert b"statement_timeout" in request.stdin
    assert b"5000ms" in request.stdin
    assert b"lock_timeout" in request.stdin
    assert b"1000ms" in request.stdin
    assert request.stdout_limit == sql._SQL_STDOUT_LIMIT
    assert request.stderr_limit == sql._SQL_STDERR_LIMIT
    assert request.input_limit == len(request.stdin)
    assert "password" not in repr(request).casefold()


@pytest.mark.parametrize(
    "bad_uuid",
    [
        "00000000-0000-0000-0000-000000000000",
        "00000000-0000-7000-8000-00000000000A",
        "not-a-uuid",
        "00000000-0000-7000-8000-000000000001' OR TRUE --",
    ],
)
def test_psql_request_rejects_noncanonical_uuid_before_transport(bad_uuid: str) -> None:
    owner = _owner()
    pins, _compose = _pins(owner)
    postgres = _postgres()

    assert (
        sql.prepare_psql_request(
            pins,
            postgres,
            "outbox_state",
            {"event_id": bad_uuid},
            deadline=_deadline(),
        )
        is None
    )


def test_effective_postgres_settings_are_exact_and_reject_overrides() -> None:
    assert sql._effective_postgres_settings(_valid_compose_bytes()) == (
        "postgres",
        "university",
    )
    assert (
        sql._effective_postgres_settings(_valid_compose_bytes(user="service_admin"))
        is None
    )
    assert (
        sql._effective_postgres_settings(
            _valid_compose_bytes(database="other_database")
        )
        is None
    )
    assert (
        sql._effective_postgres_settings(
            b'{"services":{"postgres":{"environment":["POSTGRES_USER=postgres"]}}}'
        )
        is None
    )
    assert (
        sql._effective_postgres_settings(
            b'{"services":{"postgres":{"environment":{"POSTGRES_USER":"postgres","POSTGRES_USER":"other","POSTGRES_DB":"university"}}}}'
        )
        is None
    )


def test_all_sql_shapes_use_catalog_and_principal_guards_without_write_controls() -> (
    None
):
    for statement in sql.SQL_STATEMENTS.values():
        lowered = statement.lower()
        assert b"begin read only" in lowered
        search_path = b"set local search_path to pg_catalog, pg_temp;"
        assert lowered.count(search_path) == 1
        assert lowered.index(b"begin read only") < lowered.index(search_path)
        assert lowered.index(search_path) < lowered.index(b"with\n")
        assert b"search_path to public" not in lowered
        assert b"statement_timeout" in lowered
        assert b"lock_timeout" in lowered
        assert b"session_user" in lowered
        assert b"current_user" in lowered
        assert b"pg_catalog.pg_roles" in lowered
        assert b"current_database()" in lowered
        assert b"pg_catalog.pg_class" in lowered
        assert b"pg_catalog.pg_attribute" in lowered
        assert b"app.bypass_rls" not in lowered
        assert b"set role" not in lowered
        assert b"alter role" not in lowered
        assert b"create role" not in lowered
        assert b"disable row level security" not in lowered


def test_admission_sql_surfaces_any_existing_dm_without_group_row_cap_masking_it() -> (
    None
):
    statement = sql.SQL_STATEMENTS["admission"].decode("ascii")
    pair_query = statement.split("pair_chats AS (", maxsplit=1)[1].split(
        "chat_rows AS (", maxsplit=1
    )[0]

    assert "chat_row.chat_type = 'dm'" in pair_query
    assert "LIMIT 1" in pair_query
    assert "SET ROLE" not in statement.upper()
    assert "ALTER ROLE" not in statement.upper()
    assert "INSERT INTO" not in statement.upper()
    assert "UPDATE " not in statement.upper()
    assert "DELETE FROM" not in statement.upper()


def test_decode_admission_requires_exact_postgres_principal_and_rows() -> None:
    evidence = sql.decode_admission(_admission_bytes(), deadline=_deadline())
    assert type(evidence) is AdmissionEvidence
    assert evidence.principal == PrincipalEvidence(
        "postgres", "postgres", PgRoleRow("postgres", True)
    )
    assert [row.email for row in evidence.users] == [
        "admin@university.dev",
        "demo.peer@example.com",
    ]

    wrong_principal = _admission_payload()
    wrong_principal["principal"] = {
        "session_user": "postgres",
        "current_user": "other",
        "rolname": "other",
        "rolsuper": True,
    }
    assert (
        sql.decode_admission(json.dumps(wrong_principal).encode(), deadline=_deadline())
        is None
    )


def test_decode_correlation_keeps_stored_events_primary_key_and_exact_payload() -> None:
    event_id = "00000000-0000-7000-8000-000000000009"
    message_id = "00000000-0000-7000-8000-000000000003"
    chat_id = "00000000-0000-7000-8000-000000000004"
    sender_id = "00000000-0000-7000-8000-000000000005"
    payload = {
        "database_message": {
            "message_id": message_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": "owned NATS acceptance probe",
        },
        "stored_events": [
            {
                "event_id": event_id,
                "event_type": "chat.message_sent",
                "aggregate_type": "Message",
                "aggregate_id": message_id,
                "payload": {
                    "_schema_version": 1,
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "sender_id": sender_id,
                    "content_preview": "owned NATS acceptance probe",
                },
            }
        ],
    }
    rows = sql.decode_correlation(json.dumps(payload).encode(), deadline=_deadline())

    assert type(rows) is CorrelationRows
    assert rows.database_message == MessageEvidence(
        message_id,
        chat_id,
        sender_id,
        "owned NATS acceptance probe",
    )
    assert rows.stored_events == (
        StoredMessageEvent(
            event_id,
            "chat.message_sent",
            "Message",
            message_id,
            payload["stored_events"][0]["payload"],
        ),
    )
    assert rows.stored_events[0].event_id == event_id
    payload["stored_events"].append(payload["stored_events"][0])
    duplicate_rows = sql.decode_correlation(
        json.dumps(payload).encode(), deadline=_deadline()
    )
    assert type(duplicate_rows) is CorrelationRows
    assert len(duplicate_rows.stored_events) == 2
    assert (
        validate_message_correlation(
            MessageIntent(chat_id, sender_id, "owned NATS acceptance probe"),
            rows.database_message,
            duplicate_rows.database_message,
            duplicate_rows.stored_events,
        )
        is CorrelationVerdict.INVALID_EVENT
    )


def test_decode_dm_preserves_exact_chat_and_participants_for_coordinator() -> None:
    raw = json.dumps(
        {
            "chat_rows": [
                {
                    "id": "00000000-0000-7000-8000-000000000004",
                    "chat_type": "dm",
                    "demo_seed_key": None,
                }
            ],
            "participants": [
                {
                    "chat_id": "00000000-0000-7000-8000-000000000004",
                    "user_id": "00000000-0000-7000-8000-000000000001",
                },
                {
                    "chat_id": "00000000-0000-7000-8000-000000000004",
                    "user_id": "00000000-0000-7000-8000-000000000002",
                },
            ],
            "participant_overflow": False,
        }
    ).encode()

    evidence = sql.decode_read_dm(raw, deadline=_deadline())

    assert evidence == ChatRowsEvidence(
        ChatRow("00000000-0000-7000-8000-000000000004", "dm", None),
        (
            ChatParticipantRow(
                "00000000-0000-7000-8000-000000000004",
                "00000000-0000-7000-8000-000000000001",
            ),
            ChatParticipantRow(
                "00000000-0000-7000-8000-000000000004",
                "00000000-0000-7000-8000-000000000002",
            ),
        ),
    )


def test_decode_event_state_uses_exact_stored_event_and_bounded_counts() -> None:
    event_id = "00000000-0000-7000-8000-000000000009"
    state = sql.decode_outbox_state(
        json.dumps(
            {
                "states": [
                    {
                        "stored_event_id": event_id,
                        "processed_at_present": False,
                        "error_count": 2,
                    }
                ],
                "dlq_count": 0,
            }
        ).encode(),
        expected_event_id=event_id,
        deadline=_deadline(),
    )

    assert state == StoredEventState(event_id, False, 2, 0)
    assert (
        sql.decode_outbox_state(
            json.dumps(
                {
                    "states": [
                        {
                            "stored_event_id": "00000000-0000-7000-8000-000000000010",
                            "processed_at_present": False,
                            "error_count": 2,
                        }
                    ],
                    "dlq_count": 0,
                }
            ).encode(),
            expected_event_id=event_id,
            deadline=_deadline(),
        )
        is None
    )


def test_decode_rejects_duplicate_keys_trailing_rows_and_nonfinite_json() -> None:
    bad_documents = (
        b'{"count":0,"count":1}',
        b'{"count":0}\n{"count":1}',
        b'{"count":NaN}',
        b"",
        b"null",
    )
    for raw in bad_documents:
        assert sql.decode_pending_count(raw, deadline=_deadline()) is None


def test_fake_collector_checks_owner_daemon_target_around_query(monkeypatch) -> None:
    adapter, owner, postgres = _make_adapter(monkeypatch)
    evidence = _evidence(owner)
    compose_result = ComposeMetadataResult(
        ComposeMetadataStatus.MATCHED_METADATA, evidence
    )
    daemon_reads: list[Deadline] = []
    owner_reads: list[Deadline] = []
    inspect_ids: list[tuple[str, ...]] = []
    process_calls: list[PrivateProcessRequest] = []
    process_deadlines: list[Deadline] = []

    monkeypatch.setattr(
        sql.docker,
        "observe_daemon_metadata",
        lambda _pins, *, deadline: daemon_reads.append(deadline)
        or DaemonMetadataResult(
            DaemonMetadataStatus.MATCHED_METADATA, owner.daemon_fingerprint
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_compose_config",
        lambda *_args, **_kwargs: PrivateProcessRequest(
            ("docker", "compose"),
            "/opt/ue/worktree",
            {},
            _valid_compose_bytes(),
            1000,
            100,
            1000,
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "decode_compose_config",
        lambda *_args, **_kwargs: compose_result,
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_container_inspect_reads",
        lambda _metadata, _pins, ids, *, deadline: inspect_ids.append(ids)
        or (
            PrivateProcessRequest(
                ("docker", "inspect"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
            ),
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "decode_container_inspect_reads",
        lambda _metadata, _evidence, ids, _results, *, deadline: (postgres,)
        if ids == (postgres.container_id,)
        else None,
    )
    monkeypatch.setattr(
        SignedOwnerLeasePort,
        "read_signed_owner",
        lambda _self, *, deadline: owner_reads.append(deadline) or owner,
    )

    def fake_run(request, *, deadline):
        process_calls.append(request)
        process_deadlines.append(deadline)
        if "psql" in request.argv:
            return _process_result(b'{"count":0}')
        if "compose" in request.argv:
            return _process_result(_valid_compose_bytes())
        return _process_result(b"inspect")

    monkeypatch.setattr(sql.process, "run_private_process", fake_run)

    phase = _deadline()
    assert adapter.pending_count(owner, postgres, deadline=phase) == 0
    assert len(daemon_reads) == 6
    assert len(owner_reads) == 3
    assert inspect_ids == [(postgres.container_id,), (postgres.container_id,)]
    assert all(item is daemon_reads[0] for item in daemon_reads)
    assert all(item is owner_reads[0] for item in owner_reads)
    assert all(item is daemon_reads[0] for item in process_deadlines)
    psql_calls = [call for call in process_calls if "psql" in call.argv]
    compose_calls = [call for call in process_calls if "compose" in call.argv]
    inspect_calls = [call for call in process_calls if "inspect" in call.argv]
    assert len(psql_calls) == len(compose_calls) == 1
    assert len(inspect_calls) == 2
    assert len(inspect_ids) == len(inspect_calls) == 2
    assert not any("ps" in call.argv for call in process_calls)
    assert psql_calls[0].argv[7] == postgres.container_id
    assert psql_calls[0].stdin == sql.SQL_STATEMENTS["pending_count"]


def test_fake_collector_fails_closed_on_post_query_owner_drift(monkeypatch) -> None:
    adapter, owner, postgres = _make_adapter(monkeypatch)
    evidence = _evidence(owner)
    compose_result = ComposeMetadataResult(
        ComposeMetadataStatus.MATCHED_METADATA, evidence
    )
    owner_reads = iter((owner, owner, replace(owner, project_name="other-project")))
    process_calls: list[PrivateProcessRequest] = []

    monkeypatch.setattr(
        sql.docker,
        "observe_daemon_metadata",
        lambda _pins, *, deadline: DaemonMetadataResult(
            DaemonMetadataStatus.MATCHED_METADATA, owner.daemon_fingerprint
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_compose_config",
        lambda *_args, **_kwargs: PrivateProcessRequest(
            ("docker", "compose"),
            "/opt/ue/worktree",
            {},
            _valid_compose_bytes(),
            1000,
            100,
            1000,
        ),
    )
    monkeypatch.setattr(
        sql.docker, "decode_compose_config", lambda *_a, **_k: compose_result
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_container_inspect_reads",
        lambda _metadata, _pins, ids, *, deadline: (
            PrivateProcessRequest(
                ("docker", "inspect"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
            ),
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "decode_container_inspect_reads",
        lambda _metadata, _evidence, ids, _results, *, deadline: (postgres,),
    )
    monkeypatch.setattr(
        SignedOwnerLeasePort,
        "read_signed_owner",
        lambda _self, *, deadline: next(owner_reads),
    )

    def fake_run(request, *, deadline):
        process_calls.append(request)
        if "psql" in request.argv:
            return _process_result(b'{"count":0}')
        if "compose" in request.argv:
            return _process_result(_valid_compose_bytes())
        return _process_result(b"inspect")

    monkeypatch.setattr(sql.process, "run_private_process", fake_run)

    with pytest.raises(sql.SqlReadNotReady) as caught:
        adapter.pending_count(owner, postgres, deadline=_deadline())
    assert str(caught.value) == "owner-scoped SQL read is not ready"
    assert b"count" not in str(caught.value).encode()
    assert any("psql" in call.argv for call in process_calls)


def test_owner_drift_closes_adapter_without_rebinding_on_followup(monkeypatch) -> None:
    adapter, owner, postgres = _make_adapter(monkeypatch)
    owner_reads = iter((owner, owner, replace(owner, project_name="changed-owner")))
    process_calls: list[PrivateProcessRequest] = []
    evidence = ComposeMetadataResult(
        ComposeMetadataStatus.MATCHED_METADATA, _evidence(owner)
    )

    monkeypatch.setattr(
        sql.docker,
        "observe_daemon_metadata",
        lambda _pins, *, deadline: DaemonMetadataResult(
            DaemonMetadataStatus.MATCHED_METADATA, owner.daemon_fingerprint
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_compose_config",
        lambda *_args, **_kwargs: PrivateProcessRequest(
            ("docker", "compose"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
        ),
    )
    monkeypatch.setattr(
        sql.docker, "decode_compose_config", lambda *_args, **_kwargs: evidence
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_container_inspect_reads",
        lambda *_args, **_kwargs: (
            PrivateProcessRequest(
                ("docker", "inspect"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
            ),
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "decode_container_inspect_reads",
        lambda *_args, **_kwargs: (postgres,),
    )
    monkeypatch.setattr(
        SignedOwnerLeasePort,
        "read_signed_owner",
        lambda _self, *, deadline: next(owner_reads),
    )

    def fake_run(request, *, deadline):
        process_calls.append(request)
        if "psql" in request.argv:
            return _process_result(b'{"count":0}')
        if "compose" in request.argv:
            return _process_result(_valid_compose_bytes())
        return _process_result(b"inspect")

    monkeypatch.setattr(sql.process, "run_private_process", fake_run)

    with pytest.raises(sql.SqlReadNotReady):
        adapter.pending_count(owner, postgres, deadline=_deadline())
    count_after_drift = len(process_calls)
    with pytest.raises(sql.SqlReadNotReady):
        adapter.pending_count(
            replace(owner, project_name="replacement"), postgres, deadline=_deadline()
        )
    assert len(process_calls) == count_after_drift


def test_collector_closes_on_post_query_postgres_identity_drift(monkeypatch) -> None:
    adapter, owner, postgres = _make_adapter(monkeypatch)
    compose_result = ComposeMetadataResult(
        ComposeMetadataStatus.MATCHED_METADATA, _evidence(owner)
    )
    inspect_count = 0
    process_calls: list[PrivateProcessRequest] = []
    owner_reads: list[Deadline] = []

    monkeypatch.setattr(
        sql.docker,
        "observe_daemon_metadata",
        lambda _pins, *, deadline: DaemonMetadataResult(
            DaemonMetadataStatus.MATCHED_METADATA, owner.daemon_fingerprint
        ),
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_compose_config",
        lambda *_args, **_kwargs: PrivateProcessRequest(
            ("docker", "compose"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
        ),
    )
    monkeypatch.setattr(
        sql.docker, "decode_compose_config", lambda *_args, **_kwargs: compose_result
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_container_inspect_reads",
        lambda _metadata, _pins, ids, *, deadline: (
            PrivateProcessRequest(
                ("docker", "inspect"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
            ),
        ),
    )

    def decode_inspect(_metadata, _evidence, ids, _results, *, deadline):
        nonlocal inspect_count
        inspect_count += 1
        if ids != (postgres.container_id,):
            return None
        changed = replace(postgres, identity="d" * 64)
        return (postgres if inspect_count == 1 else changed,)

    monkeypatch.setattr(sql.docker, "decode_container_inspect_reads", decode_inspect)
    monkeypatch.setattr(
        SignedOwnerLeasePort,
        "read_signed_owner",
        lambda _self, *, deadline: owner_reads.append(deadline) or owner,
    )

    def fake_run(request, *, deadline):
        process_calls.append(request)
        if "psql" in request.argv:
            return _process_result(b'{"count":0}')
        if "compose" in request.argv:
            return _process_result(_valid_compose_bytes())
        return _process_result(b"inspect")

    monkeypatch.setattr(sql.process, "run_private_process", fake_run)

    with pytest.raises(sql.SqlReadNotReady):
        adapter.pending_count(owner, postgres, deadline=_deadline())

    assert inspect_count == 2
    assert len(owner_reads) == 2
    assert any("psql" in call.argv for call in process_calls)
    calls_after_drift = len(process_calls)
    with pytest.raises(sql.SqlReadNotReady):
        adapter.pending_count(owner, postgres, deadline=_deadline())
    assert len(process_calls) == calls_after_drift


def test_expired_shared_deadline_stops_after_compose_without_inspecting_or_querying(
    monkeypatch,
) -> None:
    adapter, owner, postgres = _make_adapter(monkeypatch)
    evidence = _evidence(owner)
    compose_result = ComposeMetadataResult(
        ComposeMetadataStatus.MATCHED_METADATA, evidence
    )
    clock = FakeClock()
    phase = Deadline.after(5.0, clock=clock)
    daemon_calls = 0
    inspect_ids: list[tuple[str, ...]] = []
    process_calls: list[tuple[PrivateProcessRequest, Deadline]] = []

    def daemon_read(_pins, *, deadline):
        nonlocal daemon_calls
        daemon_calls += 1
        if daemon_calls == 2:
            clock.now = 5.0
        return DaemonMetadataResult(
            DaemonMetadataStatus.MATCHED_METADATA, owner.daemon_fingerprint
        )

    monkeypatch.setattr(sql.docker, "observe_daemon_metadata", daemon_read)
    monkeypatch.setattr(
        sql.docker,
        "prepare_compose_config",
        lambda *_args, **_kwargs: PrivateProcessRequest(
            ("docker", "compose"),
            "/opt/ue/worktree",
            {},
            b"",
            1000,
            100,
            0,
        ),
    )
    monkeypatch.setattr(
        sql.docker, "decode_compose_config", lambda *_args, **_kwargs: compose_result
    )
    monkeypatch.setattr(
        sql.docker,
        "prepare_container_inspect_reads",
        lambda _metadata, _pins, ids, *, deadline: inspect_ids.append(ids)
        or (
            PrivateProcessRequest(
                ("docker", "inspect"), "/opt/ue/worktree", {}, b"", 1000, 100, 0
            ),
        ),
    )
    monkeypatch.setattr(
        SignedOwnerLeasePort,
        "read_signed_owner",
        lambda _self, *, deadline: owner,
    )

    def fake_run(request, *, deadline):
        process_calls.append((request, deadline))
        return _process_result(_valid_compose_bytes())

    monkeypatch.setattr(sql.process, "run_private_process", fake_run)

    with pytest.raises(sql.SqlReadNotReady):
        adapter.pending_count(owner, postgres, deadline=phase)

    assert daemon_calls == 2
    assert len(process_calls) == 1
    assert "compose" in process_calls[0][0].argv
    assert inspect_ids == []
    assert all("psql" not in request.argv for request, _ in process_calls)
    assert all(deadline is process_calls[0][1] for _, deadline in process_calls)


def test_adapter_repr_and_failure_do_not_expose_pins_or_outputs(monkeypatch) -> None:
    adapter, owner, postgres = _make_adapter(monkeypatch)
    assert repr(adapter) == "<OwnedNatsSqlAdapter>"
    assert "postgres.sock" not in repr(adapter)
    assert str(sql.SqlReadNotReady()) == "owner-scoped SQL read is not ready"

    monkeypatch.setattr(
        sql.docker,
        "observe_daemon_metadata",
        lambda *_args, **_kwargs: DaemonMetadataResult(DaemonMetadataStatus.NOT_READY),
    )
    with pytest.raises(sql.SqlReadNotReady) as caught:
        adapter.pending_count(owner, postgres, deadline=_deadline())
    assert "private" not in str(caught.value).casefold()
    assert "socket" not in str(caught.value).casefold()
