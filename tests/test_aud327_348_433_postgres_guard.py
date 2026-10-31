"""Exercise the PostgreSQL evidence fixture's refusal paths without a server."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tests.integration import test_aud327_348_433_migration_postgres as evidence


class _Client:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.api = self
        self.metadata = metadata
        self.closed = False

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        return self.metadata

    def close(self) -> None:
        self.closed = True


def _metadata() -> dict[str, Any]:
    return {
        "Id": "a" * 64,
        "Config": {
            "Image": evidence.IMAGE,
            "Labels": {"university-ecosystem.dev/test-owner": "audit-test"},
        },
        "State": {"Running": True},
        "NetworkSettings": {
            "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "33019"}]}
        },
    }


_URL = "postgresql+asyncpg://test@127.0.0.1:33019/test_" + "0" * 20


@pytest.mark.parametrize(
    "fault", ["identity", "image", "stopped", "owner", "host", "port", "extra_binding"]
)
def test_container_guard_rejects_wrong_ownership_or_endpoint(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    metadata = _metadata()
    if fault == "identity":
        metadata["Id"] = "b" * 64
    elif fault == "image":
        metadata["Config"]["Image"] = "different-image"
    elif fault == "stopped":
        metadata["State"]["Running"] = False
    elif fault == "owner":
        metadata["Config"]["Labels"]["university-ecosystem.dev/test-owner"] = "other"
    elif fault == "host":
        metadata["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "192.0.2.1"
    elif fault == "port":
        metadata["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "33020"
    else:
        metadata["NetworkSettings"]["Ports"]["5432/tcp"].append(
            {"HostIp": "192.0.2.2", "HostPort": "33019"}
        )
    client = _Client(metadata)
    monkeypatch.setattr(evidence.docker, "from_env", lambda: client)

    with pytest.raises(RuntimeError, match="ownership, image or port mismatch"):
        evidence._verify_owned_container("a" * 64, "audit-test", _URL)
    assert client.closed


def test_container_guard_accepts_the_exact_owned_loopback_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(_metadata())
    monkeypatch.setattr(evidence.docker, "from_env", lambda: client)
    evidence._verify_owned_container("a" * 64, "audit-test", _URL)
    assert client.closed


@pytest.mark.parametrize(
    ("container_id", "owner"),
    [("", "audit-test"), ("x" * 64, "audit-test"), ("a" * 64, "")],
)
def test_container_guard_requires_identity_before_inspection(
    monkeypatch: pytest.MonkeyPatch, container_id: str, owner: str
) -> None:
    def unexpected_docker() -> None:
        pytest.fail("Invalid identity must be refused before inspecting Docker")

    monkeypatch.setattr(evidence.docker, "from_env", unexpected_docker)
    with pytest.raises(RuntimeError, match="exact owned container ID"):
        evidence._verify_owned_container(container_id, owner, _URL)


@pytest.mark.parametrize("occupied_query", range(4))
def test_empty_catalog_guard_rejects_each_kind_of_preexisting_object(
    occupied_query: int,
) -> None:
    flags = iter(index == occupied_query for index in range(4))
    connection = SimpleNamespace(
        exec_driver_sql=lambda _query: SimpleNamespace(scalar_one=lambda: next(flags))
    )
    with pytest.raises(RuntimeError, match="not initially empty"):
        evidence._assert_initially_empty(connection)


def test_empty_catalog_guard_accepts_only_four_empty_catalog_checks() -> None:
    queries: list[str] = []

    def execute(query: str) -> SimpleNamespace:
        queries.append(query)
        return SimpleNamespace(scalar_one=lambda: False)

    evidence._assert_initially_empty(SimpleNamespace(exec_driver_sql=execute))
    assert len(queries) == 4


def test_source_extraction_is_limited_to_the_selected_sql_fragments() -> None:
    add_student, update = evidence._role_sql()
    assert add_student == "ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'student'"
    assert "SET role = LOWER(role::text)::userrole" in update
    assert "WHERE role::text != LOWER(role::text)" in update
    assert "PARTITION BY RANGE (created_at)" in evidence._notifications_ddl()
