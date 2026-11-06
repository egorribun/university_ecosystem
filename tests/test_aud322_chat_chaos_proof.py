"""Negative controls for the Valkey outage scenario's own evidence."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa

from tests.chaos import test_resilience as resilience


@pytest.mark.parametrize(
    "bad_response", ["outage", "first-retry", "second-retry", "missing"]
)
def test_valkey_scenario_rejects_a_different_or_missing_message_id(
    monkeypatch: pytest.MonkeyPatch, bad_response: str
) -> None:
    chat_id = str(uuid.uuid4())
    sent_id, different_id = str(uuid.uuid4()), str(uuid.uuid4())
    ids: list[str | None] = [sent_id, sent_id, sent_id]
    if bad_response == "missing":
        ids = [None, None, None]
    else:
        index = {"outage": 0, "first-retry": 1, "second-retry": 2}[bad_response]
        ids[index] = different_id
    commands: list[str] = []
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite://")
    monkeypatch.setattr(resilience, "time", SimpleNamespace(sleep=lambda _: None))
    monkeypatch.setattr(resilience, "_run_docker_compose", commands.append)
    monkeypatch.setattr(
        resilience, "_assert_chat_send_db_state", lambda *_args: None, raising=False
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"id": chat_id}]})
        return httpx.Response(200, json={"id": ids.pop(0)})

    with httpx.Client(
        base_url="http://chaos.invalid", transport=httpx.MockTransport(handle)
    ) as client:
        client.cookies.set("csrf_token", "signed-csrf")
        with pytest.raises(AssertionError):
            resilience.test_valkey_outage_idempotency_fail_open(None, client)
    assert commands == ["stop valkey", "start valkey"]


@pytest.mark.parametrize(
    "state",
    [
        "valid",
        "missing-message",
        "duplicate-message",
        "wrong-response-id",
        "missing-receipt",
        "wrong-receipt-key",
        "wrong-receipt-message",
        "expired-receipt",
        "missing-event",
        "duplicate-event",
    ],
)
def test_database_probe_requires_one_scoped_message_receipt_and_event(
    tmp_path: Path, state: str
) -> None:
    probe = getattr(resilience, "_assert_chat_send_db_state", None)
    assert callable(probe), "Valkey chaos scenario needs a scoped database-state probe"
    url = f"sqlite:///{(tmp_path / 'outage-proof.sqlite').as_posix()}"
    engine = sa.create_engine(url)
    chat_id, user_id, message_id = (str(uuid.uuid4()) for _ in range(3))
    key = f"chaos-test-{uuid.uuid4()}"
    content = f"Idempotency chaos test — {key}"
    digest = hashlib.sha256(
        b"university-ecosystem:chat-send-receipt:v1\0"
        + uuid.UUID(chat_id).bytes
        + uuid.UUID(user_id).bytes
        + key.encode("utf-8")
    ).hexdigest()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE messages (id TEXT, chat_id TEXT, sender_id TEXT, content TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE chat_send_receipts (chat_id TEXT, user_id TEXT, "
                "key_digest TEXT, message_id TEXT, expires_at TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE stored_events (event_type TEXT, aggregate_type TEXT, aggregate_id TEXT)"
            )
        )
        if state != "missing-message":
            connection.execute(
                sa.text("INSERT INTO messages VALUES (:id, :chat, :user, :content)"),
                {
                    "id": message_id,
                    "chat": chat_id,
                    "user": user_id,
                    "content": content,
                },
            )
        if state == "duplicate-message":
            connection.execute(
                sa.text("INSERT INTO messages VALUES (:id, :chat, :user, :content)"),
                {
                    "id": str(uuid.uuid4()),
                    "chat": chat_id,
                    "user": user_id,
                    "content": content,
                },
            )
        if state != "missing-receipt":
            connection.execute(
                sa.text(
                    "INSERT INTO chat_send_receipts VALUES (:chat, :user, :digest, :message, :expiry)"
                ),
                {
                    "chat": chat_id,
                    "user": user_id,
                    "digest": "wrong" if state == "wrong-receipt-key" else digest,
                    "message": str(uuid.uuid4())
                    if state == "wrong-receipt-message"
                    else message_id,
                    "expiry": "2000-01-01"
                    if state == "expired-receipt"
                    else "2999-01-01",
                },
            )
        if state != "missing-event":
            connection.execute(
                sa.text(
                    "INSERT INTO stored_events VALUES ('chat.message_sent', 'Message', :id)"
                ),
                {"id": message_id},
            )
        if state == "duplicate-event":
            connection.execute(
                sa.text(
                    "INSERT INTO stored_events VALUES ('chat.message_sent', 'Message', :id)"
                ),
                {"id": message_id},
            )
    try:
        response_id = str(uuid.uuid4()) if state == "wrong-response-id" else message_id
        if state == "valid":
            probe(url, chat_id, key, content, response_id)
        else:
            with pytest.raises(AssertionError):
                probe(url, chat_id, key, content, response_id)
    finally:
        engine.dispose()
