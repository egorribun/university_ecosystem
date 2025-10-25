"""A lightweight async Redis test double used in the unit tests.

The implementation intentionally covers only the subset of Redis commands that
our suite exercises.  It should not be considered a drop-in replacement for the
real :mod:`fakeredis` package.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class _SortedSetEntry:
    member: str
    score: float


class FakeRedis:
    """Minimal subset of :class:`redis.asyncio.Redis` methods."""

    def __init__(
        self, *, encoding: str = "utf-8", decode_responses: bool = False
    ) -> None:
        self.encoding = encoding
        self.decode_responses = decode_responses
        self._strings: Dict[str, str] = {}
        self._sorted_sets: Dict[str, List[_SortedSetEntry]] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Utility helpers
    def _now(self) -> float:
        return time.monotonic()

    def _encode(self, value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode(self.encoding or "utf-8", "ignore")
        return str(value)

    def _decode(self, value: str | None) -> Any:
        if value is None:
            return None
        if self.decode_responses:
            return value
        return value.encode(self.encoding or "utf-8")

    def _purge_if_expired(self, key: str) -> None:
        expires_at = self._expiry.get(key)
        if expires_at is not None and expires_at <= self._now():
            self._strings.pop(key, None)
            self._sorted_sets.pop(key, None)
            self._expiry.pop(key, None)

    def _set_expiry(self, key: str, *, seconds: float | None = None) -> None:
        if seconds is None:
            self._expiry.pop(key, None)
            return
        self._expiry[key] = self._now() + max(seconds, 0)

    # ------------------------------------------------------------------
    # Basic key/value operations
    async def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        px: int | None = None,
    ) -> None:
        async with self._lock:
            self._strings[key] = self._encode(value)
            ttl_seconds = None
            if px is not None:
                ttl_seconds = px / 1000
            elif ex is not None:
                ttl_seconds = float(ex)
            self._set_expiry(key, seconds=ttl_seconds)

    async def get(self, key: str) -> Any:
        async with self._lock:
            self._purge_if_expired(key)
            stored = self._strings.get(key)
            return self._decode(stored)

    async def delete(self, *keys: str) -> None:
        async with self._lock:
            for key in keys:
                self._strings.pop(key, None)
                self._sorted_sets.pop(key, None)
                self._expiry.pop(key, None)

    async def flushall(self) -> None:
        async with self._lock:
            self._strings.clear()
            self._sorted_sets.clear()
            self._expiry.clear()

    async def aclose(self) -> None:  # pragma: no cover - provided for compatibility
        return None

    # ------------------------------------------------------------------
    # Sorted set helpers used by the rate-limit implementation
    def _get_sorted_set(self, key: str) -> List[_SortedSetEntry]:
        zset = self._sorted_sets.get(key)
        if zset is None:
            zset = []
            self._sorted_sets[key] = zset
        return zset

    def _sorted_members(self, key: str) -> List[_SortedSetEntry]:
        self._purge_if_expired(key)
        return list(self._sorted_sets.get(key, []))

    async def zadd(self, key: str, *, mapping: Dict[str, float]) -> None:
        async with self._lock:
            self._purge_if_expired(key)
            zset = {entry.member: entry for entry in self._get_sorted_set(key)}
            for member, score in mapping.items():
                zset[member] = _SortedSetEntry(member=member, score=float(score))
            self._sorted_sets[key] = sorted(
                zset.values(), key=lambda entry: entry.score
            )

    async def zrange(
        self,
        key: str,
        start: int,
        stop: int,
        *,
        withscores: bool = False,
    ) -> List[Any]:
        async with self._lock:
            members = self._sorted_members(key)
            length = len(members)
            if length == 0:
                return []
            if start < 0:
                start = max(length + start, 0)
            if stop < 0:
                stop = length + stop
            if stop >= length:
                stop = length - 1
            if start > stop:
                return []
            subset = members[start : stop + 1]
            if withscores:
                return [[entry.member, entry.score] for entry in subset]
            return [entry.member for entry in subset]

    async def zcard(self, key: str) -> int:
        async with self._lock:
            return len(self._sorted_members(key))

    async def zremrangebyscore(
        self, key: str, min_score: float, max_score: float
    ) -> None:
        async with self._lock:
            members = [
                entry
                for entry in self._sorted_members(key)
                if not (min_score <= entry.score <= max_score)
            ]
            if members:
                self._sorted_sets[key] = members
            else:
                self._sorted_sets.pop(key, None)

    async def pexpire(self, key: str, ms: int) -> None:
        async with self._lock:
            self._set_expiry(key, seconds=max(ms, 0) / 1000)

    # ------------------------------------------------------------------
    # Lua ``eval`` support
    async def eval(self, script: str, numkeys: int, *args: Any) -> Iterable[int]:
        if numkeys != 1:
            raise NotImplementedError("FakeRedis only supports a single key for eval")
        if len(args) < 5:
            raise ValueError("Unexpected arguments for eval")
        key = args[0]
        now_ms = int(args[1])
        window_ms = int(args[2])
        limit = int(args[3])
        member = self._encode(args[4])
        window_seconds = max(window_ms, 1) / 1000
        cutoff = (now_ms - window_ms) / 1000

        async with self._lock:
            self._purge_if_expired(key)
            zset = self._get_sorted_set(key)
            zset[:] = [entry for entry in zset if entry.score > cutoff]
            count = len(zset)
            if count >= limit:
                retry_after = 0
                if zset:
                    oldest = zset[0]
                    retry_after = window_ms - int((now_ms / 1000 - oldest.score) * 1000)
                    if retry_after < 0:
                        retry_after = 0
                return [0, 0, retry_after]
            entry = _SortedSetEntry(member=member, score=now_ms / 1000)
            zset.append(entry)
            zset.sort(key=lambda item: item.score)
            remaining = limit - (count + 1)
            if remaining < 0:
                remaining = 0
            self._set_expiry(key, seconds=window_seconds)
            return [1, remaining, 0]

    # Convenience for compatibility with ``Redis.from_url`` usage in tests
    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        encoding: str = "utf-8",
        decode_responses: bool = False,
        health_check_interval: int | None = None,
    ) -> "FakeRedis":
        _ = (url, health_check_interval)
        return cls(encoding=encoding, decode_responses=decode_responses)
