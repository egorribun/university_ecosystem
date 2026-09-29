"""Ephemeral story schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import (
    model_validator,
)

from app.core.localization import translate
from app.schemas.common import BaseModel, OrmModel
from app.schemas.validators import SanitizedInput


class StoryCreate(BaseModel):
    title: str
    title_en: SanitizedInput = None
    short_text: str
    short_text_en: SanitizedInput = None
    cover_url: SanitizedInput = None
    cta_url: SanitizedInput = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_expiration(self) -> StoryCreate:
        published = self.published_at
        expires = self.expires_at
        if expires is not None and published is not None and expires <= published:
            raise ValueError(translate("validation.stories.expires_after_publish"))
        return self


class StoryUpdate(BaseModel):
    title: str | None = None
    title_en: SanitizedInput = None
    short_text: str | None = None
    short_text_en: SanitizedInput = None
    cover_url: SanitizedInput = None
    cta_url: SanitizedInput = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate_expiration(self) -> StoryUpdate:
        provided = self.model_fields_set
        if "published_at" in provided and "expires_at" in provided:
            if self.published_at is not None and self.expires_at is not None:
                if self.expires_at <= self.published_at:
                    raise ValueError(
                        translate("validation.stories.expires_after_publish")
                    )
        return self


class StoryOut(OrmModel):
    id: uuid.UUID
    title: str
    title_en: str | None = None
    short_text: str
    short_text_en: str | None = None
    cover_url: str | None = None
    cta_url: str | None = None
    published_at: datetime
    expires_at: datetime
    is_active: bool
    created_by: str | Any | None = None
    created_at: datetime

    cover_url_optimized: str | None = None
