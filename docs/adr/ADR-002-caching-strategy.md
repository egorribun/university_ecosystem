# ADR-002: Redis for Distributed Caching

## Status
Accepted

## Context
The application needed a caching solution that works across multiple instances for session storage, rate limiting, and data caching.

## Decision
We chose **Redis** as our distributed caching layer.

## Rationale
1. **Speed** - In-memory with O(1) operations
2. **Data structures** - Supports strings, hashes, lists, sets, sorted sets
3. **Pub/Sub** - Enables real-time features and cache invalidation
4. **Atomic operations** - INCR for rate limiting, SETNX for locking
5. **Clustering** - Horizontal scaling support
6. **Ecosystem** - Excellent Python async support (aioredis/redis-py)

## Alternatives Considered
- **Memcached**: Simpler, but lacks data structures and persistence.
- **PostgreSQL caching**: Already used for DB, but adds query overhead.
- **Hazelcast/Apache Ignite**: Overkill for our scale.

## Implementation Notes
- L1 in-memory cache (LRU, 30s TTL) + L2 Redis (5min TTL)
- Connection pooling configured in `config.py`
- Graceful fallback when Redis unavailable

## Consequences
- Additional infrastructure dependency
- Requires monitoring (memory, connections, hit rate)
- Network latency for cache misses
