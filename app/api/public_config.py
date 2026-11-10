"""Expose the validated server campus timezone to public clients."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.openapi_responses import RATE_LIMITED
from app.core.config import settings


class PublicCampusConfig(BaseModel):
    """The intentionally narrow, non-secret public campus configuration."""

    model_config = ConfigDict(extra="forbid")

    campus_timezone: str


router = APIRouter(tags=["public"])


@router.get(
    "/campus/config",
    response_model=PublicCampusConfig,
    summary="Get the campus timezone",
    responses=RATE_LIMITED,
)
async def get_campus_config() -> PublicCampusConfig:
    """Return the single validated server timezone used by campus features."""
    return PublicCampusConfig(campus_timezone=settings.campus_timezone)
