"""Exact boundary and error contracts of the storage backends.

These pin the observable rules that object-key validation and bounded reads
enforce: the precise control-character range, messages callers match on,
logged event names, and how many bytes a bounded read may request.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services import storage
from app.services.storage import S3Storage, StaticFSStorage

# ---------------------------------------------------------------------------
# Control characters: C0 (< 0x20) and DEL (0x7F) only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a\x1fb", True),
        ("a\x7fb", True),
        ("a b", False),  # 0x20 is printable
        ("a\x80b", False),  # C1 range is not rejected
        ("plain", False),
    ],
)
def test_control_character_range(value: str, expected: bool) -> None:
    assert storage._has_control_chars(value) is expected


@pytest.mark.parametrize("key", ["a b.png", "café/\x80.png"])
def test_keys_with_space_or_c1_characters_are_valid(key: str) -> None:
    s3 = S3Storage(bucket="media")

    assert S3Storage._validated_key(key) == key
    assert s3._normalize_key(key) == key
    assert s3._extract_key(key) == key


@pytest.mark.parametrize("char", ["\\", "%", "?", "#", ";"])
def test_ambiguous_key_characters_are_rejected(char: str) -> None:
    assert S3Storage._validated_key(f"a{char}b") is None


def test_normalize_key_reports_control_characters_exactly() -> None:
    with pytest.raises(ValueError) as error:
        S3Storage(bucket="media")._normalize_key("a\x00b")

    assert str(error.value) == "Relative path contains control characters"


def test_normalize_key_reports_outer_whitespace_exactly() -> None:
    with pytest.raises(ValueError) as error:
        S3Storage(bucket="media")._normalize_key(" a.png")

    assert str(error.value) == "Relative path must not contain outer whitespace"


def test_extract_key_rejects_a_network_path_on_a_relative_base() -> None:
    s3 = S3Storage(bucket="media", base_url="/media")

    assert s3._extract_key("/media/a.png") == "a.png"
    assert s3._extract_key("///media/a.png") is None


def test_extract_key_rejects_a_scheme_without_a_host() -> None:
    assert S3Storage(bucket="media")._extract_key("file:a.png") is None


def test_extract_key_uses_the_constructor_normalized_base_path() -> None:
    s3 = S3Storage(bucket="media", base_url="https://cdn.example.com/files/")

    assert s3._extract_key("https://cdn.example.com/files/a.png") == "a.png"


# ---------------------------------------------------------------------------
# Bounded reads
# ---------------------------------------------------------------------------


class _Stream:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.requests: list[int | None] = []

    async def __aenter__(self) -> _Stream:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def read(self, size: int | None = None) -> bytes:
        self.requests.append(size)
        if size == 0 or not self.chunks:
            return b""
        return self.chunks.pop(0)


def _s3_with(stream: _Stream) -> S3Storage:
    client = MagicMock()
    client.get_object = AsyncMock(return_value={"Body": stream})
    return S3Storage(bucket="media", client=client)


@pytest.mark.asyncio
async def test_bounded_s3_read_stops_requesting_once_the_limit_is_reached() -> None:
    stream = _Stream([b"abc", b"def"])

    content = await _s3_with(stream).read_file("a.png", max_bytes=4)

    assert content == b"abcde"
    assert stream.requests == [5, 2]


@pytest.mark.asyncio
async def test_unbounded_s3_read_returns_the_whole_body() -> None:
    stream = _Stream([b"whole"])

    assert await _s3_with(stream).read_file("a.png") == b"whole"
    assert stream.requests == [None]


@pytest.mark.asyncio
async def test_zero_byte_bounds_are_allowed(tmp_path: Path) -> None:
    (tmp_path / "a.png").write_bytes(b"xy")
    stream = _Stream([b"x"])

    assert await _s3_with(stream).read_file("a.png", max_bytes=0) == b"x"
    assert await StaticFSStorage(tmp_path).read_file("a.png", max_bytes=0) == b"x"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["s3", "static"])
async def test_negative_bounds_are_rejected_exactly(
    backend: str, tmp_path: Path
) -> None:
    target = S3Storage(bucket="media") if backend == "s3" else StaticFSStorage(tmp_path)

    with pytest.raises(ValueError) as error:
        await target.read_file("a.png", max_bytes=-1)

    assert str(error.value) == "max_bytes must be nonnegative"


@pytest.mark.asyncio
async def test_unaddressable_s3_reads_name_the_requested_path() -> None:
    with pytest.raises(FileNotFoundError) as error:
        await S3Storage(bucket="media").read_file("../escape")

    assert str(error.value) == "S3 file not found: ../escape"


@pytest.mark.asyncio
async def test_s3_client_errors_without_a_code_are_not_treated_as_missing() -> None:
    client = MagicMock()
    failure = ClientError({}, "GetObject")
    client.get_object = AsyncMock(side_effect=failure)

    with pytest.raises(ClientError) as error:
        await S3Storage(bucket="media", client=client).read_file("a.png")

    assert error.value is failure


# ---------------------------------------------------------------------------
# Logged events and timeouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_s3_reads_log_a_stable_event() -> None:
    client = MagicMock()
    client.get_object = AsyncMock(side_effect=ConnectionError("down"))

    with patch.object(storage, "logger") as logger, pytest.raises(FileNotFoundError):
        await S3Storage(bucket="media", client=client).read_file("a.png")

    logger.error.assert_called_once_with("s3_read_failed")


@pytest.mark.asyncio
async def test_failed_s3_deletes_log_a_stable_event() -> None:
    client = MagicMock()
    client.delete_object = AsyncMock(side_effect=ConnectionError("down"))

    with patch.object(storage, "logger") as logger:
        await S3Storage(bucket="media", client=client).delete_file("a.png")

    logger.warning.assert_called_once_with("s3_delete_failed")


@pytest.mark.asyncio
async def test_bucket_probe_is_bounded_by_the_read_timeout() -> None:
    client = MagicMock()
    client.head_bucket = AsyncMock()
    deadlines: list[float | None] = []
    real_timeout = storage.asyncio.timeout

    def recording_timeout(delay: float | None):
        deadlines.append(delay)
        return real_timeout(delay)

    with patch.object(storage.asyncio, "timeout", side_effect=recording_timeout):
        await S3Storage(bucket="media", client=client).probe_bucket()

    assert deadlines == [storage._S3_READ_TIMEOUT]
    client.head_bucket.assert_awaited_once_with(Bucket="media")
