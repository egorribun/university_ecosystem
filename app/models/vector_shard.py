import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class VectorChunk(Base, UUID7PrimaryKeyMixin):
    """
    Tier 1 PostgreSQL 17 pgvector model for sharded vector storage & transactional fallback.
    Stores 1536-dimensional embeddings with HNSW cosine distance indexing.
    """

    __tablename__ = "vector_chunks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    course_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True, index=True
    )
    document_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(default=0, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_vector_chunks_embedding",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_vector_chunks_tenant_doc", "tenant_id", "document_id"),
        Index("ix_vector_chunks_tenant_course", "tenant_id", "course_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<VectorChunk(id={self.id}, tenant_id={self.tenant_id}, "
            f"doc={self.document_id}, chunk={self.chunk_index})>"
        )
