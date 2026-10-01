"""Student grade schemas."""

from __future__ import annotations

import uuid

from pydantic import Field

from app.schemas.common import BaseModel, OrmModel

# Scores are stored as floats.  The statistics layer treats anything above 5 as a
# 100-point scale, so 100 is the hard upper bound of both scales.
MAX_GRADE_SCORE = 100.0


class GradeCreate(BaseModel):
    student_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=100)
    score: float = Field(ge=0, le=MAX_GRADE_SCORE)
    assessment_type: str = Field(default="exam", min_length=1, max_length=50)


class GradeUpdate(BaseModel):
    score: float = Field(ge=0, le=MAX_GRADE_SCORE)
    reason: str | None = Field(default=None, max_length=500)


class GradeOut(OrmModel):
    id: uuid.UUID
    student_id: uuid.UUID
    subject: str
    score: float
    assessment_type: str
    assigned_by: uuid.UUID | None = None
