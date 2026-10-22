from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from scripts import backup_db


@pytest.mark.asyncio
async def test_revision_change_during_dump_stops_before_s3_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql://backup_user@localhost/synthetic_source"
    metadata = iter(
        [
            ("synthetic_source", ("revision_before",)),
            ("synthetic_source", ("revision_after",)),
        ]
    )
    metadata_calls: list[str] = []
    s3_calls: list[backup_db.S3Settings] = []

    def read_metadata(url: str) -> tuple[str, tuple[str, ...]]:
        metadata_calls.append(url)
        return next(metadata)

    def create_synthetic_dump(url: str, archive_path: Any) -> None:
        assert url == database_url
        archive_path.write_bytes(b"synthetic PostgreSQL archive")

    @asynccontextmanager
    async def forbidden_s3_client(settings: backup_db.S3Settings):
        s3_calls.append(settings)
        pytest.fail("backup publication started after the source revision changed")
        yield None

    monkeypatch.setattr(backup_db, "source_database_metadata", read_metadata)
    monkeypatch.setattr(backup_db, "dump_database", create_synthetic_dump)
    monkeypatch.setattr(backup_db, "s3_client", forbidden_s3_client)
    settings = backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket="synthetic-backups",
        prefix="synthetic",
        region="test-region",
    )

    with pytest.raises(
        backup_db.BackupArtifactError,
        match="Source database migration revision changed during dump",
    ):
        await backup_db.backup_to_s3(database_url, settings)

    assert metadata_calls == [database_url, database_url]
    assert s3_calls == []
