# ADR-003: Taskiq for Background Jobs

## Status
Accepted

## Context
We needed an async-first background job system that integrates well with our FastAPI + asyncio stack.

## Decision
We chose **Taskiq** as our background job framework.

## Rationale
1. **Async-native** - Built from ground up for asyncio
2. **Type hints** - Full typing support with IDE autocomplete
3. **Multiple brokers** - Redis, RabbitMQ, in-memory for testing
4. **FastAPI integration** - Seamless dependency injection
5. **Lightweight** - Minimal overhead compared to Celery

## Alternatives Considered
- **Celery**: Industry standard, but sync-first and heavy.
- **ARQ**: Good async support, but smaller ecosystem.
- **Dramatiq**: Good design, but less async-native.
- **RQ (Redis Queue)**: Simple, but limited features.

## Implementation Notes
- Redis broker for production
- In-memory broker for testing
- Middlewares for logging and error tracking
- Scheduled tasks via `taskiq-crontab`

## Consequences
- Smaller community than Celery
- Less battle-tested in enterprise
- Team needs to learn new API
