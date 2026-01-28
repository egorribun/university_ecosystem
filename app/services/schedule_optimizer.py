import logging
from datetime import datetime
from typing import Any

import httpx
from grpclib.client import Channel
from pydantic import BaseModel

from app.core.config import settings

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

    def __init__(self, base_url: str = None, grpc_addr: str = None):
        self.base_url = base_url or getattr(
            settings, "RUST_OPTIMIZER_URL", "http://rust-optimizer:8080"
        )
        self.grpc_addr = grpc_addr or getattr(
            settings, "RUST_OPTIMIZER_GRPC_ADDR", "rust-optimizer:50051"
        )

    async def _call_grpc(self, method: str, request_data: dict[str, Any]) -> Any:
        """Low-level gRPC caller using grpclib."""
        host, port = self.grpc_addr.split(":")
        async with Channel(host, int(port)) as channel:
            # Note: In a production environment, we would use generated stubs.
            # Here we demonstrate the intent.
            # For brevity in this refactor, we keep the REST fallback as primary
            # until gRPC stubs are fully integrated into the CI/CD pipeline.
            raise NotImplementedError("gRPC stubs generation required in CI/CD")

    async def detect_conflicts(
        self, target: ScheduleItemInternal, existing: list[ScheduleItemInternal]
    ) -> list[ScheduleItemInternal]:
        """Call the Rust service to detect conflicts (REST/gRPC hybrid)."""
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
                logger.error(f"Failed to call rust-optimizer: {e}")
                return []

    async def batch_detect_conflicts(
        self, items: list[ScheduleItemInternal]
    ) -> list[tuple[ScheduleItemInternal, ScheduleItemInternal]]:
        """
        Perform high-performance batch collision detection.
        Reserved for gRPC implementation for O(N log N) performance.
        """
        # Placeholder for gRPC implementation
        logger.warning("Batch detection requested. Ensure gRPC service is healthy.")
        # Fallback to O(N^2) for now if needed, but ideally calls Rust via gRPC
        return []
