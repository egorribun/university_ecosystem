"""Compatibility coverage for the historical UserRole case migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

from app.models.enums import UserRole
from app.schemas.schemas import UserPublicOut

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "57bdf5bf9375_resolve_role_case_mismatch_and_drop_.py"
)


def _load_role_migration():
    spec = importlib.util.spec_from_file_location("role_case_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("legacy_role", "expected_role"),
    [
        ("STUDENT", UserRole.STUDENT),
        ("TEACHER", UserRole.TEACHER),
        ("ADMIN", UserRole.ADMIN),
        ("SUPERUSER", UserRole.SUPERUSER),
    ],
)
def test_legacy_role_payload_round_trips_through_case_migration(
    legacy_role: str, expected_role: UserRole
) -> None:
    """Old uppercase rows migrate and remain readable by the current schema."""

    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (role VARCHAR NOT NULL)"))
            connection.execute(
                text("INSERT INTO users (role) VALUES (:role)"),
                {"role": legacy_role},
            )

            migration = _load_role_migration()
            operations = Operations(MigrationContext.configure(connection))
            original_op = migration.op
            migration.op = operations
            try:
                migration.upgrade()
            finally:
                migration.op = original_op

            migrated_role = connection.execute(
                text("SELECT role FROM users")
            ).scalar_one()
    finally:
        engine.dispose()

    payload = {
        "id": uuid4(),
        "full_name": "Legacy User",
        "role": migrated_role,
        "group_id": None,
        "is_active": True,
    }
    current = UserPublicOut.model_validate(payload)
    serialized = current.model_dump(mode="json")
    round_tripped = UserPublicOut.model_validate(serialized)

    assert migrated_role == expected_role.value
    assert round_tripped.role is expected_role
