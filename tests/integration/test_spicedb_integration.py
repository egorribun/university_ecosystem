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
