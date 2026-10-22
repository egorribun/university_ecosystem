from __future__ import annotations

import base64
import errno
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from botocore.exceptions import ClientError

from app.services.storage import (
    S3Storage,
    StaticFSStorage,
    UnsafeQuarantineInventoryKey,
)


def _cursor_for(payload: object) -> str:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


@pytest.mark.asyncio
async def test_static_quarantine_inventory_pages_only_regular_files_under_exact_prefix(
    tmp_path: Path,
) -> None:
    storage = StaticFSStorage(tmp_path)
    (tmp_path / "quarantine" / "first").mkdir(parents=True)
    (tmp_path / "quarantine" / "nested").mkdir()
    (tmp_path / "quarantine" / "first" / "one.bin").write_bytes(b"1")
    (tmp_path / "quarantine" / "nested" / "two.bin").write_bytes(b"22")
    (tmp_path / "quarantine-escape").mkdir()
    (tmp_path / "quarantine-escape" / "not-quarantined.bin").write_bytes(b"x")
    (tmp_path / "public.bin").write_bytes(b"public")

    cursor: str | None = None
    observed: list[tuple[str, int]] = []
    while True:
        page = await storage.list_quarantine_page(cursor, limit=1)
        assert len(page.objects) <= 1
        observed.extend((item.key, item.size_bytes) for item in page.objects)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert observed == [
        ("quarantine/first/one.bin", 1),
        ("quarantine/nested/two.bin", 2),
    ]


@pytest.mark.asyncio
async def test_static_quarantine_inventory_treats_missing_root_as_empty(
    tmp_path: Path,
) -> None:
    page = await StaticFSStorage(tmp_path).list_quarantine_page(None, limit=10)

    assert page.objects == ()
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_static_quarantine_inventory_rejects_non_directory_root(
    tmp_path: Path,
) -> None:
    (tmp_path / "quarantine").write_bytes(b"not a directory")

    with pytest.raises(RuntimeError, match="not a directory"):
        await StaticFSStorage(tmp_path).list_quarantine_page(None, limit=10)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        "!",
        base64.urlsafe_b64encode(b"not-json").decode("ascii").rstrip("="),
        _cursor_for({"version": 2, "stack": []}),
        _cursor_for({"version": 1, "stack": [["quarantine", -1]]}),
        _cursor_for({"version": 1, "stack": [["outside", 0]]}),
    ],
)
async def test_static_quarantine_inventory_rejects_invalid_cursors(
    tmp_path: Path, cursor: str
) -> None:
    with pytest.raises(ValueError, match="Invalid quarantine inventory cursor"):
        await StaticFSStorage(tmp_path).list_quarantine_page(cursor, limit=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 1001, True])
async def test_static_quarantine_inventory_rejects_unbounded_page_sizes(
    tmp_path: Path, limit: int
) -> None:
    with pytest.raises(ValueError, match="page size"):
        await StaticFSStorage(tmp_path).list_quarantine_page(None, limit=limit)


@pytest.mark.asyncio
async def test_static_quarantine_inventory_stops_at_directory_entry_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir()
    (quarantine / "first.bin").write_bytes(b"1")
    (quarantine / "second.bin").write_bytes(b"2")
    monkeypatch.setattr("app.services.storage._QUARANTINE_DIRECTORY_ENTRIES_MAX", 1)

    with pytest.raises(RuntimeError, match="exceeds the inventory bound"):
        await StaticFSStorage(tmp_path).list_quarantine_page(None, limit=10)


@pytest.mark.asyncio
async def test_static_quarantine_inventory_ignores_non_file_directory_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "quarantine").mkdir()
    monkeypatch.setattr(
        StaticFSStorage,
        "_read_quarantine_directory",
        staticmethod(lambda _path: [("special-entry", "other")]),
    )

    page = await StaticFSStorage(tmp_path).list_quarantine_page(None, limit=10)

    assert page.objects == ()


def test_static_quarantine_directory_classifies_special_entries_without_following(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SpecialEntry:
        name = "special-entry"

        def is_symlink(self) -> bool:
            return False

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return False

        def is_file(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return False

    class DirectoryScan:
        def __enter__(self) -> DirectoryScan:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> Iterator[SpecialEntry]:
            return iter([SpecialEntry()])

    monkeypatch.setattr(
        "app.services.storage.os.scandir", lambda _path: DirectoryScan()
    )

    entries = StaticFSStorage._read_quarantine_directory(tmp_path)

    assert entries == [("special-entry", "other")]


@pytest.mark.asyncio
async def test_static_quarantine_inventory_ignores_entry_replaced_by_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir()
    (quarantine / "replaced.bin").mkdir()
    monkeypatch.setattr(
        StaticFSStorage,
        "_read_quarantine_directory",
        staticmethod(lambda _path: [("replaced.bin", "file")]),
    )

    page = await StaticFSStorage(tmp_path).list_quarantine_page(None, limit=10)

    assert page.objects == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe_name", ["bad\\name.bin", "bad\nname.bin"])
async def test_static_quarantine_inventory_rejects_unsafe_discovered_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe_name: str
) -> None:
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir()
    regular_file = quarantine / "safe-on-this-platform.bin"
    regular_file.write_bytes(b"payload")
    storage = StaticFSStorage(tmp_path)
    monkeypatch.setattr(
        StaticFSStorage,
        "_read_quarantine_directory",
        staticmethod(lambda _path: [(unsafe_name, "file")]),
    )

    def resolve(relative: Path) -> Path:
        return quarantine if relative == Path("quarantine") else regular_file

    monkeypatch.setattr(storage, "_resolve_validated_path", resolve)

    with pytest.raises(UnsafeQuarantineInventoryKey):
        await storage.list_quarantine_page(None, limit=10)


@pytest.mark.asyncio
async def test_static_quarantine_delete_verifies_existing_and_already_absent_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quarantine" / "one.bin"
    path.parent.mkdir()
    path.write_bytes(b"payload")
    storage = StaticFSStorage(tmp_path)

    assert await storage.delete_quarantine_key("quarantine/one.bin") is True
    assert await storage.delete_quarantine_key("quarantine/one.bin") is True


@pytest.mark.asyncio
async def test_static_quarantine_inventory_and_delete_do_not_follow_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = StaticFSStorage(tmp_path)
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"must remain")
    link = quarantine / "linked.bin"
    try:
        os.symlink(outside, link)
    except NotImplementedError:
        assert not os.path.lexists(link)
    except OSError as exc:
        unsupported_errors = {
            errno.EACCES,
            errno.EINVAL,
            errno.ENOSYS,
            errno.EPERM,
        }
        unsupported_errors.add(getattr(errno, "EOPNOTSUPP", errno.ENOSYS))
        if (
            exc.errno not in unsupported_errors
            and getattr(exc, "winerror", None) != 1314
        ):
            raise
        assert not os.path.lexists(link)
    page = await storage.list_quarantine_page(None, limit=10)
    assert page.objects == ()
    if os.path.lexists(link):
        with pytest.raises(ValueError, match="Symlink detected"):
            await storage.delete_quarantine_key("quarantine/linked.bin")
        assert outside.read_bytes() == b"must remain"

    synthetic_link = quarantine / "synthetic-linked.bin"

    class SymlinkEntry:
        name = synthetic_link.name

        def is_symlink(self) -> bool:
            return True

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            raise AssertionError("symlink entries must not be followed")

        def is_file(self, *, follow_symlinks: bool) -> bool:
            raise AssertionError("symlink entries must not be followed")

    class DirectoryScan:
        def __enter__(self) -> DirectoryScan:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> Iterator[SymlinkEntry]:
            return iter([SymlinkEntry()])

    with monkeypatch.context() as scan_patch:
        scan_patch.setattr(
            "app.services.storage.os.scandir",
            lambda _path: DirectoryScan(),
        )
        assert StaticFSStorage._read_quarantine_directory(quarantine) == [
            (synthetic_link.name, "symlink")
        ]

    original_is_symlink = Path.is_symlink

    def observe_synthetic_symlink(path: Path) -> bool:
        if path == synthetic_link:
            return True
        return original_is_symlink(path)

    with monkeypatch.context() as synthetic_patch:
        synthetic_patch.setattr(
            storage,
            "_read_quarantine_directory",
            lambda _path: [(synthetic_link.name, "symlink")],
        )
        synthetic_patch.setattr(Path, "is_symlink", observe_synthetic_symlink)
        page = await storage.list_quarantine_page(None, limit=10)
        assert page.objects == ()
        with pytest.raises(ValueError, match="Symlink detected"):
            await storage.delete_quarantine_key("quarantine/synthetic-linked.bin")
    assert outside.read_bytes() == b"must remain"


@pytest.mark.asyncio
async def test_s3_quarantine_inventory_uses_bounded_exact_prefix_pages() -> None:
    first_updated = datetime(2026, 10, 20, tzinfo=UTC)
    second_updated = datetime(2026, 10, 19, tzinfo=UTC)
    client = AsyncMock()
    client.list_objects_v2 = AsyncMock(
        side_effect=[
            {
                "Contents": [
                    {
                        "Key": "quarantine/a.bin",
                        "Size": 3,
                        "LastModified": first_updated,
                    },
                    {
                        "Key": "quarantine-escape/b.bin",
                        "Size": 100,
                        "LastModified": first_updated,
                    },
                ],
                "IsTruncated": True,
                "NextContinuationToken": "next-page-token",
            },
            {
                "Contents": [
                    {"Key": "quarantine/", "Size": 0, "LastModified": first_updated},
                    {
                        "Key": "quarantine/nested/c.bin",
                        "Size": 5,
                        "LastModified": second_updated,
                    },
                ],
                "IsTruncated": False,
            },
        ]
    )
    storage = S3Storage(bucket="quarantine-test", client=client)

    first = await storage.list_quarantine_page(None, limit=2)
    second = await storage.list_quarantine_page(first.next_cursor, limit=2)

    assert [
        (item.key, item.size_bytes, item.last_modified) for item in first.objects
    ] == [("quarantine/a.bin", 3, first_updated)]
    assert first.next_cursor == "next-page-token"
    assert [
        (item.key, item.size_bytes, item.last_modified) for item in second.objects
    ] == [("quarantine/nested/c.bin", 5, second_updated)]
    assert second.next_cursor is None
    assert client.list_objects_v2.await_args_list == [
        call(
            Bucket="quarantine-test",
            Prefix="quarantine/",
            MaxKeys=2,
        ),
        call(
            Bucket="quarantine-test",
            Prefix="quarantine/",
            MaxKeys=2,
            ContinuationToken="next-page-token",
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 1001, True])
async def test_s3_quarantine_inventory_rejects_unbounded_page_sizes(
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="page size"):
        await S3Storage(
            bucket="quarantine-test", client=AsyncMock()
        ).list_quarantine_page(None, limit=limit)


@pytest.mark.asyncio
async def test_s3_quarantine_inventory_rejects_empty_cursor() -> None:
    with pytest.raises(ValueError, match="Invalid S3 quarantine inventory cursor"):
        await S3Storage(
            bucket="quarantine-test", client=AsyncMock()
        ).list_quarantine_page("", limit=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{"Contents": []}, None])
async def test_s3_quarantine_inventory_requires_explicit_truncation_status(
    response: object,
) -> None:
    client = AsyncMock()
    client.list_objects_v2.return_value = response

    with pytest.raises(RuntimeError, match="invalid quarantine page status"):
        await S3Storage(bucket="quarantine-test", client=client).list_quarantine_page(
            None, limit=10
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            {"Contents": {}, "IsTruncated": False},
            "invalid quarantine inventory page",
        ),
        (
            {
                "Contents": [{"Key": "quarantine/a", "Size": 0}] * 2,
                "IsTruncated": False,
            },
            "invalid quarantine inventory page",
        ),
        (
            {"Contents": [None], "IsTruncated": False},
            "invalid quarantine object metadata",
        ),
        (
            {"Contents": [{"Key": None, "Size": 0}], "IsTruncated": False},
            "invalid quarantine object key",
        ),
        (
            {
                "Contents": [{"Key": "quarantine/a", "Size": True}],
                "IsTruncated": False,
            },
            "invalid quarantine object size",
        ),
        (
            {
                "Contents": [{"Key": "quarantine/a", "Size": -1}],
                "IsTruncated": False,
            },
            "invalid quarantine object size",
        ),
        ({"Contents": [], "IsTruncated": 1}, "invalid quarantine page status"),
        (
            {"Contents": [], "IsTruncated": True},
            "omitted its quarantine continuation token",
        ),
    ],
)
async def test_s3_quarantine_inventory_rejects_malformed_pages(
    response: dict[str, object], message: str
) -> None:
    client = AsyncMock()
    client.list_objects_v2.return_value = response

    with pytest.raises(RuntimeError, match=message):
        await S3Storage(bucket="quarantine-test", client=client).list_quarantine_page(
            None, limit=1
        )


@pytest.mark.asyncio
async def test_s3_quarantine_inventory_normalizes_and_omits_unusable_timestamps() -> (
    None
):
    client = AsyncMock()
    client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "quarantine/naive.bin",
                "Size": 1,
                "LastModified": datetime(2026, 10, 20),
            },
            {
                "Key": "quarantine/invalid-time.bin",
                "Size": 2,
                "LastModified": "not-a-datetime",
            },
        ],
        "IsTruncated": False,
    }

    page = await S3Storage(
        bucket="quarantine-test", client=client
    ).list_quarantine_page(None, limit=2)

    assert page.objects[0].last_modified == datetime(2026, 10, 20, tzinfo=UTC)
    assert page.objects[1].last_modified is None


@pytest.mark.asyncio
async def test_s3_inventory_fails_closed_on_malformed_key_inside_owned_prefix() -> None:
    client = AsyncMock()
    client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "quarantine/../outside.bin", "Size": 1},
        ],
        "IsTruncated": False,
    }

    with pytest.raises(RuntimeError, match="invalid quarantine object key"):
        await S3Storage(bucket="quarantine-test", client=client).list_quarantine_page(
            None, limit=1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["filesystem", "s3"])
async def test_quarantine_delete_rejects_keys_outside_the_owned_prefix(
    backend: str, tmp_path: Path
) -> None:
    client = AsyncMock()
    storage = (
        StaticFSStorage(tmp_path)
        if backend == "filesystem"
        else S3Storage(bucket="quarantine-test", client=client)
    )

    with pytest.raises(ValueError, match="quarantine prefix"):
        await storage.delete_quarantine_key("users/private.bin")

    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["Enabled", "Suspended", "unknown"])
async def test_s3_quarantine_rejects_versioned_or_unknown_bucket_state(
    status: str,
) -> None:
    client = AsyncMock()
    response = {"Status": status} if status != "unknown" else {"Unexpected": True}
    client.get_bucket_versioning.return_value = response
    storage = S3Storage(bucket="quarantine-test", client=client)

    with pytest.raises(RuntimeError, match="unversioned S3 bucket"):
        await storage.assert_quarantine_versioning_disabled()

    client.get_bucket_versioning.assert_awaited_once_with(Bucket="quarantine-test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"MFADelete": "Enabled"},
        {"ResponseMetadata": "malformed"},
    ],
)
async def test_s3_quarantine_rejects_uncertain_versioning_metadata(
    response: dict[str, object],
) -> None:
    client = AsyncMock()
    client.get_bucket_versioning.return_value = response

    with pytest.raises(RuntimeError, match="unversioned S3 bucket"):
        await S3Storage(
            bucket="quarantine-test", client=client
        ).assert_quarantine_versioning_disabled()


@pytest.mark.asyncio
async def test_s3_quarantine_accepts_bucket_without_versioning_history() -> None:
    client = AsyncMock()
    client.get_bucket_versioning.return_value = {
        "ResponseMetadata": {"HTTPStatusCode": 200}
    }
    storage = S3Storage(bucket="quarantine-test", client=client)

    await storage.assert_quarantine_versioning_disabled()

    client.get_bucket_versioning.assert_awaited_once_with(Bucket="quarantine-test")


@pytest.mark.asyncio
async def test_s3_quarantine_delete_requires_head_absence_before_release() -> None:
    client = AsyncMock()
    client.delete_object.return_value = {}
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )
    storage = S3Storage(bucket="quarantine-test", client=client)

    assert await storage.delete_quarantine_key("quarantine/one.bin") is True
    client.delete_object.assert_awaited_once_with(
        Bucket="quarantine-test", Key="quarantine/one.bin"
    )
    client.head_object.assert_awaited_once_with(
        Bucket="quarantine-test", Key="quarantine/one.bin"
    )


@pytest.mark.asyncio
async def test_s3_quarantine_delete_keeps_charge_if_object_remains() -> None:
    client = AsyncMock()
    client.delete_object.return_value = {}
    client.head_object.return_value = {"ContentLength": 3}
    storage = S3Storage(bucket="quarantine-test", client=client)

    assert await storage.delete_quarantine_key("quarantine/one.bin") is False


@pytest.mark.asyncio
async def test_s3_quarantine_delete_propagates_unverified_head_errors() -> None:
    client = AsyncMock()
    client.delete_object.return_value = {}
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "403"}}, "HeadObject"
    )

    with pytest.raises(ClientError):
        await S3Storage(bucket="quarantine-test", client=client).delete_quarantine_key(
            "quarantine/one.bin"
        )
