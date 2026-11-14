"""Write event ownership and attendance relationships to SpiceDB.

``schema.zed`` grants ``event`` permissions through the ``creator`` and
``attendee`` relations, but application code previously never wrote them. This
module is the writer for those relations. Both are written best effort on the
backend request path after the domain commit:

- ``creator`` by the event service after ``create_event`` commits.
- ``attendee`` by the attendance service after register/unregister commits.
- ``group`` ``participant`` by the registration/create handlers and profile
  service after a ``group_id`` change commits (see ``sync_group_participant``).
  Group schedules are gated by ``group#view``, which includes ``participant``.

A SpiceDB failure is logged and never fails the request. The
event and group backfill scripts restore missing grants for current database
rows. They do not remove stale grants left by failed deletes or reordered
concurrent writes. The outbox worker intentionally has no SpiceDB access, so
these writes do not go through the outbox.

Authentication is carried by the shared channel (see ``app.core.spicedb``), so
no per-call metadata is attached here. Permission checks use SpiceDB's default
consistency, so a relation written just now can take a few seconds to be seen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Final
from uuid import UUID

import grpc.aio
from authzed.api.v1 import (
    ObjectReference,
    Relationship,
    RelationshipUpdate,
    SubjectReference,
    WriteRelationshipsRequest,
)
from authzed.api.v1.permission_service_pb2_grpc import PermissionsServiceStub

from app.core.logging import get_logger
from app.core.spicedb import acquire_shared_spicedb_channel

logger = get_logger(__name__)

EVENT_OBJECT_TYPE: Final = "event"
USER_OBJECT_TYPE: Final = "user"
CREATOR_RELATION: Final = "creator"
ATTENDEE_RELATION: Final = "attendee"
GROUP_OBJECT_TYPE: Final = "group"
GROUP_PARTICIPANT_RELATION: Final = "participant"

# Upper bound on one WriteRelationships round trip. Attendance writes happen on
# the request path, so the bound stays short.
WRITE_TIMEOUT_SECONDS: Final = 5.0

_OPERATIONS: Final[dict[str, RelationshipUpdate.Operation.ValueType]] = {
    "touch": RelationshipUpdate.OPERATION_TOUCH,
    "delete": RelationshipUpdate.OPERATION_DELETE,
}


class RelationshipWriteError(RuntimeError):
    """A SpiceDB relationship write was not confirmed."""


def build_event_relationship_update(
    *,
    operation: str,
    relation: str,
    event_id: UUID | int,
    user_id: UUID | int,
) -> RelationshipUpdate:
    """Return ``event:{event_id}#{relation}@user:{user_id}`` as an update.

    ``operation`` is ``"touch"`` (idempotent upsert) or ``"delete"``.
    """
    if operation not in _OPERATIONS:
        raise ValueError(f"unsupported relationship operation: {operation!r}")
    if relation not in (CREATOR_RELATION, ATTENDEE_RELATION):
        raise ValueError(f"unsupported event relation: {relation!r}")
    return _relationship_update(
        operation=operation,
        object_type=EVENT_OBJECT_TYPE,
        object_id=event_id,
        relation=relation,
        user_id=user_id,
    )


def build_group_participant_update(
    *,
    operation: str,
    group_id: UUID | int,
    user_id: UUID | int,
) -> RelationshipUpdate:
    """Return ``group:{group_id}#participant@user:{user_id}`` as an update.

    ``operation`` is ``"touch"`` (idempotent upsert) or ``"delete"``.
    """
    return _relationship_update(
        operation=operation,
        object_type=GROUP_OBJECT_TYPE,
        object_id=group_id,
        relation=GROUP_PARTICIPANT_RELATION,
        user_id=user_id,
    )


def _relationship_update(
    *,
    operation: str,
    object_type: str,
    object_id: UUID | int,
    relation: str,
    user_id: UUID | int,
) -> RelationshipUpdate:
    if operation not in _OPERATIONS:
        raise ValueError(f"unsupported relationship operation: {operation!r}")
    return RelationshipUpdate(
        operation=_OPERATIONS[operation],
        relationship=Relationship(
            resource=ObjectReference(object_type=object_type, object_id=str(object_id)),
            relation=relation,
            subject=SubjectReference(
                object=ObjectReference(
                    object_type=USER_OBJECT_TYPE, object_id=str(user_id)
                )
            ),
        ),
    )


class EventRelationshipWriter:
    """Writes event creator/attendee relations through an open async channel."""

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._channel = channel

    async def touch_creator(self, event_id: UUID | int, user_id: UUID | int) -> None:
        await self.write(
            [_update("touch", CREATOR_RELATION, event_id, user_id)],
        )

    async def delete_creator(self, event_id: UUID | int, user_id: UUID | int) -> None:
        await self.write([_update("delete", CREATOR_RELATION, event_id, user_id)])

    async def touch_attendee(self, event_id: UUID | int, user_id: UUID | int) -> None:
        await self.write([_update("touch", ATTENDEE_RELATION, event_id, user_id)])

    async def delete_attendee(self, event_id: UUID | int, user_id: UUID | int) -> None:
        await self.write([_update("delete", ATTENDEE_RELATION, event_id, user_id)])

    async def touch_group_participant(
        self, group_id: UUID | int, user_id: UUID | int
    ) -> None:
        await self.write(
            [
                build_group_participant_update(
                    operation="touch", group_id=group_id, user_id=user_id
                )
            ]
        )

    async def delete_group_participant(
        self, group_id: UUID | int, user_id: UUID | int
    ) -> None:
        await self.write(
            [
                build_group_participant_update(
                    operation="delete", group_id=group_id, user_id=user_id
                )
            ]
        )

    async def write(self, updates: Sequence[RelationshipUpdate]) -> None:
        """Send one WriteRelationships request; raise on any unconfirmed failure."""
        if not updates:
            return
        stub = PermissionsServiceStub(self._channel)
        request = WriteRelationshipsRequest(updates=list(updates))
        try:
            async with asyncio.timeout(WRITE_TIMEOUT_SECONDS):
                await stub.WriteRelationships(request)
        except (grpc.aio.AioRpcError, OSError, TimeoutError) as err:
            raise RelationshipWriteError(
                "SpiceDB relationship write was not confirmed"
            ) from err


def _update(
    operation: str, relation: str, event_id: UUID | int, user_id: UUID | int
) -> RelationshipUpdate:
    return build_event_relationship_update(
        operation=operation,
        relation=relation,
        event_id=event_id,
        user_id=user_id,
    )


async def sync_event_creator(event_id: UUID | int, user_id: UUID | int | None) -> None:
    """Best-effort ``event#creator`` TOUCH after the event commit.

    A missing creator is a no-op. A SpiceDB failure is logged and swallowed so
    that the committed event is never reported as failed; the backfill script
    reconciles missed relations.
    """
    if user_id is None:
        return
    try:
        writer = EventRelationshipWriter(await acquire_shared_spicedb_channel())
        await writer.touch_creator(event_id, user_id)
    except RelationshipWriteError as err:
        logger.warning(
            "event_creator_relationship_sync_failed",
            operation="touch",
            event_id=str(event_id),
            error=str(err),
        )


async def sync_event_attendee(
    event_id: UUID | int, user_id: UUID | int, *, attending: bool
) -> None:
    """Best-effort ``event#attendee`` sync after an attendance commit.

    There is no domain event for attendance, so a SpiceDB failure is logged and
    swallowed. The TOUCH-only backfill restores missing grants, not failed
    deletions.
    """
    operation = "touch" if attending else "delete"
    try:
        writer = EventRelationshipWriter(await acquire_shared_spicedb_channel())
        if attending:
            await writer.touch_attendee(event_id, user_id)
        else:
            await writer.delete_attendee(event_id, user_id)
    except RelationshipWriteError as err:
        logger.warning(
            "event_attendee_relationship_sync_failed",
            operation=operation,
            event_id=str(event_id),
            error=str(err),
        )


async def sync_group_participant(
    user_id: UUID | int,
    old_group_id: UUID | int | None,
    new_group_id: UUID | int | None,
) -> None:
    """Best-effort ``group#participant`` sync after a ``group_id`` change commits.

    The old membership is DELETEd and the new one TOUCHed in one request. An
    unchanged or entirely absent membership is a no-op. A SpiceDB failure is
    logged and swallowed. The TOUCH-only backfill restores missing grants, not failed
    deletions.
    """
    if old_group_id == new_group_id:
        return
    updates: list[RelationshipUpdate] = []
    if old_group_id is not None:
        updates.append(
            build_group_participant_update(
                operation="delete", group_id=old_group_id, user_id=user_id
            )
        )
    if new_group_id is not None:
        updates.append(
            build_group_participant_update(
                operation="touch", group_id=new_group_id, user_id=user_id
            )
        )
    try:
        writer = EventRelationshipWriter(await acquire_shared_spicedb_channel())
        await writer.write(updates)
    except RelationshipWriteError as err:
        logger.warning(
            "group_participant_relationship_sync_failed",
            user_id=str(user_id),
            old_group_id=str(old_group_id),
            new_group_id=str(new_group_id),
            error=str(err),
        )


__all__ = [
    "ATTENDEE_RELATION",
    "CREATOR_RELATION",
    "GROUP_PARTICIPANT_RELATION",
    "EventRelationshipWriter",
    "RelationshipWriteError",
    "build_event_relationship_update",
    "build_group_participant_update",
    "sync_event_attendee",
    "sync_event_creator",
    "sync_group_participant",
]
