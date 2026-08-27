"""Regression coverage for fail-closed Alembic revision metadata parsing."""

from pathlib import Path

import pytest

from scripts.quality.read_alembic_revision import (
    RevisionMetadataError,
    read_revision_metadata,
)


def _write_migration(tmp_path: Path, source: str) -> Path:
    migration = tmp_path / "migration.py"
    migration.write_text(source, encoding="utf-8")
    return migration


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            'revision: str = "annotated"\ndown_revision: str | None = "parent"\n',
            ("annotated", "parent"),
        ),
        (
            'revision = "plain"\ndown_revision = None\n',
            ("plain", "base"),
        ),
    ],
)
def test_reads_literal_plain_and_annotated_metadata(
    tmp_path: Path,
    source: str,
    expected: tuple[str, str],
) -> None:
    assert read_revision_metadata(_write_migration(tmp_path, source)) == expected


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("down_revision = None\n", "revision must be assigned exactly once"),
        ('revision = "only"\n', "down_revision must be assigned exactly once"),
        (
            'revision = "first"\nrevision: str = "second"\ndown_revision = None\n',
            "revision must be assigned exactly once",
        ),
        (
            "revision = make_revision()\ndown_revision = None\n",
            "revision must be a string literal",
        ),
        (
            "revision = 123\ndown_revision = None\n",
            "revision must be a string literal",
        ),
        (
            'revision = "child"\ndown_revision = ("left", "right")\n',
            "down_revision must be a string literal or None",
        ),
        (
            'revision = alias = "child"\ndown_revision = None\n',
            "revision must use a single-name assignment",
        ),
        (
            'if enabled:\n    revision = "conditional"\ndown_revision = None\n',
            "revision must be a top-level assignment",
        ),
        (
            'revision = ""\ndown_revision = None\n',
            "revision must not be empty",
        ),
    ],
)
def test_rejects_missing_dynamic_non_string_or_ambiguous_metadata(
    tmp_path: Path,
    source: str,
    message: str,
) -> None:
    with pytest.raises(RevisionMetadataError, match=message):
        read_revision_metadata(_write_migration(tmp_path, source))


def test_rejects_invalid_python(tmp_path: Path) -> None:
    migration = _write_migration(tmp_path, 'revision = "broken"\nif\n')

    with pytest.raises(RevisionMetadataError, match="invalid Python syntax"):
        read_revision_metadata(migration)


def test_ci_uses_the_fail_closed_revision_metadata_parser() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert (
        'uv run python scripts/quality/read_alembic_revision.py "$migration"'
        in workflow
    )
    assert 're.search(r"^revision' not in workflow
