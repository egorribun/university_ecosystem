from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class CwvEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pathname: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    device_class: Literal["mobile", "desktop"]
    renewal_envelope: Annotated[
        str | None, StringConstraints(min_length=32, max_length=4096)
    ] = None


class CwvEnvelopeResponse(BaseModel):
    envelope: Annotated[str, StringConstraints(min_length=32, max_length=4096)]
    expires_at: datetime


class CwvObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    envelope: Annotated[str, StringConstraints(min_length=32, max_length=4096)]
    metric: Literal["LCP", "INP", "CLS"]
    value: float = Field(ge=0, le=60_000)


class CwvObservationAccepted(BaseModel):
    metric_id: str
    accepted: Literal[True] = True
