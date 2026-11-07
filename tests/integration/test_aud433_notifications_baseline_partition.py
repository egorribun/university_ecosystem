"""AUD433 candidate: exercise notifications partitions after a fresh MVP baseline.

This is a PostgreSQL regression candidate, not evidence that it has run. It is
bound to the exact canonical baseline and the existing owned-PostgreSQL proof
helpers. It never creates notification partitions itself.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run the owned PostgreSQL proof",
    ),
]

BASELINE_REVISION = "202611020000"
BASELINE_FILENAME = f"{BASELINE_REVISION}_mvp_baseline.py"
SOURCE_SHA256 = {
    "alembic/versions/202611020000_mvp_baseline.py": (
        "d92820ac1cfb705206c8f287c3059c55563a3707ebc0e3fb3e77af2132e3c41a"
    ),
    "tests/fixtures/owned_baseline_postgres.py": (
        "8f099d2ac946feaa06ce6692b9b9b034487602afe3f8460c5e3598a4722fb84b"
    ),
    "tests/integration/test_mvp_baseline_schema_equivalence.py": (
        "a5d7e357f7b20c41b120093365b3dc93b47692b169a470b41f41f10b63a2af79"
    ),
}


def _repository_root() -> Path:
    """Locate the checkout from either this private candidate or tests/."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").is_file() and (
            parent / "alembic" / "versions" / BASELINE_FILENAME
        ).is_file():
            return parent
    raise AssertionError("AUD433 repository root or canonical baseline not found")


PROJECT_ROOT = _repository_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _assert_source_bindings() -> None:
    for relative_path, expected in SOURCE_SHA256.items():
        source = PROJECT_ROOT / relative_path
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        assert actual == expected, (
            f"AUD433 source binding changed for {relative_path}: {actual}"
        )


def _notification_children(connection: sa.Connection) -> dict[str, str]:
    rows = connection.execute(
        sa.text(
            "SELECT child.relname, pg_catalog.pg_get_expr(child.relpartbound, child.oid) "
            "FROM pg_catalog.pg_inherits AS inheritance "
            "JOIN pg_catalog.pg_class AS parent "
            "ON parent.oid = inheritance.inhparent "
            "JOIN pg_catalog.pg_class AS child "
            "ON child.oid = inheritance.inhrelid "
            "WHERE parent.oid = 'public.notifications'::regclass "
            "ORDER BY child.relname"
        )
    ).all()
    return {str(name): str(bound) for name, bound in rows}


def _notification_delivery_foreign_keys(
    connection: sa.Connection,
) -> tuple[tuple[object, ...], ...]:
    rows = connection.execute(
        sa.text(
            "SELECT referencing.relname, "
            "constraint_row.conname, constraint_row.confrelid::regclass::text, "
            "constraint_row.convalidated, "
            "pg_catalog.pg_get_constraintdef(constraint_row.oid, true), "
            "parent_constraint.conname, "
            "constraint_row.confrelid = 'public.notifications'::regclass, "
            "constraint_row.conrelid = 'public.notification_deliveries'::regclass, "
            "constraint_row.conislocal, constraint_row.coninhcount "
            "FROM pg_catalog.pg_constraint AS constraint_row "
            "JOIN pg_catalog.pg_class AS referencing "
            "ON referencing.oid = constraint_row.conrelid "
            "LEFT JOIN pg_catalog.pg_constraint AS parent_constraint "
            "ON parent_constraint.oid = constraint_row.conparentid "
            "WHERE constraint_row.contype = 'f' "
            "AND constraint_row.conrelid IN (SELECT relid FROM "
            "pg_catalog.pg_partition_tree('public.notification_deliveries')) "
            "AND constraint_row.confrelid IN (SELECT relid FROM "
            "pg_catalog.pg_partition_tree('public.notifications')) "
            "ORDER BY 1, 2"
        )
    ).all()
    return tuple(tuple(row) for row in rows)


def _expected_notification_children(suffixes: tuple[str, ...]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for suffix in suffixes:
        name = f"notifications_{suffix}"
        if suffix == "default":
            expected[name] = "DEFAULT"
            continue
        year_text, month_text = suffix.split("_")
        year, month = int(year_text), int(month_text)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        expected[name] = (
            "FOR VALUES FROM ('"
            f"{year:04d}-{month:02d}-01 00:00:00+00') TO ('"
            f"{next_year:04d}-{next_month:02d}-01 00:00:00+00')"
        )
    return expected


def test_aud433_fresh_baseline_notifications_are_partitioned_and_writable() -> None:
    """The canonical fresh upgrade installs and uses its own notification children."""
    _assert_source_bindings()

    from tests.integration import test_mvp_baseline_schema_equivalence as proof

    assert proof.PROJECT_ROOT.resolve() == PROJECT_ROOT
    assert proof.BASELINE_REVISION == BASELINE_REVISION
    revisions = sorted(
        path.name for path in (PROJECT_ROOT / "alembic" / "versions").glob("*.py")
    )
    assert revisions == [BASELINE_FILENAME], (
        "AUD433 proof must exercise the canonical baseline as the only revision"
    )

    with proof.owned.owned_postgres_server() as server:
        database_url = proof._owned_url(server, "psycopg")
        proof._assert_owned_url_is_authoritative(PROJECT_ROOT, database_url)
        upgrade = proof._alembic(PROJECT_ROOT, database_url, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr[-4000:]

        engine = sa.create_engine(
            sa.engine.make_url(database_url),
            poolclass=sa.pool.NullPool,
            connect_args={"connect_timeout": 5},
            hide_parameters=True,
        )
        try:
            tenant_id = uuid4()
            user_id = uuid4()
            notification_id = uuid4()
            with engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
                version = connection.scalar(
                    sa.text("SELECT version_num FROM public.alembic_version")
                )
                assert version == BASELINE_REVISION

                root_kind, partition_key = connection.execute(
                    sa.text(
                        "SELECT relkind, pg_catalog.pg_get_partkeydef(oid) "
                        "FROM pg_catalog.pg_class "
                        "WHERE oid = 'public.notifications'::regclass"
                    )
                ).one()
                assert root_kind == "p"
                assert partition_key == "RANGE (created_at)"

                children = _notification_children(connection)
                expected_children = _expected_notification_children(
                    proof._PARTITION_SUFFIXES
                )
                assert children == expected_children

                current_suffix, created_at = connection.execute(
                    sa.text(
                        "SELECT to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', "
                        "'YYYY_MM'), CURRENT_TIMESTAMP"
                    )
                ).one()
                current_child = f"notifications_{current_suffix}"
                assert current_child in children
                assert not children[current_child].startswith("DEFAULT")

                connection.execute(
                    sa.text(
                        "INSERT INTO public.tenants (id, name, slug) "
                        "VALUES (:id, 'AUD433 partition proof', :slug)"
                    ),
                    {"id": tenant_id, "slug": f"aud433-{tenant_id.hex}"},
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO public.users (id, email, hashed_password, tenant_id) "
                        "VALUES (:id, :email, 'aud433-proof-only', :tenant_id)"
                    ),
                    {
                        "id": user_id,
                        "email": f"aud433-{user_id.hex}@example.invalid",
                        "tenant_id": tenant_id,
                    },
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO public.notifications "
                        "(id, user_id, title, read, created_at, tenant_id) "
                        "VALUES (:id, :user_id, 'AUD433 baseline proof', false, "
                        ":created_at, :tenant_id)"
                    ),
                    {
                        "id": notification_id,
                        "user_id": user_id,
                        "created_at": created_at,
                        "tenant_id": tenant_id,
                    },
                )
                routed_child = connection.scalar(
                    sa.text(
                        "SELECT child.relname FROM pg_catalog.pg_class AS child "
                        "WHERE child.oid = (SELECT tableoid FROM public.notifications "
                        "WHERE id = :id AND created_at = :created_at)"
                    ),
                    {"id": notification_id, "created_at": created_at},
                )
                assert routed_child == current_child, (
                    "notification insert did not route to its current-month range child"
                )

            # Negative control: remove every child created by the canonical baseline
            # inside a savepoint. The harness itself creates no partition; rollback
            # restores the exact just-upgraded schema after proving the insert fails.
            with engine.connect() as connection:
                with connection.begin():
                    original_children = _notification_children(connection)
                    original_foreign_keys = _notification_delivery_foreign_keys(
                        connection
                    )
                    parent_foreign_keys = tuple(
                        row
                        for row in original_foreign_keys
                        if row[1] == "fk_notification_deliveries_notification"
                        and row[7] is True
                    )
                    assert len(parent_foreign_keys) == 1
                    parent_foreign_key = parent_foreign_keys[0]
                    assert parent_foreign_key[3] is True
                    definition = str(parent_foreign_key[4]).casefold()
                    assert "foreign key (notification_id, notification_created_at)" in (
                        definition
                    )
                    assert "references notifications(id, created_at)" in definition
                    assert "on delete cascade" in definition
                    assert parent_foreign_key[5] is None
                    assert parent_foreign_key[6] is True
                    assert parent_foreign_key[8] is True
                    assert parent_foreign_key[9] == 0
                    copies = tuple(
                        row for row in original_foreign_keys if row[7] is False
                    )
                    expected_delivery_children = {
                        f"notification_deliveries_{suffix}"
                        for suffix in proof._PARTITION_SUFFIXES
                    }
                    assert {row[0] for row in copies} == expected_delivery_children
                    assert len(copies) == len(proof._PARTITION_SUFFIXES)
                    assert all(
                        row[3] is True
                        and row[5] == "fk_notification_deliveries_notification"
                        and row[6] is True
                        and row[8] is False
                        and row[9] > 0
                        for row in copies
                    )

                    counterfactual = connection.begin_nested()
                    try:
                        # PostgreSQL's FK from notification_deliveries keeps each
                        # notifications partition dependency alive. Drop only that
                        # known parent constraint; this propagates to its partition
                        # copies and is rolled back with the counterfactual savepoint.
                        connection.exec_driver_sql(
                            "ALTER TABLE public.notification_deliveries "
                            "DROP CONSTRAINT fk_notification_deliveries_notification"
                        )
                        assert _notification_delivery_foreign_keys(connection) == ()

                        for child in original_children:
                            assert re.fullmatch(
                                r"notifications_(?:[0-9]{4}_[0-9]{2}|default)", child
                            ), f"unexpected notification child name: {child}"
                            connection.exec_driver_sql(f'DROP TABLE public."{child}"')
                        assert _notification_children(connection) == {}

                        rejected_id = uuid4()
                        with pytest.raises(sa.exc.DBAPIError) as rejected:
                            with connection.begin_nested():
                                connection.execute(
                                    sa.text(
                                        "INSERT INTO public.notifications "
                                        "(id, user_id, title, read, created_at, tenant_id) "
                                        "VALUES (:id, :user_id, 'AUD433 no-partition "
                                        "control', false, :created_at, :tenant_id)"
                                    ),
                                    {
                                        "id": rejected_id,
                                        "user_id": user_id,
                                        "created_at": created_at,
                                        "tenant_id": tenant_id,
                                    },
                                )
                        original = rejected.value.orig
                        sqlstate = getattr(original, "sqlstate", None) or getattr(
                            original, "pgcode", None
                        )
                        primary = getattr(
                            getattr(original, "diag", None), "message_primary", ""
                        )
                        assert sqlstate == "23514"
                        assert "no partition of relation" in primary.casefold()
                        assert "notifications" in primary.casefold()
                    finally:
                        if counterfactual.is_active:
                            counterfactual.rollback()
                    restored_children = _notification_children(connection)
                    assert restored_children == original_children
                    assert restored_children == expected_children
                    assert (
                        _notification_delivery_foreign_keys(connection)
                        == original_foreign_keys
                    )
                    restored_route = connection.scalar(
                        sa.text(
                            "SELECT child.relname FROM pg_catalog.pg_class AS child "
                            "WHERE child.oid = (SELECT tableoid FROM "
                            "public.notifications WHERE id = :id AND created_at = "
                            ":created_at)"
                        ),
                        {"id": notification_id, "created_at": created_at},
                    )
                    assert restored_route == current_child
        finally:
            engine.dispose()
