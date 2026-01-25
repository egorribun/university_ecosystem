import logging
from datetime import datetime

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class ScheduleItemInternal(BaseModel):
    id: int | None = None
    weekday: str
    start_time: datetime
    end_time: datetime
    parity: str


class ScheduleOptimizerService:
    """Service to interact with the Rust-based schedule optimizer."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or getattr(
            settings, "RUST_OPTIMIZER_URL", "http://rust-optimizer:8080"
        )

    async def detect_conflicts(
        self, target: ScheduleItemInternal, existing: list[ScheduleItemInternal]
    ) -> list[ScheduleItemInternal]:
        """Call the Rust service to detect conflicts."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                # Ensure all times are ISO formatted for Rust
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
                # Fallback to empty list or raise?
                # For high reliability, we might want to throw if optimization
                # is mandatory
                return []
