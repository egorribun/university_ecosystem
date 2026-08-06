from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import struct
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

import asyncpg
from opentelemetry import trace
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

from app.core.config import settings
from app.core.events import _EVENT_REGISTRY, DomainEvent, EventMetadata
from app.core.logging import get_logger
from app.core.nats_broker import NatsTaskBroker
from app.core.nats_broker import broker as global_nats_broker

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

# ── Prometheus Metrics for CDC Outbox Observability ───────────────────────────


def _get_or_create_metric(
    cls: Any, name: str, documentation: str, **kwargs: Any
) -> Any:
    if cls is None:
        return None
    if (
        REGISTRY
        and hasattr(REGISTRY, "_names_to_collectors")
        and name in REGISTRY._names_to_collectors
    ):
        return REGISTRY._names_to_collectors[name]
    try:
        return cls(name, documentation, **kwargs)
    except ValueError:
        if (
            REGISTRY
            and hasattr(REGISTRY, "_names_to_collectors")
            and name in REGISTRY._names_to_collectors
        ):
            return REGISTRY._names_to_collectors[name]
        raise


OUTBOX_CDC_EVENTS_DISPATCHED = _get_or_create_metric(
    Counter,
    "outbox_cdc_events_dispatched_total",
    "Total CDC outbox events dispatched to NATS JetStream",
    labelnames=["event_type", "status"],  # status: success | failed
)

OUTBOX_CDC_DISPATCH_DURATION = _get_or_create_metric(
    Histogram,
    "outbox_cdc_dispatch_duration_seconds",
    "End-to-end CDC dispatch latency from WAL parse to NATS PubAck",
    labelnames=["event_type"],
    buckets=(0.001, 0.002, 0.005, 0.010, 0.025, 0.050, 0.100, 0.500, 1.0),
)

CDC_WAL_REPLICATION_LAG_BYTES = _get_or_create_metric(
    Gauge,
    "cdc_wal_replication_lag_bytes",
    "PostgreSQL CDC WAL replication lag in bytes",
    labelnames=["slot_name"],
)

OUTBOX_CDC_REPLICATION_LAG_BYTES = _get_or_create_metric(
    Gauge,
    "pg_cdc_replication_lag_bytes",
    "PostgreSQL CDC replication LSN lag in bytes",
    labelnames=["slot_name"],
)

OUTBOX_CDC_REPLICATION_LAG_SECONDS = _get_or_create_metric(
    Gauge,
    "pg_cdc_replication_lag_seconds",
    "PostgreSQL CDC replication lag in seconds",
    labelnames=["slot_name"],
)

NATS_JETSTREAM_CONSUMER_LAG = _get_or_create_metric(
    Gauge,
    "nats_jetstream_consumer_lag",
    "NATS JetStream consumer unacknowledged message lag",
    labelnames=["stream", "consumer"],
)

JETSTREAM_CONSUMER_LAG = _get_or_create_metric(
    Gauge,
    "jetstream_consumer_lag_messages",
    "NATS JetStream consumer lag in messages",
    labelnames=["stream", "consumer"],
)

NATS_JETSTREAM_ACKS_TOTAL = _get_or_create_metric(
    Counter,
    "nats_jetstream_acks_total",
    "Total NATS JetStream message ACKs",
    labelnames=["stream", "consumer"],
)

JETSTREAM_MESSAGES_ACKED = _get_or_create_metric(
    Counter,
    "jetstream_messages_acked_total",
    "Total NATS JetStream messages ACKed",
    labelnames=["stream", "consumer"],
)

NATS_JETSTREAM_NAKS_TOTAL = _get_or_create_metric(
    Counter,
    "nats_jetstream_naks_total",
    "Total NATS JetStream message NAKs",
    labelnames=["stream", "consumer"],
)

JETSTREAM_MESSAGES_NACKED = _get_or_create_metric(
    Counter,
    "jetstream_messages_nacked_total",
    "Total NATS JetStream messages NACKed",
    labelnames=["stream", "consumer"],
)


# ── LSN Conversion Utilities ──────────────────────────────────────────────────


def lsn_to_int(lsn_str: str) -> int:
    """Convert a PostgreSQL LSN string ('X/Y') to a 64-bit integer."""
    if not lsn_str or not isinstance(lsn_str, str):
        return 0
    try:
        if "/" in lsn_str:
            parts = lsn_str.split("/")
            if len(parts) != 2:
                return 0
            return (int(parts[0], 16) << 32) + int(parts[1], 16)
        return int(lsn_str, 16)
    except (
        ValueError,
        TypeError,
        AttributeError,
        IndexError,
    ):  # RZ-20-04: graceful handling of invalid LSN strings
        return 0


def int_to_lsn(lsn_int: int) -> str:
    """Convert a 64-bit integer to a PostgreSQL LSN string ('X/Y')."""
    high = lsn_int >> 32
    low = lsn_int & 0xFFFFFFFF
    return f"{high:X}/{low:X}"


def format_standby_status_update(lsn: int, reply_requested: bool = False) -> bytes:
    """Format a PostgreSQL Standby Status Update binary payload for WAL replication.

    Byte layout (34 bytes):
    - Byte 0: 'r' (0x72) - Standby status update message identifier
    - Bytes 1..9: uint64 wal_write_lsn
    - Bytes 9..17: uint64 wal_flush_lsn (advanced after NATS PubAck)
    - Bytes 17..25: uint64 wal_apply_lsn
    - Bytes 25..33: int64 client_clock (microseconds since 2000-01-01 00:00:00 UTC)
    - Byte 33: uint8 reply_requested (1 = reply immediately, 0 = no reply)
    """
    pg_epoch_offset = 946684800  # Seconds between Unix epoch and 2000-01-01 UTC
    now_us = int((time.time() - pg_epoch_offset) * 1_000_000)
    if now_us < 0:
        now_us = 0
    return b"r" + struct.pack(
        ">QQQQB", lsn, lsn, lsn, now_us, 1 if reply_requested else 0
    )


# ── pgoutput Binary Decoder Data Structures ───────────────────────────────────


@dataclass
class ColumnSchema:
    name: str
    type_id: int
    flags: int = 0


@dataclass
class RelationSchema:
    relation_id: int
    namespace: str
    relation_name: str
    columns: list[ColumnSchema] = field(default_factory=list)


@dataclass
class CDCInsertRecord:
    relation_id: int
    relation_name: str
    data: dict[str, Any]
    lsn: int
    commit_time: datetime | None = None


@dataclass
class KeepaliveMessage:
    wal_end_lsn: int
    server_clock: int
    reply_requested: bool


# ── PgOutputDecoder Implementation ───────────────────────────────────────────


class PgOutputDecoder:
    """Decoder for PostgreSQL pgoutput logical replication binary stream.

    Parses XLogData ('w') and Keepalive ('k') envelope messages, relation ('R')
    metadata messages, and tuple insert ('I') messages according to the pgoutput
    protocol specification.
    """

    def __init__(self) -> None:
        self.relations: dict[int, RelationSchema] = {}

    def decode(
        self, data: bytes, default_lsn: int = 0
    ) -> CDCInsertRecord | KeepaliveMessage | None:
        if not data:
            return None

        try:
            msg_type = data[0:1]

            # 1. Parse XLogData envelope ('w')
            if msg_type == b"w":
                if len(data) < 25:
                    logger.warning(
                        "Truncated XLogData WAL envelope (len=%d < 25)", len(data)
                    )
                    return None
                data_start_lsn = struct.unpack_from(">Q", data, 1)[0]
                wal_payload = data[25:]
                return self._decode_pgoutput_payload(
                    wal_payload, lsn=data_start_lsn or default_lsn
                )

            # 2. Parse Primary Keepalive envelope ('k')
            if msg_type == b"k":
                if len(data) < 18:
                    logger.warning(
                        "Truncated Keepalive WAL envelope (len=%d < 18)", len(data)
                    )
                    return None
                wal_end_lsn = struct.unpack_from(">Q", data, 1)[0]
                server_clock = struct.unpack_from(">q", data, 9)[0]
                reply_requested = data[17] == 1
                return KeepaliveMessage(
                    wal_end_lsn=wal_end_lsn,
                    server_clock=server_clock,
                    reply_requested=reply_requested,
                )

            # Direct pgoutput payload without envelope
            return self._decode_pgoutput_payload(data, lsn=default_lsn)
        except (
            struct.error,
            IndexError,
            ValueError,
        ):  # RZ-20-04: graceful handling of corrupted binary frames
            return None

    def _decode_pgoutput_payload(
        self, payload: bytes, lsn: int
    ) -> CDCInsertRecord | None:
        if not payload:
            return None

        try:
            cmd = payload[0:1]
            offset = 1

            # Relation metadata ('R')
            if cmd == b"R":
                if len(payload) < 5:
                    logger.warning(
                        "Truncated relation metadata header (len=%d < 5)", len(payload)
                    )
                    return None
                relation_id = struct.unpack_from(">I", payload, offset)[0]
                offset += 4

                null_idx = payload.find(b"\x00", offset)
                if null_idx == -1:
                    return None
                namespace = payload[offset:null_idx].decode("utf-8", errors="replace")
                offset = null_idx + 1

                null_idx = payload.find(b"\x00", offset)
                if null_idx == -1:
                    return None
                relation_name = payload[offset:null_idx].decode(
                    "utf-8", errors="replace"
                )
                offset = null_idx + 1

                if offset + 3 > len(payload):
                    logger.warning("Truncated relation metadata columns header")
                    return None
                offset += 1  # replica identity
                num_columns = struct.unpack_from(">H", payload, offset)[0]
                offset += 2

                cols: list[ColumnSchema] = []
                for _ in range(num_columns):
                    if offset >= len(payload):
                        break
                    flags = payload[offset]
                    offset += 1

                    null_idx = payload.find(b"\x00", offset)
                    if null_idx == -1:
                        break
                    col_name = payload[offset:null_idx].decode(
                        "utf-8", errors="replace"
                    )
                    offset = null_idx + 1

                    if offset + 8 > len(payload):
                        break
                    type_id = struct.unpack_from(">I", payload, offset)[0]
                    offset += 4
                    offset += 4  # type modifier

                    cols.append(
                        ColumnSchema(name=col_name, type_id=type_id, flags=flags)
                    )

                self.relations[relation_id] = RelationSchema(
                    relation_id=relation_id,
                    namespace=namespace,
                    relation_name=relation_name,
                    columns=cols,
                )
                return None

            # Insert tuple ('I')
            if cmd == b"I":
                if len(payload) < 8:
                    logger.warning(
                        "Truncated tuple insert header (len=%d < 8)", len(payload)
                    )
                    return None
                relation_id = struct.unpack_from(">I", payload, offset)[0]
                offset += 4

                tuple_byte = payload[offset : offset + 1]
                offset += 1
                if tuple_byte != b"N":
                    return None

                if offset + 2 > len(payload):
                    return None
                num_cols = struct.unpack_from(">H", payload, offset)[0]
                offset += 2

                schema = self.relations.get(relation_id)
                row_data: dict[str, Any] = {}

                for i in range(num_cols):
                    col_name = (
                        schema.columns[i].name
                        if schema and i < len(schema.columns)
                        else f"col_{i}"
                    )
                    if offset >= len(payload):
                        return None
                    kind = payload[offset : offset + 1]
                    offset += 1

                    if kind in (b"n", b"u"):
                        row_data[col_name] = None
                    elif kind == b"t":
                        if offset + 4 > len(payload):
                            return None
                        val_len = struct.unpack_from(">I", payload, offset)[0]
                        offset += 4
                        if offset + val_len > len(payload):
                            return None
                        val_bytes = payload[offset : offset + val_len]
                        offset += val_len
                        val_str = val_bytes.decode("utf-8", errors="replace")

                        if col_name in ("payload", "metadata_", "trace_context"):
                            try:
                                row_data[col_name] = json.loads(val_str)
                            except (json.JSONDecodeError, TypeError):
                                row_data[col_name] = val_str
                        elif col_name in ("error_count", "version", "sequence_number"):
                            with contextlib.suppress(ValueError):
                                row_data[col_name] = int(val_str)
                            if col_name not in row_data:
                                row_data[col_name] = val_str
                        else:
                            row_data[col_name] = val_str
                    else:
                        return None

                rel_name = schema.relation_name if schema else ""
                return CDCInsertRecord(
                    relation_id=relation_id,
                    relation_name=rel_name,
                    data=row_data,
                    lsn=lsn,
                )

            return None
        except (
            struct.error,
            IndexError,
            ValueError,
            TypeError,
        ) as exc:  # RZ-20-04: graceful handling of corrupted binary frames
            logger.error("Failed to decode pgoutput payload: %s", exc, exc_info=True)
            return None


# ── CdcOutboxWorker Implementation ───────────────────────────────────────────


class CdcOutboxWorker:
    """Zero-Latency CDC Outbox Worker using PostgreSQL Logical Replication (pgoutput).

    Consumes WAL binary changes directly from PostgreSQL WAL logs without polling
    stored_events or using SELECT FOR UPDATE SKIP LOCKED. Reconstructs DomainEvents
    and publishes directly to NATS JetStream stream OUTBOX_EVENTS.
    """

    PUBLICATION_NAME = "outbox_pub"
    SLOT_NAME = "outbox_cdc_slot"
    STREAM_NAME = "OUTBOX_EVENTS"

    def __init__(
        self,
        dsn: str | None = None,
        nats_broker: NatsTaskBroker | None = None,
        slot_name: str = SLOT_NAME,
        publication_name: str = PUBLICATION_NAME,
    ) -> None:
        self.dsn = dsn or str(settings.database_url)
        self.nats_broker = nats_broker or global_nats_broker
        self.slot_name = slot_name
        self.publication_name = publication_name
        self._decoder = PgOutputDecoder()
        self._is_running = False
        self._last_acknowledged_lsn = 0

    def _normalize_dsn(self) -> str:
        parsed = urlparse(self.dsn)
        normalised_scheme = parsed.scheme.replace("+asyncpg", "")
        return urlunparse(parsed._replace(scheme=normalised_scheme))

    async def provision_replication_resources(
        self, conn: asyncpg.Connection | None = None
    ) -> None:
        """Provision publication and logical replication slot in PostgreSQL."""
        normalised_dsn = self._normalize_dsn()
        close_conn = False
        if conn is None:
            conn = await asyncpg.connect(normalised_dsn)
            close_conn = True

        try:
            # 1. Provision Publication for stored_events table
            pub_exists = await conn.fetchval(
                "SELECT 1 FROM pg_publication WHERE pubname = $1",
                self.publication_name,
            )
            if not pub_exists:
                # Sanitize publication name identifier to ensure safe DDL execution
                safe_pub_name = "".join(
                    c for c in self.publication_name if c.isalnum() or c == "_"
                )
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                await conn.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    f"CREATE PUBLICATION {safe_pub_name} FOR TABLE stored_events;"  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                )
                logger.info("Provisioned replication publication '%s'", safe_pub_name)

            # 2. Provision Replication Slot using pgoutput plugin
            slot_exists = await conn.fetchval(
                "SELECT 1 FROM pg_replication_slots WHERE slot_name = $1",
                self.slot_name,
            )
            if not slot_exists:
                await conn.fetchval(
                    "SELECT pg_create_logical_replication_slot($1, 'pgoutput')",
                    self.slot_name,
                )
                logger.info(
                    "Provisioned logical replication slot '%s' with pgoutput",
                    self.slot_name,
                )
        finally:
            if close_conn and conn is not None:
                await conn.close()

    async def dispatch_insert_record(
        self, record: CDCInsertRecord
    ) -> DomainEvent | None:
        """Reconstruct DomainEvent from CDC record and publish to NATS JetStream.

        Achieves sub-5ms end-to-end dispatch latency.
        """
        _t0 = time.perf_counter()
        data = record.data
        event_type = str(data.get("event_type") or "")
        stored_event_id = str(data.get("id") or uuid.uuid4())

        if not event_type:
            logger.warning("CDC record missing event_type: %s", data)
            return None

        event_cls = _EVENT_REGISTRY.get(event_type)
        if event_cls is None:
            logger.warning(
                "CdcOutboxWorker: unknown event_type %r in stored event %s — skipping",
                event_type,
                stored_event_id,
            )
            return None

        raw_payload = data.get("payload") or {}
        if isinstance(raw_payload, str):
            try:
                raw_payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                raw_payload = {}

        metadata_ = data.get("metadata_") or {}
        if isinstance(metadata_, str):
            try:
                metadata_ = json.loads(metadata_)
            except json.JSONDecodeError:
                metadata_ = {}

        known_fields = {f.name for f in dataclasses.fields(event_cls)}
        safe_payload = {k: v for k, v in raw_payload.items() if k in known_fields}

        try:
            event = event_cls(**safe_payload)
            if metadata_:
                if "event_id" in metadata_:
                    event.event_id = str(metadata_["event_id"])
                user_id_raw = metadata_.get("user_id")
                user_id_uuid: uuid.UUID | None = None
                if isinstance(user_id_raw, uuid.UUID):
                    user_id_uuid = user_id_raw
                elif isinstance(user_id_raw, str):
                    with contextlib.suppress(ValueError):
                        user_id_uuid = uuid.UUID(user_id_raw)
                event.metadata = EventMetadata(
                    correlation_id=metadata_.get("correlation_id"),
                    user_id=user_id_uuid,
                )

            with tracer.start_as_current_span("cdc_outbox.dispatch_event") as span:
                span.set_attribute("cdc_outbox.event_type", event_type)
                span.set_attribute("cdc_outbox.stored_event_id", stored_event_id)

                subject = f"outbox.events.{event_type}"
                event_payload = {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "stored_event_id": stored_event_id,
                    "payload": raw_payload,
                    "metadata": {
                        "correlation_id": event.metadata.correlation_id,
                        "user_id": str(event.metadata.user_id)
                        if event.metadata.user_id
                        else None,
                    },
                    "occurred_at": event.occurred_at.isoformat()
                    if hasattr(event, "occurred_at") and event.occurred_at
                    else None,
                }

                await self.nats_broker.publish(
                    subject=subject,
                    payload=event_payload,
                    headers={"Nats-Msg-Id": stored_event_id},
                    msg_id=stored_event_id,
                )

                duration = time.perf_counter() - _t0
                OUTBOX_CDC_DISPATCH_DURATION.labels(event_type=event_type).observe(
                    duration
                )
                OUTBOX_CDC_EVENTS_DISPATCHED.labels(
                    event_type=event_type, status="success"
                ).inc()

                logger.debug(
                    "CDC Outbox: dispatched event %s (type: %s) in %.3fms",
                    stored_event_id,
                    event_type,
                    duration * 1000,
                )
                return event

        except (
            Exception
        ) as exc:  # RZ-22-01-JUSTIFIED: handler-nak — log and increment failed count
            OUTBOX_CDC_EVENTS_DISPATCHED.labels(
                event_type=event_type, status="failed"
            ).inc()
            logger.error(
                "Failed to dispatch CDC event %s: %s",
                stored_event_id,
                exc,
                exc_info=True,
            )
            return None

    def send_status_update(self, lsn: int, reply_requested: bool = False) -> bytes:
        """Advance replication slot acknowledged LSN position."""
        if lsn > self._last_acknowledged_lsn:
            self._last_acknowledged_lsn = lsn
        return format_standby_status_update(lsn, reply_requested)

    async def process_wal_message(
        self, raw_bytes: bytes, lsn: int = 0, conn: asyncpg.Connection | None = None
    ) -> list[DomainEvent]:
        """Decode WAL payload, dispatch matching domain events, and advance LSN."""
        try:
            decoded = self._decoder.decode(raw_bytes, default_lsn=lsn)
        except (struct.error, IndexError, ValueError) as exc:
            logger.error(
                "CdcOutboxWorker: malformed WAL payload decoding failed: %s",
                exc,
                exc_info=True,
            )
            return []

        dispatched_events: list[DomainEvent] = []
        status_bytes: bytes | None = None

        if isinstance(decoded, CDCInsertRecord):
            is_stored_events = (
                not decoded.relation_name
                or decoded.relation_name == "stored_events"
                or "stored_events" in decoded.relation_name
            )
            if is_stored_events:
                evt = await self.dispatch_insert_record(decoded)
                if evt is not None:
                    dispatched_events.append(evt)
                    if decoded.lsn > 0:
                        status_bytes = self.send_status_update(decoded.lsn)
            elif decoded.lsn > 0:
                status_bytes = self.send_status_update(decoded.lsn)

        elif isinstance(decoded, KeepaliveMessage):
            if decoded.wal_end_lsn > 0:
                lag_bytes = max(0, decoded.wal_end_lsn - self._last_acknowledged_lsn)
                OUTBOX_CDC_REPLICATION_LAG_BYTES.labels(slot_name=self.slot_name).set(
                    lag_bytes
                )
                if CDC_WAL_REPLICATION_LAG_BYTES is not None:
                    CDC_WAL_REPLICATION_LAG_BYTES.labels(slot_name=self.slot_name).set(
                        lag_bytes
                    )
                if decoded.server_clock > 0:
                    server_time_sec = 946684800 + (decoded.server_clock / 1_000_000.0)
                    lag_seconds = max(0.0, time.time() - server_time_sec)
                    OUTBOX_CDC_REPLICATION_LAG_SECONDS.labels(
                        slot_name=self.slot_name
                    ).set(lag_seconds)
                status_bytes = self.send_status_update(
                    decoded.wal_end_lsn, reply_requested=decoded.reply_requested
                )

        if status_bytes and conn is not None:
            with contextlib.suppress(
                OSError, ConnectionError, asyncpg.PostgresError
            ):  # RZ-20-04: replication standby status update transmission
                await conn.put_copy_data(status_bytes)

        return dispatched_events

    async def run_forever(self) -> None:
        """Run CDC Outbox worker loop over asyncpg logical replication protocol."""
        self._is_running = True
        logger.info("CdcOutboxWorker starting (Zero-Latency CDC Mode)")

        if not self.nats_broker.is_connected:
            with contextlib.suppress(
                Exception
            ):  # RZ-22-01-JUSTIFIED: handler-nak — connect attempt
                await self.nats_broker.connect()

        # Step 1: Provision publication & replication slot
        try:
            await self.provision_replication_resources()
        except (
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
            asyncpg.InternalClientError,
            OSError,
            ConnectionError,
        ) as e:  # RZ-20-04: narrowed — postgres replication resources setup
            logger.warning(
                "CdcOutboxWorker: logical replication provisioning failed (%s). Falling back to OutboxWorker.",
                e,
            )
            await self._run_fallback_worker()
            return

        # Step 2: Establish replication streaming loop
        normalised_dsn = self._normalize_dsn()
        while self._is_running:
            try:
                conn = await asyncpg.connect(normalised_dsn, replication="database")
                try:
                    logger.info(
                        "CdcOutboxWorker connected to WAL logical replication slot '%s'",
                        self.slot_name,
                    )
                    # Use asyncpg copy_out to receive CopyData replication stream
                    start_stmt = (
                        f"START_REPLICATION SLOT {self.slot_name} LOGICAL 0/0 "
                        f"(proto_version '1', publication_names '{self.publication_name}')"
                    )

                    async def _wal_stream_writer(
                        data: bytes, repl_conn: asyncpg.Connection = conn
                    ) -> None:
                        if not self._is_running:
                            return
                        await self.process_wal_message(data, conn=repl_conn)

                    await conn._copy_out(start_stmt, _wal_stream_writer, timeout=None)
                finally:
                    await conn.close()
            except (
                asyncpg.PostgresError,
                asyncpg.InterfaceError,
                asyncpg.InternalClientError,
                OSError,
                ConnectionError,
            ) as exc:  # RZ-20-04: narrowed — replication connection loss
                if not self._is_running:
                    break  # type: ignore[unreachable]
                logger.warning(
                    "CdcOutboxWorker replication connection lost, retrying in 5s: %s",
                    exc,
                )
                await asyncio.sleep(5)

    async def _run_fallback_worker(self) -> None:
        from app.workers.outbox import OutboxWorker

        logger.info("CdcOutboxWorker: launching fallback OutboxWorker")
        fallback = OutboxWorker()
        await fallback.run_forever()

    async def stop(self) -> None:
        self._is_running = False
        logger.info("CdcOutboxWorker stopped")
