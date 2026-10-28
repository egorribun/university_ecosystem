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
        hashed_password="synthetic-hash",
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
        SimpleNamespace(email="new@example.com", password="synthetic-input"),
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
