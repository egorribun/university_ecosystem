"""Replace plaintext auth-email tokens retained in dead_letter_jobs (AUD-447).

Revision ID: 202610310001
Revises: 202610250001
Create Date: 2026-10-31 00:00:00.000000

Password-reset and e-mail-confirmation links were stored verbatim in
``dead_letter_jobs.payload`` and echoed into ``error_message``. Rows whose auth
payload is already sealed (``kwargs.encrypted_link`` is true) are kept. Every
other row that still carries a plaintext ``#token=`` / ``?token=`` link, and any
unreadable auth payload that cannot be proven sealed, has its payload replaced
by the quarantine tombstone that ``DeadLetterQueue.quarantine_auth_payload()``
writes. Error text that echoes such a link is replaced by the same tombstone.

The scan is keyset-batched and idempotent: scrubbed rows already hold the
tombstone, so a rerun changes nothing. Identity, hash and retry state are kept,
so a scrubbed row still fails closed on replay. The scrub cannot be reversed,
because the removed plaintext is not recoverable; downgrade is therefore a no-op.
This module must not import application code at migration time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202610310001"
down_revision: str | None = "202610250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTH_EMAIL_JOB_TYPE = "app.tasks.email.send_auth_email"
# Byte-for-byte the value of app.workers.dead_letter_queue._QUARANTINED_AUTH_PAYLOAD.
QUARANTINED_AUTH_PAYLOAD = json.dumps({"kind": "auth-email-quarantined-v1"})
_PLAINTEXT_TOKEN = re.compile(r"[#?&]token=[^\s&\"'<>]+")
_BATCH_SIZE = 500


def _is_sealed_auth_payload(parsed: object) -> bool:
    """Return whether an auth task payload carries a sealed link envelope."""
    if not isinstance(parsed, dict):
        return False
    kwargs = parsed.get("kwargs")
    return isinstance(kwargs, dict) and kwargs.get("encrypted_link") is True


def _payload_needs_scrub(job_type: str, payload: str) -> bool:
    if payload == QUARANTINED_AUTH_PAYLOAD:
        return False
    if _PLAINTEXT_TOKEN.search(payload):
        return True
    if job_type != AUTH_EMAIL_JOB_TYPE:
        return False
    try:
        parsed = json.loads(payload)
    except ValueError:
        # Unreadable auth bytes cannot be proven sealed, so they are scrubbed too.
        return True
    return not _is_sealed_auth_payload(parsed)


def _scrubbed_rows(rows) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    for row in rows:
        payload = row.payload
        if _payload_needs_scrub(row.job_type, payload):
            payload = QUARANTINED_AUTH_PAYLOAD
        error_message = row.error_message
        if error_message and _PLAINTEXT_TOKEN.search(error_message):
            error_message = QUARANTINED_AUTH_PAYLOAD
        if (payload, error_message) != (row.payload, row.error_message):
            changes.append(
                {"id": row.id, "payload": payload, "error_message": error_message}
            )
    return changes


def upgrade() -> None:
    bind = op.get_bind()
    last_id = 0
    while True:
        rows = bind.execute(
            sa.text(
                "SELECT id, job_type, payload, error_message FROM dead_letter_jobs "
                "WHERE id > :last_id ORDER BY id LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": _BATCH_SIZE},
        ).fetchall()
        if not rows:
            return
        changes = _scrubbed_rows(rows)
        if changes:
            bind.execute(
                sa.text(
                    "UPDATE dead_letter_jobs SET payload = :payload, "
                    "error_message = :error_message WHERE id = :id"
                ),
                changes,
            )
        last_id = rows[-1].id


def downgrade() -> None:
    """Irreversible: the scrubbed plaintext links are not recoverable."""
    return None
