"""
Database configuration settings.

Extracted from main config.py for better organization.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection configuration."""

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/university",
        description="Async PostgreSQL connection URL",
    )

    database_pool_size: int | None = Field(
        default=5,
        description="Connection pool size",
    )

    database_max_overflow: int | None = Field(
        default=10,
        description="Max overflow connections beyond pool_size",
    )

    database_pool_timeout: float | None = Field(
        default=30.0,
        description="Seconds to wait for a connection from pool",
    )

    database_pool_recycle: int | None = Field(
        default=3600,
        description="Seconds before connection is recycled",
    )

    database_echo: bool = Field(
        default=False,
        description="Echo SQL statements to stdout",
    )

    database_read_url: str | None = Field(
        default=None,
        description="Read replica connection URL (optional)",
    )

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    @property
    def has_read_replica(self) -> bool:
        """Check if read replica is configured."""
        return bool(self.database_read_url)


__all__ = ["DatabaseSettings"]
