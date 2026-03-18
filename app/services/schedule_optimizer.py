import logging
import uuid
from datetime import UTC, datetime, time
from typing import Any

import rust_ext
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Kept for backward compatibility with DI containers passing URLs
        pass

    async def close(self) -> None:
        """No-op for backward compatibility."""
        pass

    def _to_rust_item(self, item: ScheduleItemInternal) -> rust_ext.ScheduleItem:
        # Rust expects i32 for ID, but we use UUID.
        # For conflict detection, the ID is only used to map back.
        # We'll use a hash of the UUID if it's a UUID, otherwise the int.
        rust_id: int | None = None
        if isinstance(item.id, int):
            rust_id = item.id
        elif isinstance(item.id, uuid.UUID):
            # Deterministic hash to stay within i32 range
            rust_id = hash(item.id) & 0x7FFFFFFF

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
        except Exception as e:
            logger.error(f"Native PyO3 conflict detection failed: {e}")
            return []

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
        except Exception as e:
            logger.error(f"Native PyO3 batch detection failed: {e}")
            return []

    async def find_optimal_slot(
        self,
        duration_minutes: int,
        existing: list[ScheduleItemInternal],
        preferred_weekdays: list[str] | None = None,
    ) -> ScheduleItemInternal | None:
        """Find an optimal schedule slot natively."""
        try:
            existing_rust = [self._to_rust_item(item) for item in existing]

            days = preferred_weekdays or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            # Domain-driven schedule available blocks (hours) instead of hardcoded in Rust
            available_blocks = [(day, [9, 11, 13, 15]) for day in days]

            suggested_rust = rust_ext.find_optimal_slot(
                duration_minutes=duration_minutes,
                existing_schedule=existing_rust,
                available_blocks=available_blocks,
            )

            if suggested_rust:
                return self._from_rust_item(
                    suggested_rust, original_room="Auto", original_teacher="Auto"
                )
            return None
        except Exception as e:
            logger.exception(f"Native PyO3 find_optimal_slot failed: {e}")
            raise e
