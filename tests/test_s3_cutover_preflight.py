"""Fail-closed, read-only checks before switching persistent S3 storage."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

import scripts.s3_cutover_preflight as cutover
from scripts.s3_cutover_preflight import (
    _client_from_environment,
    _ensure_distinct_endpoints,
    compare_snapshots,
    snapshot_bucket,
)


class _Response(BytesIO):
    def release_conn(self) -> None:
        pass


class _ReadOnlyS3:
    def __init__(
        self,
        objects: dict[str, tuple[bytes, str]],
        metadata: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.objects = objects
        self.metadata = metadata or {}
        self.responses: list[_Response] = []
        self.versioning_status: str | None = None

    def get_bucket_versioning(self, bucket: str) -> SimpleNamespace:
        assert bucket == "uploads"
        return SimpleNamespace(status=self.versioning_status)

    def list_objects(self, bucket: str, *, recursive: bool) -> list[SimpleNamespace]:
        assert bucket == "uploads" and recursive
        return [
            SimpleNamespace(object_name=key, size=len(body))
            for key, (body, _) in self.objects.items()
        ]

    def stat_object(self, bucket: str, key: str) -> SimpleNamespace:
        assert bucket == "uploads"
        return SimpleNamespace(
            content_type=self.objects[key][1], metadata=self.metadata.get(key, {})
        )

    def get_object(self, bucket: str, key: str) -> _Response:
        assert bucket == "uploads"
        response = _Response(self.objects[key][0])
        self.responses.append(response)
        return response

    def put_object(self, *_args: object, **_kwargs: object) -> None:
        pytest.fail("preflight must never mutate storage")


def test_snapshot_hashes_every_object_and_closes_streams() -> None:
    client = _ReadOnlyS3({"avatars/a.png": (b"a" * 1024, "image/png")})

    snapshot = snapshot_bucket(client, "uploads")

    assert snapshot.count == 1
    assert snapshot.total_bytes == 1024
    assert len(snapshot.objects["avatars/a.png"].sha256) == 64
    assert snapshot.objects["avatars/a.png"].content_type == "image/png"
    assert all(response.closed for response in client.responses)


def test_snapshot_rejects_versioned_bucket() -> None:
    client = _ReadOnlyS3({"avatars/a.png": (b"a", "image/png")})
    client.versioning_status = "Enabled"

    with pytest.raises(ValueError, match="versioning"):
        snapshot_bucket(client, "uploads")


def test_compare_rejects_same_size_but_changed_bytes() -> None:
    source = snapshot_bucket(_ReadOnlyS3({"a": (b"one", "text/plain")}), "uploads")
    target = snapshot_bucket(_ReadOnlyS3({"a": (b"two", "text/plain")}), "uploads")

    assert compare_snapshots(source, target) is False


def test_compare_rejects_missing_object_or_changed_content_type() -> None:
    source = snapshot_bucket(_ReadOnlyS3({"a": (b"one", "text/plain")}), "uploads")
    missing = snapshot_bucket(_ReadOnlyS3({}), "uploads")
    wrong_type = snapshot_bucket(
        _ReadOnlyS3({"a": (b"one", "application/octet-stream")}), "uploads"
    )

    assert not compare_snapshots(source, missing)
    assert not compare_snapshots(source, wrong_type)


def test_http_override_rejects_nonlocal_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_SOURCE_ENDPOINT", "http://object-storage.example:9000")
    monkeypatch.setenv("S3_SOURCE_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SOURCE_SECRET_KEY", "test-secret")

    with pytest.raises(ValueError, match="local Compose"):
        _client_from_environment("SOURCE", allow_http=True)


def test_compare_rejects_changed_user_metadata() -> None:
    objects = {"a": (b"same", "text/plain")}
    source = snapshot_bucket(
        _ReadOnlyS3(objects, {"a": {"x-amz-meta-color": "blue"}}), "uploads"
    )
    target = snapshot_bucket(
        _ReadOnlyS3(objects, {"a": {"x-amz-meta-color": "red"}}), "uploads"
    )

    assert not compare_snapshots(source, target)


def test_verify_rejects_same_source_and_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_SOURCE_ENDPOINT", "https://store.example:443")
    monkeypatch.setenv("S3_TARGET_ENDPOINT", "https://store.example:443/")

    with pytest.raises(ValueError, match="distinct"):
        _ensure_distinct_endpoints()


def test_verify_rejects_dns_aliases_of_the_same_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_SOURCE_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("S3_TARGET_ENDPOINT", "http://seaweedfs-target:9000")

    def resolve(host: str, port: int, **_kwargs: object) -> list[tuple[object, ...]]:
        assert host in {"minio", "seaweedfs-target"}
        return [(None, None, None, None, ("10.0.0.7", port))]

    monkeypatch.setattr(
        cutover,
        "socket",
        SimpleNamespace(getaddrinfo=resolve, SOCK_STREAM=1),
        raising=False,
    )
    with pytest.raises(ValueError, match="distinct"):
        _ensure_distinct_endpoints()


def test_verify_rejects_unresolved_target_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_SOURCE_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("S3_TARGET_ENDPOINT", "http://seaweedfs-target:9000")

    def resolve(host: str, port: int, **_kwargs: object) -> list[tuple[object, ...]]:
        if host == "seaweedfs-target":
            raise OSError("DNS unavailable")
        return [(None, None, None, None, ("10.0.0.7", port))]

    monkeypatch.setattr(
        cutover,
        "socket",
        SimpleNamespace(getaddrinfo=resolve, SOCK_STREAM=1),
        raising=False,
    )
    with pytest.raises(OSError, match="DNS unavailable"):
        _ensure_distinct_endpoints()


def test_verify_rejects_bucket_other_than_deployed_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_CUTOVER_BUCKET", "other")

    assert cutover.main(["verify"]) == 2


@pytest.mark.parametrize(
    ("source_address", "target_address", "expected_error"),
    [
        ("10.0.0.7", "10.0.0.8", None),
        ("10.0.0.7", "10.0.0.7", "distinct"),
        ("10.0.0.7", None, "unresolved"),
    ],
)
def test_verify_requires_independent_resolved_endpoint_identity(
    monkeypatch: pytest.MonkeyPatch,
    source_address: str,
    target_address: str | None,
    expected_error: str | None,
) -> None:
    monkeypatch.setenv("S3_SOURCE_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("S3_TARGET_ENDPOINT", "http://seaweedfs-target:9001")

    def resolve(host: str, port: int, **_kwargs: object) -> list[tuple[object, ...]]:
        address = source_address if host == "minio" else target_address
        return [(None, None, None, None, (address, port))] if address else []

    monkeypatch.setattr(
        cutover,
        "socket",
        SimpleNamespace(getaddrinfo=resolve, SOCK_STREAM=1),
    )
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):
            _ensure_distinct_endpoints()
    else:
        _ensure_distinct_endpoints()
