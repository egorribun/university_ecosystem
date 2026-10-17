"""Initialize authorization only for the verified, disposable live stand.

Run last through ``python scripts/live_stand.py seed --demo``. The SQL admin
seed must have committed first. This is not a production provisioning command
and does not grant access to arbitrary users with a local admin role.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import grpc
from authzed.api.v1 import (
    CheckPermissionRequest,
    CheckPermissionResponse,
    Consistency,
    ObjectReference,
    PermissionsServiceStub,
    Relationship,
    RelationshipUpdate,
    SchemaServiceStub,
    SubjectReference,
    WriteRelationshipsRequest,
    WriteSchemaRequest,
)
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session, init_database
from app.models.enums import UserRole
from app.models.users import User
from scripts.seed_admin_data import ADMIN_EMAIL
from scripts.seed_target import ADMIN_SMOKE_PROJECT, require_owned_live_stand_target

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.zed"
RPC_TIMEOUT_SECONDS = 30


def _require_authorization_target() -> None:
    if require_owned_live_stand_target() == ADMIN_SMOKE_PROJECT:
        raise RuntimeError("authorization seed requires an owned live stand")
    # The SQL seed guard alone cannot attest the authorization service target.
    # Only the existing plaintext Compose service is supported by this command.
    if (
        settings.spicedb_endpoint != "spicedb:50051"
        or os.environ.get("SPICEDB_INSECURE", "").lower() != "true"
    ):
        raise RuntimeError(
            "authorization seed requires the spicedb service in the owned live stand"
        )
    if not settings.spicedb_preshared_key.strip():
        raise RuntimeError("authorization seed requires the configured SpiceDB key")


def _write_authorization(admin_id: str, schema: str) -> None:
    metadata = (("authorization", f"Bearer {settings.spicedb_preshared_key}"),)
    with grpc.insecure_channel(settings.spicedb_endpoint) as channel:
        schema_client = SchemaServiceStub(channel)
        permissions = PermissionsServiceStub(channel)
        schema_client.WriteSchema(
            WriteSchemaRequest(schema=schema),
            metadata=metadata,
            timeout=RPC_TIMEOUT_SECONDS,
        )
        resource = ObjectReference(object_type="semester", object_id="current")
        subject = SubjectReference(
            object=ObjectReference(object_type="user", object_id=admin_id)
        )
        written = permissions.WriteRelationships(
            WriteRelationshipsRequest(
                updates=[
                    RelationshipUpdate(
                        operation=RelationshipUpdate.OPERATION_TOUCH,
                        relationship=Relationship(
                            resource=resource, relation="admin", subject=subject
                        ),
                    )
                ]
            ),
            metadata=metadata,
            timeout=RPC_TIMEOUT_SECONDS,
        )
        checked = permissions.CheckPermission(
            CheckPermissionRequest(
                resource=resource,
                permission="admin",
                subject=subject,
                consistency=Consistency(at_least_as_fresh=written.written_at),
            ),
            metadata=metadata,
            timeout=RPC_TIMEOUT_SECONDS,
        )
        if (
            checked.permissionship
            != CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
        ):
            raise RuntimeError("SpiceDB did not confirm the seeded admin grant")


async def main() -> None:
    _require_authorization_target()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    if not schema.strip():
        raise RuntimeError("the canonical authorization schema is empty")
    init_database()
    async with async_session() as db:
        admin = await db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None or admin.role != UserRole.ADMIN or not admin.is_active:
            raise RuntimeError("an active seeded admin must exist before authorization")
        admin_id = str(admin.id)

    # The management SDK is synchronous; keep its channel lifetime off the loop.
    await asyncio.to_thread(_write_authorization, admin_id, schema)
    print("Owned live stand authorization initialized and admin grant verified.")


if __name__ == "__main__":
    asyncio.run(main())
