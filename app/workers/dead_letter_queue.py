"""
Dead Letter Queue (DLQ) for failed background job processing.

This module provides:
- Storage for failed jobs with retry metadata
- Job deduplication to prevent duplicate processing
- Metrics for monitoring DLQ health
- Automatic retry with exponential backoff
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import random
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote, unquote

from sqlalchemy import (
    delete,
    func,
    select,
    update,
)

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

from app.models.dead_letter import DeadLetterJob, JobStatus

logger = get_logger(__name__)
_worker_dlq_tasks: set[asyncio.Task[Any]] = set()


def compute_job_hash(job_type: str, payload: dict[str, Any]) -> str:
    """Compute a unique hash for job deduplication."""
    content = json.dumps({"type": job_type, "payload": payload}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _unique_auth_payload_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate auth task payload field")
        result[key] = value
    return result


_AUTH_EMAIL_JOB_TYPE = "app.tasks.email.send_auth_email"


def _protected_auth_payload_bytes(
    job_type: str, job_hash: str, stored_payload: str
) -> str | None:
    """Validate in an isolated frame before returning only protected bytes."""
    try:
        from app.tasks.email import prepare_auth_email_payload

        if job_type != _AUTH_EMAIL_JOB_TYPE:
            return None
        payload = json.loads(
            stored_payload, object_pairs_hook=_unique_auth_payload_object
        )
        if not isinstance(payload, dict):
            return None
        protected, logical = prepare_auth_email_payload(payload)
        if compute_job_hash(job_type, logical) != job_hash:
            return None
        # Reject duplicate JSON fields above before preserving original bytes:
        # a shadowed field could otherwise retain a plaintext link on disk.
        return stored_payload if protected == payload else json.dumps(protected)
    except Exception:  # RZ-22-01-JUSTIFIED: opaque retained auth-row validation
        return None


def _protect_retained_auth_payload(job: DeadLetterJob) -> None:
    protected = _protected_auth_payload_bytes(job.job_type, job.job_hash, job.payload)
    if protected is None:
        from app.tasks.email import AuthEmailPayloadError

        # Raise after the parser/crypto frame returned, without raw JSON locals.
        raise AuthEmailPayloadError() from None
    if protected != job.payload:
        job.payload = protected


# Unprotectable retained auth bytes may hold a plaintext link, so they are replaced
# with a constant that matches no auth task shape. Identity and retry state stay.
_QUARANTINED_AUTH_PAYLOAD = json.dumps({"kind": "auth-email-quarantined-v1"})

# Same rule as the DLQ token-scrub migration: error text that echoes a plaintext
# ``#token=`` / ``?token=`` link is replaced, so no error field keeps the link.
# The separator and the ``=`` may also arrive percent-encoded or as HTML
# entities, and the parameter name may vary in case; each form is a live link.
_PLAINTEXT_TOKEN_LINK = re.compile(
    r"(?:[#?&]|%23|%3f|%26|&amp;|&#0*38;|&#x0*26;)token(?:=|%3d|&#0*61;|&#x0*3d;)"
    r"[^\s&\"'<>]+",
    re.IGNORECASE,
)


# The token parameter of a reset or verification link, plain or percent-encoded.
_LINK_TOKEN_VALUE = re.compile(r"[#?&]token=([^&#\s]+)", re.IGNORECASE)


class DeadLetterPlaintextLinkError(ValueError):
    """A retained job would store a reset or verification link in plaintext."""

    def __init__(self) -> None:
        super().__init__("Dead-letter payload carries a plaintext token link")


def _auth_link_tokens(job_type: str, stored_payload: str) -> tuple[str, ...]:
    """Return the token values carried by a stored auth payload's link.

    Only the error scrub uses these values, so a token that an error repeats
    outside a link is removed as well. Any unreadable payload yields no values.
    The payload itself is protected separately, and this never returns the link.
    """
    if job_type != _AUTH_EMAIL_JOB_TYPE:
        return ()
    try:
        from app.services.auth_service import _token_hmac_secret
        from app.tasks.email import _read_auth_email_link, send_auth_email

        payload = json.loads(stored_payload)
        bound = inspect.signature(send_auth_email).bind(
            *payload["args"], **payload["kwargs"]
        )
        link = bound.arguments["link"]
        if bound.arguments.get("encrypted_link", False) is True:
            link = _read_auth_email_link(link, _token_hmac_secret())[0]
    except Exception:  # RZ-22-01-JUSTIFIED: unreadable row yields no extra scrub values
        return ()
    if not isinstance(link, str):
        return ()
    return tuple(
        sorted(
            {unquote(match.group(1)) for match in _LINK_TOKEN_VALUE.finditer(link)}
            - {""}
        )
    )


def _scrub_error_text(error: str, tokens: tuple[str, ...] = ()) -> str:
    """Return the error text unless it echoes a token link or a known token."""
    if _PLAINTEXT_TOKEN_LINK.search(error):
        return _QUARANTINED_AUTH_PAYLOAD
    for token in tokens:
        if token in error or quote(token, safe="") in error:
            return _QUARANTINED_AUTH_PAYLOAD
    return error


def _reject_plaintext_link(stored_payload: str) -> None:
    """Refuse to persist a payload that still carries a plaintext token link.

    Auth payloads are sealed before this check, so it only fails for another
    job type that carries such a link, or for an auth payload that was not sealed.
    """
    if _PLAINTEXT_TOKEN_LINK.search(stored_payload):
        raise DeadLetterPlaintextLinkError()


class DeadLetterQueue:
    """Manager for the dead letter queue."""

    BASE_BACKOFF_SECONDS = 60  # 1 minute
    MAX_BACKOFF_SECONDS = 3600  # 1 hour

    _replay_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _is_replaying: ClassVar[bool] = False

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_failed_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        error_message: str,
        max_retries: int = 3,
    ) -> DeadLetterJob | None:
        """
        Add a failed job to the dead letter queue.

        Returns the created job, or None if a duplicate already exists.
        """
        if job_type == "app.tasks.email.send_auth_email":
            from app.tasks.email import prepare_auth_email_payload

            payload, logical_payload = prepare_auth_email_payload(payload)
            job_hash = compute_job_hash(job_type, logical_payload)
            del logical_payload
        else:
            job_hash = compute_job_hash(job_type, payload)

        # Calculate next retry time with exponential backoff
        next_retry = datetime.now(UTC) + timedelta(seconds=self.BASE_BACKOFF_SECONDS)

        # The stored form is the only form written below. Its error text is scrubbed
        # with the tokens that this payload carries.
        stored_payload = json.dumps(payload)
        tokens = _auth_link_tokens(job_type, stored_payload)
        # A non-auth payload that still carries a plaintext link is recorded as a
        # quarantined row: the failure stays on record, and it is never replayed.
        quarantine = job_type != _AUTH_EMAIL_JOB_TYPE and bool(
            _PLAINTEXT_TOKEN_LINK.search(stored_payload)
        )

        # Duplicate check: skip only while a retry for this payload is queued.
        statement = select(DeadLetterJob).where(DeadLetterJob.job_hash == job_hash)
        if job_type == "app.tasks.email.send_auth_email":
            # Repair only the current row state, not a stale identity-map copy.
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        existing = (await self.session.execute(statement)).scalar_one_or_none()
        if existing is not None and existing.status in (
            JobStatus.PENDING.value,
            JobStatus.RETRYING.value,
        ):
            if job_type == "app.tasks.email.send_auth_email":
                # Keep retry state and let the caller persist the payload repair.
                _protect_retained_auth_payload(existing)
            # The retained row keeps its own earlier error text; a link that an
            # earlier failure stored must not survive a later duplicate either.
            if existing.error_message is not None:
                existing.error_message = _scrub_error_text(
                    existing.error_message,
                    _auth_link_tokens(job_type, existing.payload),
                )
            logger.debug(
                "Duplicate job detected, skipping: type=%s, hash=%s",
                job_type,
                job_hash[:8],
            )
            return None

        # A new or reopened row persists this payload, so refuse a plaintext auth
        # link before any write. A duplicate above writes nothing and returns early.
        if quarantine:
            logger.warning("dlq_plaintext_link_quarantined: task=%s", job_type)
            row_payload = _QUARANTINED_AUTH_PAYLOAD
            row_status = JobStatus.FAILED.value
            row_retry_at = None
        else:
            _reject_plaintext_link(stored_payload)
            row_payload = stored_payload
            row_status = JobStatus.PENDING.value
            row_retry_at = next_retry
        if existing is not None:
            # job_hash is unique, so a finished row (completed or exhausted)
            # describes an earlier run; a new failure reopens it instead.
            job = existing
            job.status = row_status
            job.retry_count = 0
            job.max_retries = max_retries
            job.payload = row_payload
            job.error_message = _scrub_error_text(error_message, tokens)
            job.next_retry_at = row_retry_at
        else:
            job = DeadLetterJob(
                job_type=job_type,
                job_hash=job_hash,
                payload=row_payload,
                error_message=_scrub_error_text(error_message, tokens),
                status=row_status,
                max_retries=max_retries,
                next_retry_at=row_retry_at,
            )
            self.session.add(job)
        # TD-012 (audit 2026-03-04): commit removed — callers own the Unit of Work
        # boundary. Committing inside repository methods prevents batching multiple
        # operations atomically and violates the UoW pattern.
        # Callers MUST flush/commit after this method if persistence is required.
        await self.session.flush()

        logger.info(
            "Added job to DLQ: type=%s, hash=%s, next_retry=%s",
            job_type,
            job_hash[:8],
            next_retry.isoformat(),
        )

        return job

    async def get_jobs_ready_for_retry(self, limit: int = 10) -> list[DeadLetterJob]:
        """Get jobs that are ready to be retried."""
        now = datetime.now(UTC)

        result = await self.session.execute(
            select(DeadLetterJob)
            .where(
                DeadLetterJob.status.in_(
                    [JobStatus.PENDING.value, JobStatus.RETRYING.value]
                ),
                DeadLetterJob.next_retry_at <= now,
            )
            .order_by(DeadLetterJob.next_retry_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        return list(result.scalars().all())

    async def mark_job_retrying(self, job: DeadLetterJob) -> None:
        """Mark a job as currently being retried."""
        job.status = JobStatus.RETRYING.value
        job.retry_count = int(getattr(job, "retry_count", 0)) + 1
        job.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def mark_job_completed(self, job: DeadLetterJob) -> None:
        """Mark a job as successfully completed after retry."""
        job.status = JobStatus.COMPLETED.value
        job.updated_at = datetime.now(UTC)
        await self.session.flush()

        logger.info(
            "DLQ job completed: type=%s, hash=%s, retries=%d",
            job.job_type,
            job.job_hash[:8],
            job.retry_count,
        )

    async def get_queue_stats(self) -> dict[str, int]:
        """Get statistics about the dead letter queue."""
        result = await self.session.execute(
            select(
                DeadLetterJob.status,
                func.count(DeadLetterJob.id).label("count"),
            ).group_by(DeadLetterJob.status)
        )

        stats: dict[str, int] = {
            JobStatus.PENDING.value: 0,
            JobStatus.RETRYING.value: 0,
            JobStatus.FAILED.value: 0,
            JobStatus.COMPLETED.value: 0,
        }

        for row in result:
            stats[str(getattr(row, "status", ""))] = int(getattr(row, "count", 0) or 0)

        return stats

    async def cleanup_completed_jobs(self, older_than_days: int = 7) -> int:
        """Remove completed jobs older than the specified number of days."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

        result = await self.session.execute(
            delete(DeadLetterJob).where(
                DeadLetterJob.status == JobStatus.COMPLETED.value,
                DeadLetterJob.updated_at < cutoff,
            )
        )

        await self.session.flush()
        deleted = getattr(result, "rowcount", 0) or 0

        return deleted

    async def quarantine_auth_payload(self, job_hash: str) -> bool:
        """Replace an unprotectable retained auth payload, as a compare-and-set.

        The stored row is read again here and judged on those bytes. Only that
        exact payload is replaced (``WHERE payload = <observed bytes>``), so a
        row that another writer changed after it was read is never overwritten
        on a stale judgement. A row that is protectable now, or is not auth
        work, is left alone. Returns whether this call replaced the bytes.

        Only the stored bytes, and any error text that echoes a link, change.
        The row keeps its id, hash, status, retry budget and schedule, so every
        later replay still fails closed.
        """
        row = (
            await self.session.execute(
                select(
                    DeadLetterJob.job_type,
                    DeadLetterJob.job_hash,
                    DeadLetterJob.payload,
                    DeadLetterJob.error_message,
                ).where(DeadLetterJob.job_hash == job_hash)
            )
        ).one_or_none()
        if row is None or row.job_type != _AUTH_EMAIL_JOB_TYPE:
            return False
        if (
            _protected_auth_payload_bytes(row.job_type, row.job_hash, row.payload)
            is not None
        ):
            return False

        values: dict[str, str] = {"payload": _QUARANTINED_AUTH_PAYLOAD}
        if row.error_message is not None:
            scrubbed = _scrub_error_text(row.error_message)
            if scrubbed != row.error_message:
                values["error_message"] = scrubbed
        result = await self.session.execute(
            update(DeadLetterJob)
            .where(
                DeadLetterJob.job_hash == job_hash,
                DeadLetterJob.payload == row.payload,
            )
            .values(**values)
        )
        return bool(getattr(result, "rowcount", 0))

    async def auto_replay_jobs(
        self,
        handler: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        *,
        batch_size: int = 10,
        max_batches: int = 10,
        rate_limit_delay: float = 0.05,
        circuit_breaker: Any | None = None,
        base_backoff_seconds: int = 60,
        max_backoff_seconds: int = 3600,
        jitter: float = 0.5,
        force: bool = False,
    ) -> tuple[int, int]:
        """
        Automated recovery replay engine for DB-backed DeadLetterJob records.

        Features:
        - Thundering herd prevention (asyncio.Lock)
        - Circuit breaker status monitoring
        - Rate-limited batch processing
        - Exponential backoff with jitter on failures
        """
        # Import lazily: the auth task module imports this worker's broker.
        from app.tasks.email import AuthEmailPayloadError

        if DeadLetterQueue._replay_lock.locked() and not force:
            logger.info(
                "DB DLQ auto-replay already in progress; skipping thundering herd"
            )
            return (0, 0)

        async with DeadLetterQueue._replay_lock:
            DeadLetterQueue._is_replaying = True
            success_count = 0
            failed_count = 0

            try:
                for _ in range(max_batches):
                    if circuit_breaker and not force:
                        if (
                            getattr(
                                circuit_breaker.state,
                                "name",
                                str(circuit_breaker.state),
                            )
                            == "OPEN"
                        ):
                            logger.warning(
                                "Circuit breaker is OPEN; halting DB DLQ auto-replay"
                            )
                            break

                    jobs = await self.get_jobs_ready_for_retry(limit=batch_size)
                    if not jobs:
                        break

                    for job in jobs:
                        admission = None
                        if circuit_breaker:
                            admission = circuit_breaker.admit_request(force=force)
                            if not admission.allowed and not force:
                                break

                        try:
                            await self.mark_job_retrying(job)
                            try:
                                if job.job_type == "app.tasks.email.send_auth_email":
                                    try:
                                        _protect_retained_auth_payload(job)
                                    except AuthEmailPayloadError:
                                        # Persist the replacement before the failure
                                        # bookkeeping flushes in the same transaction.
                                        await self.quarantine_auth_payload(job.job_hash)
                                        raise
                                payload = json.loads(job.payload)
                                if handler is None:
                                    raise RuntimeError(
                                        "No DB DLQ replay handler is configured for "
                                        f"job type {job.job_type!r}"
                                    )
                                await handler(job.job_type, payload)
                                await self.mark_job_completed(job)
                                success_count += 1
                                if circuit_breaker:
                                    circuit_breaker.record_success(admission)
                            except Exception as exc:  # RZ-22-01-JUSTIFIED: DB DLQ worker job execution error must be handled during automated replay
                                failed_count += 1
                                if circuit_breaker:
                                    circuit_breaker.record_failure(admission)

                                # A handler error can echo a retained link; store and log
                                # only the scrubbed text.
                                error_msg = _scrub_error_text(
                                    str(exc),
                                    _auth_link_tokens(job.job_type, job.payload),
                                )
                                retry_count = int(getattr(job, "retry_count", 0))
                                max_retries = int(getattr(job, "max_retries", 3))

                                if retry_count >= max_retries:
                                    job.status = JobStatus.FAILED.value
                                    job.next_retry_at = None
                                    logger.error(
                                        "DB DLQ job %d permanently failed after %d retries: %s",
                                        job.id,
                                        retry_count,
                                        error_msg[:200],
                                    )
                                else:
                                    job.status = JobStatus.PENDING.value
                                    backoff = min(
                                        base_backoff_seconds * (2**retry_count)
                                        + random.uniform(0, jitter),  # noqa: S311 # nosec B311
                                        max_backoff_seconds,
                                    )
                                    job.next_retry_at = datetime.now(UTC) + timedelta(
                                        seconds=backoff
                                    )
                                    logger.warning(
                                        "DB DLQ job %d failed, scheduled retry #%d at %s",
                                        job.id,
                                        retry_count,
                                        job.next_retry_at.isoformat(),
                                    )

                                job.error_message = error_msg
                                job.updated_at = datetime.now(UTC)
                                await self.session.flush()

                            if rate_limit_delay > 0:
                                await asyncio.sleep(rate_limit_delay)
                        finally:
                            if circuit_breaker and admission is not None:
                                circuit_breaker.abandon_request(admission)
                    else:
                        # A normal loop completion means the whole batch was
                        # processed; circuit-breaker denial uses ``break`` and
                        # exits replay without flushing a partial batch.
                        await self.session.flush()
                        continue
                    break
            finally:
                DeadLetterQueue._is_replaying = False

            return (success_count, failed_count)
