import uuid
from datetime import UTC, datetime, time

import rust_ext
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)
_UNSET = object()


class ScheduleItemInternal(BaseModel):
    id: uuid.UUID | int | None = None
    weekday: int | str
    start_time: datetime | time
    end_time: datetime | time
    parity: str
    room: str | None = None
    teacher: str | None = None


class ScheduleOptimizerService:
    """Service to interact with the Rust-based schedule optimizer natively via PyO3."""

    def _to_rust_item(
        self,
        item: ScheduleItemInternal,
        *,
        rust_id_override: int | None | object = _UNSET,
    ) -> rust_ext.ScheduleItem:
        # Rust expects i32 for ID, but we use UUID.
        # For conflict detection, the ID is only used to map back.
        # We'll use a hash of the UUID if it's a UUID, otherwise the int.
        rust_id: int | None = None
        if isinstance(item.id, int):
            rust_id = item.id
        elif isinstance(item.id, uuid.UUID):
            if rust_id_override is _UNSET:
                # Keep the standalone conversion deterministic for callers
                # that only need a Rust value. Conflict paths use the
                # collision-free allocator below because UUIDv7 values share
                # their high bytes within the same timestamp window.
                rust_id = int.from_bytes(item.id.bytes[:4], "big") & 0x7FFFFFFF
            else:
                rust_id = (
                    rust_id_override if isinstance(rust_id_override, int) else None
                )

        # Convert time to datetime if needed (use 1970-01-01 to avoid OS/platform
        # overflow errors when calling .timestamp() on year 1)
        st = item.start_time
        if isinstance(st, time):
            st = datetime.combine(datetime(1970, 1, 1).date(), st, tzinfo=UTC)

        et = item.end_time
        if isinstance(et, time):
            et = datetime.combine(datetime(1970, 1, 1).date(), et, tzinfo=UTC)

        return rust_ext.ScheduleItem(
            weekday=str(item.weekday),
            start_time=int(st.timestamp()),
            end_time=int(et.timestamp()),
            parity=item.parity,
            id=rust_id,
        )

    def _to_rust_items_with_unique_ids(
        self, items: list[ScheduleItemInternal]
    ) -> tuple[list[rust_ext.ScheduleItem], dict[int, ScheduleItemInternal]]:
        """Convert a conflict batch with a collision-free per-call ID map.

        Rust exposes a signed 32-bit integer identifier while the domain uses
        UUIDs.  Deriving an integer from only the first four UUID bytes is not
        injective (UUIDv7 values generated in one timestamp window commonly
        collide), so conflict reconstruction must allocate surrogate IDs for
        UUID-backed items and retain the reverse map for this invocation.
        """

        used_ids = {item.id for item in items if isinstance(item.id, int)}
        next_surrogate = 2_147_483_647
        rust_id_map: dict[int, ScheduleItemInternal] = {}
        rust_items: list[rust_ext.ScheduleItem] = []

        for item in items:
            if isinstance(item.id, uuid.UUID):
                while next_surrogate in used_ids:
                    next_surrogate -= 1
                rust_id = next_surrogate
                used_ids.add(rust_id)
                next_surrogate -= 1
                rust_id_map[rust_id] = item
                rust_items.append(self._to_rust_item(item, rust_id_override=rust_id))
            else:
                rust_item = self._to_rust_item(item)
                rust_items.append(rust_item)
                if isinstance(item.id, int):
                    rust_id_map[item.id] = item

        return rust_items, rust_id_map

    def _from_rust_item(
        self,
        item: rust_ext.ScheduleItem,
        original_room: str | None = None,
        original_teacher: str | None = None,
    ) -> ScheduleItemInternal:
        return ScheduleItemInternal(
            id=item.id,
            weekday=item.weekday,
            start_time=datetime.fromtimestamp(item.start_time, tz=UTC),
            end_time=datetime.fromtimestamp(item.end_time, tz=UTC),
            parity=item.parity,
            room=original_room,
            teacher=original_teacher,
        )

    async def detect_conflicts(
        self, target: ScheduleItemInternal, existing: list[ScheduleItemInternal]
    ) -> list[ScheduleItemInternal]:
        """Call the native Rust extension to detect conflicts."""
        try:
            rust_items, rust_id_map = self._to_rust_items_with_unique_ids(
                [target, *existing]
            )
            target_rust = rust_items[0]
            existing_rust = rust_items[1:]

            conflicts_rust = rust_ext.detect_conflicts(target_rust, existing_rust)

            result = []
            for c_item in conflicts_rust:
                orig = rust_id_map.get(c_item.id) if c_item.id is not None else None
                room = orig.room if orig else None
                teacher = orig.teacher if orig else None
                orig_id = orig.id if orig else c_item.id
                reconstructed = self._from_rust_item(c_item, room, teacher)
                reconstructed.id = orig_id
                result.append(reconstructed)

            return result
        # HIGH-W19 + RZ-20-04: narrow to Rust/PyO3 error types — consistent
        # with batch_detect_conflicts and find_optimal_slot handlers.
        except (RuntimeError, ImportError, OSError) as e:
            # RZ-33-13: Re-raise instead of returning empty — an empty list is
            # indistinguishable from "no conflicts", which lets the caller create
            # a conflicting schedule entry.  Callers must handle the exception.
            logger.error("Native PyO3 conflict detection failed: %s", e)
            raise RuntimeError("Schedule conflict detection unavailable") from e

    async def batch_detect_conflicts(
        self, items: list[ScheduleItemInternal]
    ) -> list[tuple[ScheduleItemInternal, ScheduleItemInternal]]:
        """Perform high-performance native batch detection."""
        try:
            items_rust, rust_id_map = self._to_rust_items_with_unique_ids(items)
            conflicts_rust = rust_ext.batch_detect_conflicts(items_rust)

            result = []
            for a, b in conflicts_rust:
                orig_a = rust_id_map.get(a.id) if a.id is not None else None
                orig_b = rust_id_map.get(b.id) if b.id is not None else None

                rec_a = self._from_rust_item(
                    a,
                    orig_a.room if orig_a else None,
                    orig_a.teacher if orig_a else None,
                )
                if orig_a:
                    rec_a.id = orig_a.id

                rec_b = self._from_rust_item(
                    b,
                    orig_b.room if orig_b else None,
                    orig_b.teacher if orig_b else None,
                )
                if orig_b:
                    rec_b.id = orig_b.id

                result.append((rec_a, rec_b))
            return result
        except (RuntimeError, ImportError, OSError) as e:
            # RZ-33-13: Re-raise — empty list is indistinguishable from "no conflicts".
            logger.error(
                "Native PyO3 batch detection failed: %s", e
            )  # LOW-W19: lazy logging
            raise RuntimeError("Schedule batch conflict detection unavailable") from e

    async def find_optimal_slot(
        self,
        duration_minutes: int,
        existing: list[ScheduleItemInternal],
        preferred_weekdays: list[str] | None = None,
    ) -> ScheduleItemInternal | None:
        """Find an optimal schedule slot natively."""
        try:
            existing_rust = [self._to_rust_item(item) for item in existing]

            days = preferred_weekdays or [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ]
            # Rust API accepts either Vec<(String, Vec<u32>)> (new) or
            # Vec<String> (old).  Try the new signature first, fall back.
            available_blocks = [(day, list(range(8, 21))) for day in days]
            try:
                suggested_rust = rust_ext.find_optimal_slot(
                    duration_minutes,
                    existing_rust,
                    available_blocks,
                )
            except TypeError:
                suggested_rust = rust_ext.find_optimal_slot(
                    duration_minutes,
                    existing_rust,
                    days,
                )

            if suggested_rust:
                return self._from_rust_item(
                    suggested_rust, original_room="Auto", original_teacher="Auto"
                )
            return None
        except (RuntimeError, ImportError, OSError) as e:
            # RZ-20-04: Narrowed — Rust/PyO3 binding failures.
            logger.exception(
                "Native PyO3 find_optimal_slot failed: %s", e
            )  # LOW-W19: lazy logging
            raise
