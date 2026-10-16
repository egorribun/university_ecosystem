"""Strict adapter for a root-owned, bounded loopback PostgreSQL test server."""

from __future__ import annotations

import re
from ipaddress import ip_address

import sqlalchemy as sa

_TEST_DATABASE_RE = re.compile(r"test_[0-9a-f]{20}\Z", re.ASCII)


class _LoopbackMigrationPostgres:
    """Validate the operator's test URL without taking ownership of its server."""

    def __init__(self, connection_url: str) -> None:
        parsed = sa.engine.make_url(connection_url)
        try:
            loopback = ip_address(parsed.host or "").is_loopback
        except ValueError:
            loopback = False
        if (
            parsed.drivername != "postgresql+asyncpg"
            or not loopback
            or parsed.username != "test"
            or parsed.database is None
            or len(parsed.database) != 25
            or not parsed.database.startswith("test_")
            or any(
                character not in "0123456789abcdef" for character in parsed.database[5:]
            )
            or not parsed.password
            or parsed.port is None
            or not 1 <= parsed.port <= 65535
            or parsed.port == 5432
            or bool(parsed.query)
        ):
            raise ValueError(
                "MIGRATION_ROUNDTRIP_DATABASE_URL must target the owned loopback "
                "PG17 test database."
            )
        if parsed.database is None:
            raise ValueError("Operator database name is required.")
        self._url = parsed
        self._database = parsed.database

    def get_connection_url(self, *, driver: str) -> str:
        return self._render_connection_url(driver=driver, database=self._database)

    def get_maintenance_connection_url(self, *, driver: str) -> str:
        return self._render_connection_url(driver=driver, database="postgres")

    def get_test_connection_url(self, database: str, *, driver: str) -> str:
        if _TEST_DATABASE_RE.fullmatch(database) is None:
            raise ValueError(
                "Generated test database name is outside the allowed format."
            )
        return self._render_connection_url(driver=driver, database=database)

    def _render_connection_url(self, *, driver: str, database: str) -> str:
        if driver not in {"asyncpg", "psycopg"}:
            raise ValueError("Unsupported migration test database driver.")
        return self._url.set(
            drivername=f"postgresql+{driver}", database=database
        ).render_as_string(hide_password=False)
