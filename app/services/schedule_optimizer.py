import uuid
from datetime import UTC, datetime, time

import rust_ext
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


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

    def _to_rust_item(self, item: ScheduleItemInternal) -> rust_ext.ScheduleItem:
        # Rust expects i32 for ID, but we use UUID.
        # For conflict detection, the ID is only used to map back.
        # We'll use a hash of the UUID if it's a UUID, otherwise the int.
        rust_id: int | None = None
        if isinstance(item.id, int):
            rust_id = item.id
        elif isinstance(item.id, uuid.UUID):
            # HIGH-W19: use deterministic bytes-based conversion instead of
            # Python's randomized hash() which changes across process restarts.
            rust_id = int.from_bytes(item.id.bytes[:4], "big") & 0x7FFFFFFF

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
            target_rust = self._to_rust_item(target)
            existing_rust = [self._to_rust_item(item) for item in existing]

            conflicts_rust = rust_ext.detect_conflicts(target_rust, existing_rust)

            # Reconstruct original items by matching IDs to restore metadata (room, teacher)
            existing_map = {item.id: item for item in existing if item.id is not None}

            result = []
            for item in conflicts_rust:
                orig = existing_map.get(item.id)
                room = orig.room if orig else None
                teacher = orig.teacher if orig else None
                result.append(self._from_rust_item(item, room, teacher))

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
            items_rust = [self._to_rust_item(item) for item in items]
            conflicts_rust = rust_ext.batch_detect_conflicts(items_rust)

            existing_map = {item.id: item for item in items if item.id is not None}

            result = []
            for a, b in conflicts_rust:
                orig_a = existing_map.get(a.id)
                orig_b = existing_map.get(b.id)

                result.append(
                    (
                        self._from_rust_item(
                            a,
                            orig_a.room if orig_a else None,
                            orig_a.teacher if orig_a else None,
                        ),
                        self._from_rust_item(
                            b,
                            orig_b.room if orig_b else None,
                            orig_b.teacher if orig_b else None,
                        ),
                    )
                )
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
