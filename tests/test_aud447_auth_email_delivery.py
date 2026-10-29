"""Regression evidence for authentication links in the NATS dead-letter path."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import multiprocessing
import uuid
from datetime import UTC, datetime, timedelta
from multiprocessing.connection import Connection
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

import app.core.database as database_module
import app.core.nats_broker as nats_module
import app.services.auth_service as auth_module
import app.tasks.email as email_tasks
from app.services.auth_service import AuthService


def _sentry_probe_child(scenario: str, output: Connection) -> None:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    import app.core.logging as app_logging

    async def run_probe() -> dict[str, bool]:
        return await _sentry_probe(
            scenario, app_logging, sentry_sdk, LoggingIntegration
        )

    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            outcome = asyncio.run(run_probe())
        output.send(outcome)
    except Exception:
        # Never print captured event contents or synthetic test markers.
        output.send({"completed": False})
    finally:
        output.close()


async def _sentry_probe(
    scenario: str, app_logging: Any, sentry_sdk: Any, logging_integration: Any
) -> dict[str, bool]:
    marker = uuid.uuid4().hex
    secret = uuid.uuid4().hex
    original = "https://example.invalid/reset-password#token=" + marker
    envelope = email_tasks.seal_auth_email_link(
        original, datetime.now(UTC) + timedelta(minutes=5), secret
    )
    auth_module._token_hmac_secret = lambda: secret

    def fail_decrypt(_envelope: str, _secret: str) -> str:
        raise ValueError(marker)

    def fail_build(
        link: str, _name: str, *, locale: str | None
    ) -> tuple[str, str, str]:
        raise ValueError(link)

    async def fail_delivery(**kwargs: Any) -> None:
        link = kwargs["fallback_fields"]["link"]
        if scenario == "cancel":
            raise asyncio.CancelledError(link)
        try:
            raise ValueError(link)
        except ValueError as cause:
            raise RuntimeError(link) from cause

    if scenario == "decrypt":
        email_tasks._open_auth_email_link = fail_decrypt
    elif scenario == "build":
        email_tasks.email_utils.build_reset_email_content = fail_build
    else:
        email_tasks._deliver_email_message = fail_delivery

    events: list[dict[str, Any]] = []
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        app_logging.configure_logging(level=logging.INFO, json_output=True)
        sentry_sdk.init(
            dsn=f"https://{uuid.uuid4().hex}@example.invalid/1",
            integrations=[
                logging_integration(level=logging.INFO, event_level=logging.ERROR)
            ],
            send_default_pii=False,
            transport=events.append,
        )

        async def worker(ciphertext: str) -> bool:
            handler = email_tasks.broker._tasks["app.tasks.email.send_auth_email"]
            try:
                await handler(
                    "student@example.invalid", ciphertext, encrypted_link=True
                )
            except BaseException as exc:
                nats_module._logger.exception(
                    "Error processing task %s: %s", "auth.email", exc
                )
                return isinstance(exc, asyncio.CancelledError)
            raise AssertionError("expected synthetic handler failure")

        cancelled = await worker(envelope)
        sentry_sdk.flush(timeout=1)

    values = ((events[0].get("exception") or {}).get("values") or []) if events else []
    frames = [
        frame
        for value in values
        for frame in (value.get("stacktrace") or {}).get("frames", [])
    ]
    return {
        "completed": True,
        "captured": len(events) == 1,
        "safe_event": marker not in json.dumps(events, default=str),
        "safe_log": marker not in stream.getvalue(),
        "one_exception": len(values) == 1,
        "handler_frame_present": any(
            frame.get("function") == "send_auth_email" for frame in frames
        ),
        "cancel_propagated": cancelled == (scenario == "cancel"),
    }


@pytest.mark.parametrize("scenario", ["decrypt", "build", "delivery", "cancel"])
def test_aud447_sentry_events_do_not_capture_plaintext_frames(scenario: str) -> None:
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_sentry_probe_child, args=(scenario, send))
    process.start()
    send.close()
    try:
        assert receive.poll(30), "the isolated Sentry probe timed out"
        outcome = receive.recv()
        process.join(timeout=5)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join()
        receive.close()
    assert outcome["completed"], "the isolated Sentry probe failed"
    assert outcome["captured"]
    assert outcome["safe_event"], "a Sentry event contained the synthetic marker"
    assert outcome["safe_log"]
    assert outcome["one_exception"]
    assert outcome["handler_frame_present"]
    assert outcome["cancel_propagated"]


class _Session:
    def __init__(self) -> None:
        self.jobs: list[Any] = []

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> SimpleNamespace:
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, job: Any) -> None:
        self.jobs.append(job)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_aud447_reset_delivery_failure_never_parks_the_token_in_dlq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # All markers and key material are generated locally and are never printed.
    marker = "synthetic-" + uuid.uuid4().hex
    key_material = uuid.uuid4().hex
    user = SimpleNamespace(id=uuid.uuid4(), email="student@example.test", full_name="")
    auth_repo = MagicMock()
    auth_repo.create_password_reset_token = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_by_email = AsyncMock(return_value=user)
    uow = MagicMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.commit = AsyncMock()
    service = AuthService(MagicMock(), auth_repo, user_repo, MagicMock(), uow)
    monkeypatch.setattr(
        auth_module,
        "settings",
        SimpleNamespace(
            token_hmac_secret=key_material,
            environment="testing",
            secret_key=key_material,
            app_base_url_clean="https://portal.example.test",
        ),
    )
    monkeypatch.setattr(auth_module.secrets, "token_urlsafe", lambda _size: marker)
    monkeypatch.setattr(auth_module, "resolve_locale", lambda **_kwargs: "en")
    monkeypatch.setattr("app.core.ratelimit.enforce_rate_limit", AsyncMock())
    monkeypatch.setattr(
        "app.core.ratelimit.get_default_strategy", lambda _key: object()
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    js = AsyncMock()
    monkeypatch.setattr(email_tasks.broker, "_js", js)
    monkeypatch.setattr(
        email_tasks.broker,
        "enqueue",
        nats_module.NatsTaskBroker.enqueue.__get__(email_tasks.broker),
    )
    background_tasks = BackgroundTasks()
    await service.initiate_password_reset(user.email, MagicMock(), background_tasks)
    await background_tasks.tasks[0]()
    wire = js.publish.await_args.args[1]
    task = nats_module._NatsTaskPayload.model_validate(json.loads(wire))

    # Simulate a delivery exception that includes the decrypted link. The NATS
    # worker persists str(exception), so the handler must suppress that detail.
    built_links: list[str] = []

    def build(link: str, _name: str, *, locale: str | None) -> tuple[str, str, str]:
        built_links.append(link)
        return ("subject", "plain", "<p>html</p>")

    async def fail_delivery(**_kwargs: object) -> None:
        raise RuntimeError(built_links[-1])

    monkeypatch.setattr(email_tasks.email_utils, "build_reset_email_content", build)
    monkeypatch.setattr(email_tasks, "_deliver_email_message", fail_delivery)
    handler = email_tasks.broker._tasks[task.name]
    with pytest.raises(Exception) as failure:
        await handler(*task.args, **task.kwargs)

    session = _Session()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    saved = await email_tasks.broker._dead_letter(task, str(failure.value), 3)
    assert saved and len(session.jobs) == 1

    # Keep failure output to booleans, never the token, wire body or stored job.
    delivered_original_link = marker in built_links[0]
    wire_safe = marker not in wire.decode()
    stored_payload_safe = marker not in session.jobs[0].payload
    stored_error_safe = marker not in session.jobs[0].error_message
    assert delivered_original_link
    assert wire_safe, "the NATS payload contained the synthetic marker"
    assert stored_payload_safe, (
        "the persisted DLQ payload contained the synthetic marker"
    )
    assert stored_error_safe, "the persisted DLQ error contained the synthetic marker"
    await email_tasks.broker.replay_dead_letter(
        task.name, json.loads(session.jobs[0].payload)
    )
    replay = json.loads(js.publish.await_args.args[1])
    replay_preserved_envelope = (
        replay["args"] == list(task.args) and replay["kwargs"] == task.kwargs
    )
    assert replay_preserved_envelope
    envelope = json.loads(
        email_tasks._auth_email_cipher(key_material).decrypt(
            task.args[1].encode("ascii")
        )
    )
    stored_expiry = auth_repo.create_password_reset_token.await_args.kwargs[
        "expires_at"
    ]
    assert datetime.fromisoformat(envelope["expires_at"]) == stored_expiry


@pytest.mark.asyncio
async def test_aud447_email_change_queues_an_encrypted_link_with_the_record_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.auth.security as security_module

    marker = "synthetic-" + uuid.uuid4().hex
    secret = uuid.uuid4().hex
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="student@example.test",
        hashed_password=uuid.uuid4().hex,
        profile=SimpleNamespace(full_name="Student"),
        model_dump=lambda: {},
    )
    auth_repo = MagicMock()
    auth_repo.create_email_change_token = AsyncMock()
    user_repo = MagicMock()
    user_repo.check_email_exists = AsyncMock(return_value=False)
    user_repo.get = AsyncMock(return_value=user)
    uow = MagicMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.commit = AsyncMock()
    service = AuthService(MagicMock(), auth_repo, user_repo, MagicMock(), uow)
    monkeypatch.setattr(
        auth_module,
        "settings",
        SimpleNamespace(
            token_hmac_secret=secret,
            environment="testing",
            secret_key=secret,
            app_base_url_clean="https://portal.example.test",
        ),
    )
    monkeypatch.setattr(auth_module.secrets, "token_urlsafe", lambda _size: marker)
    monkeypatch.setattr(auth_module, "resolve_locale", lambda **_kwargs: "en")
    monkeypatch.setattr(
        security_module, "verify_password", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        auth_module, "ensure_mfa_relationships_loaded", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth_module, "attach_pending_email", AsyncMock(return_value=user)
    )
    kick = AsyncMock()
    monkeypatch.setattr(auth_module.send_auth_email, "kick", kick)

    await service.initiate_email_change(
        user,
        SimpleNamespace(email="new@example.com", password=uuid.uuid4().hex),
        MagicMock(),
        BackgroundTasks(),
    )

    kick.assert_awaited_once()
    assert kick.await_args.kwargs["encrypted_link"] is True
    sealed_link = kick.await_args.args[1]
    protected = marker not in sealed_link
    assert protected
    envelope = json.loads(
        email_tasks._auth_email_cipher(secret).decrypt(sealed_link.encode("ascii"))
    )
    expires_at = auth_repo.create_email_change_token.await_args.kwargs["expires_at"]
    assert datetime.fromisoformat(envelope["expires_at"]) == expires_at
    restores_original = marker in email_tasks._open_auth_email_link(sealed_link, secret)
    assert restores_original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["expired", "tampered", "rotated", "marked_plaintext", "naive_expiry", "bad_link"],
)
async def test_aud447_unreadable_or_expired_marked_links_fail_closed(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    secret = uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    expiry = datetime.now(UTC) + timedelta(minutes=-1 if case == "expired" else 5)
    if case == "naive_expiry":
        expiry = expiry.replace(tzinfo=None)
    envelope = email_tasks.seal_auth_email_link(link, expiry, secret)
    if case == "tampered":
        index = len(envelope) // 2
        replacement = "A" if envelope[index] != "A" else "B"
        envelope = envelope[:index] + replacement + envelope[index + 1 :]
    elif case == "marked_plaintext":
        envelope = link
    elif case == "bad_link":
        malformed = json.dumps({"link": None, "expires_at": expiry.isoformat()})
        envelope = (
            email_tasks._auth_email_cipher(secret).encrypt(malformed.encode()).decode()
        )
    read_secret = uuid.uuid4().hex if case == "rotated" else secret
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: read_secret)
    build = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "build_reset_email_content", build)
    handler = email_tasks.broker._tasks["app.tasks.email.send_auth_email"]

    with pytest.raises(
        RuntimeError, match=r"^Authentication email delivery failed$"
    ) as failure:
        await handler("student@example.test", envelope, encrypted_link=True)

    error_safe = marker not in str(failure.value)
    assert error_safe
    build.assert_not_called()


@pytest.mark.asyncio
async def test_aud447_legacy_unmarked_queued_links_remain_deliverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    built_links: list[str] = []

    def build(value: str, _name: str, *, locale: str | None) -> tuple[str, str, str]:
        built_links.append(value)
        return ("subject", "plain", "<p>html</p>")

    deliver = AsyncMock()
    monkeypatch.setattr(email_tasks.email_utils, "build_reset_email_content", build)
    monkeypatch.setattr(email_tasks, "_deliver_email_message", deliver)
    handler = email_tasks.broker._tasks["app.tasks.email.send_auth_email"]
    await handler("student@example.test", link)

    delivered_original_link = built_links == [link]
    assert delivered_original_link
    deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_aud447_smtp_error_does_not_log_decrypted_link(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import app.core.config as config_module

    marker = "synthetic-" + uuid.uuid4().hex
    secret = uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    envelope = email_tasks.seal_auth_email_link(
        link, datetime.now(UTC) + timedelta(minutes=5), secret
    )
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    monkeypatch.setattr(
        config_module,
        "settings",
        SimpleNamespace(
            mail_from="sender@example.test",
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            smtp_security="none",
            smtp_starttls=False,
            is_development=True,
            environment="testing",
        ),
    )
    client = MagicMock()
    client.connect = AsyncMock()
    client.send_message = AsyncMock(side_effect=OSError(link))
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", MagicMock(return_value=client))
    handler = email_tasks.broker._tasks["app.tasks.email.send_auth_email"]

    await handler("student@example.test", envelope, encrypted_link=True)

    matching = [
        record
        for record in caplog.records
        if record.msg == "password.reset_email.error"
    ]
    assert len(matching) == 1
    assert not matching[0].exc_info
    safe_log = marker not in repr(matching[0].__dict__)
    assert safe_log


@pytest.mark.asyncio
async def test_aud447_legacy_delivery_failure_protects_dlq_payload_and_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Already-queued plaintext must not be persisted again after failure."""
    marker = "synthetic-" + uuid.uuid4().hex
    legacy_link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    task = nats_module._NatsTaskPayload.model_validate(
        {
            "id": str(uuid.uuid4()),
            "name": "app.tasks.email.send_auth_email",
            "args": ["student@example.test", legacy_link],
            "kwargs": {},
        }
    )
    deliveries: list[bool] = []

    async def fail_delivery(**kwargs: Any) -> None:
        deliveries.append(kwargs["fallback_fields"]["link"] == legacy_link)
        raise RuntimeError(legacy_link)

    monkeypatch.setattr(email_tasks, "_deliver_email_message", fail_delivery)
    handler = email_tasks.broker._tasks[task.name]
    with pytest.raises(
        RuntimeError, match=r"^Authentication email delivery failed$"
    ) as failure:
        await handler(*task.args, **task.kwargs)
    assert deliveries == [True]

    # The broker and DLQ serializer are real. Only database transport uses the
    # existing sink; this proves stored model values, not a PostgreSQL commit.
    session = _Session()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    saved = await email_tasks.broker._dead_letter(task, str(failure.value), 3)
    parked_once = saved and len(session.jobs) == 1
    assert parked_once, "the legacy task must retain its retryable DLQ record"

    # Failure output contains booleans, never the link, marker, or stored job.
    stored_payload_safe = marker not in session.jobs[0].payload
    stored_error_safe = marker not in session.jobs[0].error_message
    assert stored_error_safe, "the persisted DLQ error contained the synthetic marker"
    assert stored_payload_safe, (
        "the persisted legacy DLQ payload contained the synthetic marker"
    )

    # Protection must not erase the link or make supported legacy jobs
    # undeliverable: actual replay must still restore the original email link.
    js = AsyncMock()
    monkeypatch.setattr(email_tasks.broker, "_js", js)
    monkeypatch.setattr(
        email_tasks.broker,
        "enqueue",
        nats_module.NatsTaskBroker.enqueue.__get__(email_tasks.broker),
    )
    await email_tasks.broker.replay_dead_letter(
        task.name, json.loads(session.jobs[0].payload)
    )
    wire = js.publish.await_args.args[1]
    wire_safe = marker not in wire.decode()
    assert wire_safe, "the replayed NATS payload contained the synthetic marker"
    replay = nats_module._NatsTaskPayload.model_validate(json.loads(wire))

    async def deliver_replay(**kwargs: Any) -> None:
        deliveries.append(kwargs["fallback_fields"]["link"] == legacy_link)

    monkeypatch.setattr(email_tasks, "_deliver_email_message", deliver_replay)
    await handler(*replay.args, **replay.kwargs)
    assert deliveries == [True, True]


class _HashLookupSession(_Session):
    """Evaluate only the real DLQ hash lookup; no database persistence claim."""

    async def execute(self, statement: Any) -> SimpleNamespace:
        parameters = list(statement.compile().params.values())
        assert len(parameters) == 1
        requested_hash = parameters[0]
        assert isinstance(requested_hash, str) and len(requested_hash) == 64
        existing = next(
            (job for job in self.jobs if job.job_hash == requested_hash), None
        )
        return SimpleNamespace(scalar_one_or_none=lambda: existing)

    def add(self, job: Any) -> None:
        # SQLAlchemy applies this column default at INSERT in a real session.
        job.status = "pending"
        super().add(job)


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["enqueue", "replay"])
@pytest.mark.parametrize("call_style", ["positional", "keyword"])
async def test_aud447_plaintext_entrypoints_protect_links_without_changing_delivery(
    monkeypatch: pytest.MonkeyPatch, entrypoint: str, call_style: str
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password?next=a%2Bb#token={marker}"
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    broker = nats_module.NatsTaskBroker()
    js = AsyncMock()
    monkeypatch.setattr(broker, "_js", js)
    name = "app.tasks.email.send_auth_email"
    payload: dict[str, Any]
    if call_style == "positional":
        payload = {"args": ["student@example.test", link], "kwargs": {}}
    else:
        payload = {
            "args": [],
            "kwargs": {"to_email": "student@example.test", "link": link},
        }
    original = json.dumps(payload, sort_keys=True)

    if entrypoint == "enqueue":
        await broker.enqueue(name, *payload["args"], **payload["kwargs"])
    else:
        # This is an already-stored legacy payload, not one prepared by a producer.
        await broker.replay_dead_letter(name, payload)

    assert js.publish.await_count == 1
    wire = js.publish.await_args.args[1]
    wire_safe = marker not in wire.decode()
    source_unchanged = json.dumps(payload, sort_keys=True) == original
    assert wire_safe, "the NATS payload contained the synthetic marker"
    assert source_unchanged, "queue preparation mutated the caller's legacy payload"
    task = nats_module._NatsTaskPayload.model_validate(json.loads(wire))
    delivered: list[bool] = []

    async def capture(**kwargs: Any) -> None:
        delivered.append(kwargs["fallback_fields"]["link"] == link)

    monkeypatch.setattr(email_tasks, "_deliver_email_message", capture)
    await email_tasks.broker._tasks[name](*task.args, **task.kwargs)
    assert delivered == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_status", ["pending", "completed", "failed"])
@pytest.mark.parametrize("call_style", ["positional", "keyword"])
async def test_aud447_legacy_parking_keeps_logical_dedup_and_protects_reopened_rows(
    monkeypatch: pytest.MonkeyPatch, existing_status: str, call_style: str
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    other_marker = "synthetic-" + uuid.uuid4().hex
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    session = _HashLookupSession()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    broker = nats_module.NatsTaskBroker()
    name = "app.tasks.email.send_auth_email"

    def legacy_task(token: str) -> nats_module._NatsTaskPayload:
        link = f"https://portal.example.test/reset-password#token={token}"
        if call_style == "positional":
            args, kwargs = ["student@example.test", link], {}
        else:
            args, kwargs = [], {"to_email": "student@example.test", "link": link}
        return nats_module._NatsTaskPayload.model_validate(
            {"id": str(uuid.uuid4()), "name": name, "args": args, "kwargs": kwargs}
        )

    assert await broker._dead_letter(legacy_task(marker), "delivery failed", 3)
    assert len(session.jobs) == 1
    original_job = session.jobs[0]
    original_hash = original_job.job_hash
    original_job.status = existing_status
    original_job.retry_count = 2

    # A fresh task ID and fresh input object must still find the logical job.
    assert await broker._dead_letter(legacy_task(marker), "delivery failed", 4)
    same_job = len(session.jobs) == 1 and session.jobs[0] is original_job
    assert same_job, "the same legacy task created a second DLQ record"
    same_hash = original_job.job_hash == original_hash
    assert same_hash
    assert original_job.status == "pending"
    assert original_job.retry_count == (2 if existing_status == "pending" else 0)

    # Positive control: genuinely different links must not collapse together.
    assert await broker._dead_letter(legacy_task(other_marker), "delivery failed", 3)
    assert len(session.jobs) == 2
    hashes_distinct = session.jobs[0].job_hash != session.jobs[1].job_hash
    payloads_safe = all(
        marker not in job.payload and other_marker not in job.payload
        for job in session.jobs
    )
    assert hashes_distinct
    assert payloads_safe, "a stored or reopened payload contained a synthetic marker"


async def _aud447_queue_park_and_replay(
    broker: nats_module.NatsTaskBroker,
    js: AsyncMock,
    session: _Session,
    payload: dict[str, Any],
) -> nats_module._NatsTaskPayload:
    name = "app.tasks.email.send_auth_email"
    await broker.enqueue(name, *payload["args"], **payload["kwargs"])
    task = nats_module._NatsTaskPayload.model_validate(
        json.loads(js.publish.await_args.args[1])
    )
    assert await broker._dead_letter(task, "delivery failed", 3)
    assert len(session.jobs) == 1
    await broker.replay_dead_letter(name, json.loads(session.jobs[0].payload))
    return nats_module._NatsTaskPayload.model_validate(
        json.loads(js.publish.await_args.args[1])
    )


@pytest.mark.asyncio
async def test_aud447_sealed_round_trip_preserves_bytes_and_native_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    clock = [datetime(2026, 10, 29, 12, 0, tzinfo=UTC)]
    native_expiry = clock[0] + timedelta(minutes=2)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            if tz is not None:
                return clock[0].astimezone(tz)
            return clock[0].replace(tzinfo=None)

    monkeypatch.setattr(email_tasks, "datetime", FrozenDateTime)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    envelope = email_tasks.seal_auth_email_link(link, native_expiry, secret)
    payload = {
        "args": ["student@example.test", envelope],
        "kwargs": {"encrypted_link": True},
    }
    broker = nats_module.NatsTaskBroker()
    js = AsyncMock()
    monkeypatch.setattr(broker, "_js", js)
    session = _Session()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    replay = await _aud447_queue_park_and_replay(broker, js, session, payload)
    assert js.publish.await_count == 2
    serialized = [json.loads(call.args[1]) for call in js.publish.await_args_list]
    serialized.append(json.loads(session.jobs[0].payload))
    bytes_preserved = all(
        item["args"] == payload["args"] and item["kwargs"] == payload["kwargs"]
        for item in serialized
    )
    assert bytes_preserved, "queue or DLQ preparation rewrote a sealed payload"
    decoded = json.loads(
        email_tasks._auth_email_cipher(secret).decrypt(replay.args[1].encode("ascii"))
    )
    exact_expiry = decoded["expires_at"] == native_expiry.isoformat()
    assert exact_expiry, "queue preparation changed the original envelope expiry"
    delivered: list[bool] = []

    async def capture(**kwargs: Any) -> None:
        delivered.append(kwargs["fallback_fields"]["link"] == link)

    monkeypatch.setattr(email_tasks, "_deliver_email_message", capture)
    handler = email_tasks.broker._tasks[replay.name]
    clock[0] = native_expiry - timedelta(microseconds=1)
    await handler(*replay.args, **replay.kwargs)
    assert delivered == [True]
    clock[0] = native_expiry
    session.jobs.clear()
    js.reset_mock()
    expired_replay = await _aud447_queue_park_and_replay(broker, js, session, payload)
    assert js.publish.await_count == 2
    expired_serialized = [
        json.loads(call.args[1]) for call in js.publish.await_args_list
    ]
    expired_serialized.append(json.loads(session.jobs[0].payload))
    expired_bytes_preserved = all(
        item["args"] == payload["args"] and item["kwargs"] == payload["kwargs"]
        for item in expired_serialized
    )
    assert expired_bytes_preserved, "storage changed an expired sealed payload"
    with pytest.raises(RuntimeError, match=r"^Authentication email delivery failed$"):
        await handler(*expired_replay.args, **expired_replay.kwargs)
    assert delivered == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["expired", "tampered", "marked_plaintext", "missing_expiry"]
)
async def test_aud447_marked_round_trip_never_falls_back_to_legacy_delivery(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    future = datetime.now(UTC) + timedelta(minutes=5)
    broker = nats_module.NatsTaskBroker()
    js = AsyncMock()
    monkeypatch.setattr(broker, "_js", js)
    session = _Session()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    delivered: list[bool] = []

    async def capture(**kwargs: Any) -> None:
        delivered.append(kwargs["fallback_fields"]["link"] == link)

    monkeypatch.setattr(email_tasks, "_deliver_email_message", capture)
    handler = email_tasks.broker._tasks["app.tasks.email.send_auth_email"]

    # Valid input must traverse the same real broker/DLQ path before a negative
    # case can pass; an unconditional rejection is not a security fix.
    valid = email_tasks.seal_auth_email_link(link, future, secret)
    replay = await _aud447_queue_park_and_replay(
        broker,
        js,
        session,
        {
            "args": ["student@example.test", valid],
            "kwargs": {"encrypted_link": True},
        },
    )
    await handler(*replay.args, **replay.kwargs)
    assert delivered == [True]
    session.jobs.clear()
    js.reset_mock()
    delivered.clear()

    if case == "expired":
        bad = email_tasks.seal_auth_email_link(
            link, datetime.now(UTC) - timedelta(minutes=1), secret
        )
    elif case == "tampered":
        index = len(valid) // 2
        replacement = "A" if valid[index] != "A" else "B"
        bad = valid[:index] + replacement + valid[index + 1 :]
    elif case == "marked_plaintext":
        bad = link
    else:
        bad = (
            email_tasks._auth_email_cipher(secret)
            .encrypt(json.dumps({"link": link}).encode())
            .decode()
        )

    # A safe early rejection is allowed. If accepted for transport, the actual
    # handler must reject rather than reinterpret a marked link as legacy.
    with pytest.raises((ValueError, RuntimeError)) as failure:
        replay = await _aud447_queue_park_and_replay(
            broker,
            js,
            session,
            {
                "args": ["student@example.test", bad],
                "kwargs": {"encrypted_link": True},
            },
        )
        await handler(*replay.args, **replay.kwargs)

    error_safe = marker not in str(failure.value)
    wire_safe = all(
        marker not in call.args[1].decode() for call in js.publish.await_args_list
    )
    stored_safe = all(marker not in job.payload for job in session.jobs)
    assert error_safe, "rejection exposed the synthetic marker"
    assert wire_safe, "a rejected marked payload exposed the marker on NATS"
    assert stored_safe, "a rejected marked payload exposed the marker in the DLQ"
    assert delivered == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["marked_plaintext", "tampered", "missing_expiry", "rotated"]
)
async def test_aud447_unsafe_marked_parking_uses_existing_nak_without_plaintext(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    read_secret = [secret]
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: read_secret[0])
    envelope = email_tasks.seal_auth_email_link(
        link, datetime.now(UTC) + timedelta(minutes=5), secret
    )
    session = _Session()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    broker = nats_module.NatsTaskBroker()
    message = SimpleNamespace(
        metadata=SimpleNamespace(num_delivered=nats_module._MAX_DELIVERIES),
        ack=AsyncMock(),
        nak=AsyncMock(),
        term=AsyncMock(),
    )

    def marked_task(value: str) -> nats_module._NatsTaskPayload:
        return nats_module._NatsTaskPayload.model_validate(
            {
                "id": str(uuid.uuid4()),
                "name": "app.tasks.email.send_auth_email",
                "args": ["student@example.test", value],
                "kwargs": {"encrypted_link": True},
            }
        )

    # Actual safe parking must persist before TERM, not reject every auth task.
    await broker._retry_or_dead_letter(message, marked_task(envelope), "failed")
    assert len(session.jobs) == 1
    control_safe = marker not in session.jobs[0].payload
    assert control_safe
    message.term.assert_awaited_once_with()
    message.nak.assert_not_awaited()
    message.ack.assert_not_awaited()
    session.jobs.clear()
    message.term.reset_mock()
    caplog.clear()

    if case == "marked_plaintext":
        invalid = link
    elif case == "tampered":
        index = len(envelope) // 2
        replacement = "A" if envelope[index] != "A" else "B"
        invalid = envelope[:index] + replacement + envelope[index + 1 :]
    elif case == "missing_expiry":
        invalid = (
            email_tasks._auth_email_cipher(secret)
            .encrypt(json.dumps({"link": link}).encode())
            .decode()
        )
    else:
        invalid = envelope
        read_secret[0] = uuid.uuid4().hex

    with caplog.at_level(logging.WARNING, logger="app.core.nats_broker"):
        await broker._retry_or_dead_letter(message, marked_task(invalid), "failed")

    assert len(session.jobs) == 0, "unsafe input must not create a DLQ row"
    message.term.assert_not_awaited()
    message.ack.assert_not_awaited()
    expected_delay = min(
        nats_module._RETRY_BASE_DELAY_S * 2 ** (nats_module._MAX_DELIVERIES - 1),
        nats_module._RETRY_MAX_DELAY_S,
    )
    message.nak.assert_awaited_once_with(delay=expected_delay)
    failure_logs = [
        record
        for record in caplog.records
        if record.name == "app.core.nats_broker" and record.levelno >= logging.WARNING
    ]
    failure_recorded = bool(failure_logs)
    logs_safe = all(marker not in repr(record.__dict__) for record in failure_logs)
    no_traceback = all(not record.exc_info for record in failure_logs)
    assert failure_recorded, "safe parking failure must remain observable"
    assert logs_safe, "parking failure logs contained the synthetic marker"
    assert no_traceback, "parking rejection must not report raw-payload frames"


@pytest.mark.asyncio
@pytest.mark.parametrize("call_style", ["positional", "keyword"])
@pytest.mark.parametrize(
    "flag_present", [False, True], ids=["absent", "explicit-false"]
)
async def test_aud447_protected_replay_reopens_original_legacy_job_without_hash_drift(
    monkeypatch: pytest.MonkeyPatch, call_style: str, flag_present: bool
) -> None:
    from app.workers.dead_letter_queue import compute_job_hash

    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    name = "app.tasks.email.send_auth_email"
    payload: dict[str, Any]
    if call_style == "positional":
        payload = {"args": ["student@example.test", link], "kwargs": {}}
    else:
        payload = {
            "args": [],
            "kwargs": {"to_email": "student@example.test", "link": link},
        }
    if flag_present:
        payload["kwargs"]["encrypted_link"] = False
    original = json.dumps(payload, sort_keys=True)
    expected_hash = compute_job_hash(name, payload)
    legacy = nats_module._NatsTaskPayload.model_validate(
        {"id": str(uuid.uuid4()), "name": name, **payload}
    )
    session = _HashLookupSession()
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    broker = nats_module.NatsTaskBroker()
    js = AsyncMock()
    monkeypatch.setattr(broker, "_js", js)

    assert await broker._dead_letter(legacy, "initial delivery failed", 3)
    assert len(session.jobs) == 1
    original_job = session.jobs[0]
    original_hash_preserved = original_job.job_hash == expected_hash
    assert original_hash_preserved, "legacy parking changed the original logical hash"
    stored_payloads = [original_job.payload]
    original_job.status = "completed"
    original_job.retry_count = 2

    # Replay the real stored representation, not a freshly prepared raw task.
    await broker.replay_dead_letter(name, json.loads(original_job.payload))
    assert js.publish.await_count == 1
    wire = js.publish.await_args.args[1]
    replay = nats_module._NatsTaskPayload.model_validate(json.loads(wire))
    assert await broker._dead_letter(replay, "replayed delivery failed", 4)

    same_job = len(session.jobs) == 1 and session.jobs[0] is original_job
    assert same_job, "protected replay created a second logical DLQ record"
    same_hash = original_job.job_hash == expected_hash
    assert same_hash, "protected replay changed the original logical hash"
    assert original_job.status == "pending"
    assert original_job.retry_count == 0
    stored_payloads.append(original_job.payload)

    # An active duplicate must not reset its retry budget or overwrite the row.
    original_job.retry_count = 2
    pending_payload = original_job.payload
    pending_error = original_job.error_message
    pending_retry_at = original_job.next_retry_at
    assert await broker._dead_letter(replay, "another replay failure", 5)
    still_same_job = len(session.jobs) == 1 and session.jobs[0] is original_job
    assert still_same_job, "an active protected duplicate created another DLQ record"
    pending_unchanged = (
        original_job.job_hash == expected_hash
        and original_job.status == "pending"
        and original_job.retry_count == 2
        and original_job.payload == pending_payload
        and original_job.error_message == pending_error
        and original_job.next_retry_at == pending_retry_at
    )
    assert pending_unchanged, "an active duplicate rewrote or reset the pending job"

    # Keep all sensitive comparisons boolean-only in pytest failure output.
    legacy_after = json.dumps(
        {"args": legacy.args, "kwargs": legacy.kwargs}, sort_keys=True
    )
    source_unchanged = (
        json.dumps(payload, sort_keys=True) == original and legacy_after == original
    )
    wire_safe = marker not in wire.decode()
    stored_payloads_safe = all(marker not in value for value in stored_payloads)
    assert source_unchanged, "parking or replay mutated the original legacy input"
    assert wire_safe, "protected replay published the synthetic marker"
    assert stored_payloads_safe, "initial or reopened storage contained the marker"
