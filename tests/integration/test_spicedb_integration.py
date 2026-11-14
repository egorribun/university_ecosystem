"""Real SpiceDB ReBAC contract tests against an in-memory disposable cell."""

from __future__ import annotations

import os

import grpc
import pytest
from authzed.api.v1 import (
    core_pb2,
    permission_service_pb2,
    permission_service_pb2_grpc,
    schema_service_pb2,
    schema_service_pb2_grpc,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("USE_TESTCONTAINERS_SPICEDB") != "1",
        reason="Set USE_TESTCONTAINERS_SPICEDB=1 to run the SpiceDB cell",
    ),
]

_SCHEMA = """
definition user {}

definition document {
    relation reader: user
    permission view = reader
}
"""


def _metadata(token: str) -> tuple[tuple[str, str], ...]:
    return (("authorization", f"Bearer {token}"),)


def _object(object_type: str, object_id: str) -> core_pb2.ObjectReference:
    return core_pb2.ObjectReference(object_type=object_type, object_id=object_id)


def _check_request(
    user_id: str,
    *,
    freshness: core_pb2.ZedToken | None = None,
) -> permission_service_pb2.CheckPermissionRequest:
    request = permission_service_pb2.CheckPermissionRequest(
        resource=_object("document", "doc-1"),
        permission="view",
        subject=core_pb2.SubjectReference(object=_object("user", user_id)),
    )
    if freshness is not None:
        request.consistency.at_least_as_fresh.CopyFrom(freshness)
    return request


def test_spicedb_schema_relationship_check_and_revoke(
    spicedb_container: dict[str, str],
) -> None:
    token = spicedb_container["token"]
    channel = grpc.insecure_channel(spicedb_container["endpoint"])
    try:
        schema = schema_service_pb2_grpc.SchemaServiceStub(channel)
        permissions = permission_service_pb2_grpc.PermissionsServiceStub(channel)
        metadata = _metadata(token)

        schema.WriteSchema(
            schema_service_pb2.WriteSchemaRequest(schema=_SCHEMA),
            metadata=metadata,
        )
        write_response = permissions.WriteRelationships(
            permission_service_pb2.WriteRelationshipsRequest(
                updates=[
                    core_pb2.RelationshipUpdate(
                        operation=core_pb2.RelationshipUpdate.OPERATION_TOUCH,
                        relationship=core_pb2.Relationship(
                            resource=_object("document", "doc-1"),
                            relation="reader",
                            subject=core_pb2.SubjectReference(
                                object=_object("user", "alice")
                            ),
                        ),
                    )
                ]
            ),
            metadata=metadata,
        )

        allowed = permissions.CheckPermission(
            _check_request("alice", freshness=write_response.written_at),
            metadata=metadata,
        )
        denied = permissions.CheckPermission(
            _check_request("bob", freshness=write_response.written_at),
            metadata=metadata,
        )
        assert (
            allowed.permissionship
            == permission_service_pb2.CheckPermissionResponse.Permissionship.Value(
                "PERMISSIONSHIP_HAS_PERMISSION"
            )
        )
        assert (
            denied.permissionship
            == permission_service_pb2.CheckPermissionResponse.Permissionship.Value(
                "PERMISSIONSHIP_NO_PERMISSION"
            )
        )

        delete_response = permissions.DeleteRelationships(
            permission_service_pb2.DeleteRelationshipsRequest(
                relationship_filter=permission_service_pb2.RelationshipFilter(
                    resource_type="document",
                    optional_resource_id="doc-1",
                    optional_relation="reader",
                    optional_subject_filter=permission_service_pb2.SubjectFilter(
                        subject_type="user", optional_subject_id="alice"
                    ),
                )
            ),
            metadata=metadata,
        )
        revoked = permissions.CheckPermission(
            _check_request("alice", freshness=delete_response.deleted_at),
            metadata=metadata,
        )
        assert (
            revoked.permissionship
            == permission_service_pb2.CheckPermissionResponse.Permissionship.Value(
                "PERMISSIONSHIP_NO_PERMISSION"
            )
        )
    finally:
        channel.close()


def test_spicedb_event_file_permission_preserves_independent_grants(
    spicedb_container: dict[str, str],
) -> None:
    """The canonical alias excludes only attendee, not overlapping graph grants."""
    from pathlib import Path
    from uuid import uuid4

    from authzed.api import v1

    prefix = "event-file-guard-" + uuid4().hex
    user_id = prefix + "-user"
    metadata = _metadata(spicedb_container["token"])
    channel = grpc.insecure_channel(spicedb_container["endpoint"])
    permissions = v1.PermissionsServiceStub(channel)
    owned_resources: set[tuple[str, str]] = set()

    def relationship(kind, resource, relation, subject_kind, subject):
        resource_id = prefix + "-" + resource
        owned_resources.add((kind, resource_id))
        return v1.Relationship(
            resource=_object(kind, resource_id),
            relation=relation,
            subject=v1.SubjectReference(
                object=_object(subject_kind, prefix + "-" + subject)
            ),
        )

    cases = [
        (
            "stale-attendee",
            False,
            [relationship("event", "stale-attendee", "attendee", "user", "user")],
        ),
        (
            "creator",
            True,
            [relationship("event", "creator", "creator", "user", "user")],
        ),
        (
            "semester-admin",
            True,
            [
                relationship(
                    "event", "semester-admin", "semester", "semester", "semester-parent"
                ),
                relationship("semester", "semester-parent", "admin", "user", "user"),
            ],
        ),
    ]
    for role in ("member", "student", "faculty", "admin"):
        name = "campus-" + role
        cases.append(
            (
                name,
                True,
                [
                    relationship("event", name, "campus", "campus", name),
                    relationship("campus", name, role, "user", "user"),
                ],
            )
        )
    for role in ("admin", "member", "auditor"):
        name = "tenant-" + role
        cases.append(
            (
                name,
                True,
                [
                    relationship("event", name, "tenant", "tenant", name),
                    relationship("tenant", name, role, "user", "user"),
                ],
            )
        )
        name = "campus-tenant-" + role
        cases.append(
            (
                name,
                True,
                [
                    relationship("event", name, "campus", "campus", name),
                    relationship("campus", name, "tenant", "tenant", name),
                    relationship("tenant", name, role, "user", "user"),
                ],
            )
        )
    cases.append(
        (
            "creator-and-attendee",
            True,
            [
                relationship(
                    "event", "creator-and-attendee", "creator", "user", "user"
                ),
                relationship(
                    "event", "creator-and-attendee", "attendee", "user", "user"
                ),
            ],
        )
    )
    try:
        schema = (Path(__file__).resolve().parents[2] / "schema.zed").read_text()
        v1.SchemaServiceStub(channel).WriteSchema(
            v1.WriteSchemaRequest(schema=schema), metadata=metadata, timeout=5
        )
        permissions.WriteRelationships(
            v1.WriteRelationshipsRequest(
                updates=[
                    v1.RelationshipUpdate(
                        operation=v1.RelationshipUpdate.OPERATION_TOUCH,
                        relationship=relation,
                    )
                    for _, _, relations in cases
                    for relation in relations
                ]
            ),
            metadata=metadata,
            timeout=5,
        )
        for name, expected_alias, _ in cases:
            for permission, expected in (
                ("view", True),
                ("view_without_attendee", expected_alias),
            ):
                response = permissions.CheckPermission(
                    v1.CheckPermissionRequest(
                        resource=_object("event", prefix + "-" + name),
                        permission=permission,
                        subject=v1.SubjectReference(object=_object("user", user_id)),
                        consistency=v1.Consistency(fully_consistent=True),
                    ),
                    metadata=metadata,
                    timeout=5,
                )
                assert (
                    response.permissionship
                    == v1.CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
                ) is expected, (name, permission)
    finally:
        try:
            for kind, resource_id in owned_resources:
                permissions.DeleteRelationships(
                    v1.DeleteRelationshipsRequest(
                        relationship_filter=v1.RelationshipFilter(
                            resource_type=kind, optional_resource_id=resource_id
                        )
                    ),
                    metadata=metadata,
                    timeout=5,
                )
        finally:
            channel.close()
