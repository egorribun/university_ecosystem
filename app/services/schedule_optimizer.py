import logging
from datetime import datetime

import httpx
from grpclib.client import Channel
from pydantic import BaseModel

from app.core.config import settings

# Attempt to import generated stubs. If they don't exist yet, we'll fall back gracefully
# or raise an informative error during development.
try:
    from gen.python.university_ecosystem.optimizer.v1.optimizer_grpc import (
        OptimizerServiceStub,
    )
    from gen.python.university_ecosystem.optimizer.v1.optimizer_pb2 import (
        BatchDetectConflictsRequest,
        DetectConflictsRequest,
        ScheduleItem,
    )

    HAS_STUBS = True
except ImportError:
    HAS_STUBS = False

logger = logging.getLogger(__name__)


class ScheduleItemInternal(BaseModel):
    id: int | None = None
    weekday: str
    start_time: datetime
    end_time: datetime
    parity: str
    room: str | None = None
    teacher: str | None = None


class ScheduleOptimizerService:
    """Service to interact with the Rust-based schedule optimizer."""

    def __init__(self, base_url: str | None = None, grpc_addr: str | None = None):
        self.base_url = base_url or getattr(
            settings, "RUST_OPTIMIZER_URL", "http://rust-optimizer:8080"
        )
        self.grpc_addr = grpc_addr or getattr(
            settings, "RUST_OPTIMIZER_GRPC_ADDR", "rust-optimizer:50051"
        )
        self._channel: Channel | None = None

    def _get_channel(self) -> Channel:
        """Lazily create gRPC channel on first use."""
        if self._channel is None:
            host, port = self.grpc_addr.split(":")
            self._channel = Channel(host, int(port))
        return self._channel

    async def _to_grpc_item(self, item: ScheduleItemInternal) -> "ScheduleItem":
        from google.protobuf.timestamp_pb2 import Timestamp

        ts_start = Timestamp()
        ts_start.FromDatetime(item.start_time)
        ts_end = Timestamp()
        ts_end.FromDatetime(item.end_time)

        return ScheduleItem(
            id=item.id,
            weekday=item.weekday,
            start_time=ts_start,
            end_time=ts_end,
            parity=item.parity,
            room=item.room or "",
            teacher=item.teacher or "",
        )

    def _from_grpc_item(self, item: "ScheduleItem") -> ScheduleItemInternal:
        return ScheduleItemInternal(
            id=item.id if item.HasField("id") else None,
            weekday=item.weekday,
            start_time=item.start_time.ToDatetime(),
            end_time=item.end_time.ToDatetime(),
            parity=item.parity,
            room=item.room,
            teacher=item.teacher,
        )

    async def detect_conflicts(
        self, target: ScheduleItemInternal, existing: list[ScheduleItemInternal]
    ) -> list[ScheduleItemInternal]:
        """Call the Rust service to detect conflicts primarily via gRPC."""
        if not HAS_STUBS:
            return await self._detect_conflicts_rest_fallback(target, existing)

        try:
            stub = OptimizerServiceStub(self._get_channel())
            target_grpc = await self._to_grpc_item(target)
            existing_grpc = [await self._to_grpc_item(item) for item in existing]

            request = DetectConflictsRequest(target=target_grpc, existing=existing_grpc)
            response = await stub.DetectConflicts(request)

            return [self._from_grpc_item(item) for item in response.conflicts]
        except Exception as e:
            logger.error(f"gRPC conflict detection failed, falling back: {e}")
            return await self._detect_conflicts_rest_fallback(target, existing)

    async def _detect_conflicts_rest_fallback(
        self, target: ScheduleItemInternal, existing: list[ScheduleItemInternal]
    ) -> list[ScheduleItemInternal]:
        """REST Fallback for backward compatibility."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                payload = {
                    "target": target.model_dump(mode="json"),
                    "existing": [item.model_dump(mode="json") for item in existing],
                }
                response = await client.post(
                    f"{self.base_url}/detect-conflicts", json=payload
                )
                response.raise_for_status()
                data = response.json()
                return [
                    ScheduleItemInternal(**item) for item in data.get("conflicts", [])
                ]
            except Exception as e:
                logger.error(f"REST fallback failed: {e}")
                return []

    async def batch_detect_conflicts(
        self, items: list[ScheduleItemInternal]
    ) -> list[tuple[ScheduleItemInternal, ScheduleItemInternal]]:
        """Perform high-performance gRPC batch detection."""
        if not HAS_STUBS:
            logger.warning("Batch detection skipped: gRPC stubs unavailable")
            return []

        try:
            stub = OptimizerServiceStub(self._get_channel())
            request = BatchDetectConflictsRequest(
                items=[await self._to_grpc_item(item) for item in items]
            )
            response = await stub.BatchDetectConflicts(request)

            return [
                (self._from_grpc_item(pair.item_a), self._from_grpc_item(pair.item_b))
                for pair in response.conflicts
            ]
        except Exception as e:
            logger.error(f"gRPC batch detection failed: {e}")
            return []
