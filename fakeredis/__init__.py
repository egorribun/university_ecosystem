"""Minimal fakeredis compatibility layer for tests.

This package provides a very small subset of the :mod:`fakeredis` API that our
unit tests rely on.  It is *not* a general purpose drop-in replacement, but it
implements enough of the asynchronous Redis client behaviour for the tests to
exercise the cache and rate-limiting components without pulling in the external
fakeredis dependency in production environments.
"""

from .aioredis import FakeRedis

__all__ = ["FakeRedis"]
