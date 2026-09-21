"""Shared Pydantic bases for the generated API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import (
    ConfigDict,
    Field,
)

from app.schemas.base import SecureBaseModel


class BaseModel(SecureBaseModel):
    pass


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    created_at: datetime | None = Field(default=None)

    @classmethod
    def from_orm(cls, obj: Any) -> OrmModel:
        return cls.model_validate(obj)
