"""Study-group schemas."""

from __future__ import annotations

import uuid

from app.schemas.common import BaseModel, OrmModel


class GroupCreate(BaseModel):
    name: str
    course: int | None = None
    faculty: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    course: int | None = None
    faculty: str | None = None


class GroupOut(OrmModel):
    id: uuid.UUID
    name: str
    course: int | None = None
    faculty: str | None = None
