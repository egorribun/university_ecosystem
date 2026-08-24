# ADR-018: CQRS Pattern Implementation

## Status
Accepted

## Context
As the university ecosystem backend (Python/FastAPI) grew, complex business logic like schedule management and user activity analysis started to bloat standard CRUD controllers. We needed a pattern to separate the write logic (Commands) from the read logic (Queries) to improve maintainability, testing isolation, and performance.

## Decision
We implemented a lightweight **CQRS (Command Query Responsibility Segregation)** pattern in the Python backend.

Key components:
1. **Command/Query Base Classes**: Simple markers for messages.
2. **Handlers**: Classes implementing a `handle()` method for specific messages.
3. **Bus**: Central dispatchers (`CommandBus`, `QueryBus`) that resolve handlers via the Dishka DI container.
4. **Middleware**: Hooks for cross-cutting concerns (logging, validation, performance tracking) executed in the bus.

## Rationale
1. **Single Responsibility**: Handlers focus on one specific business operation.
2. **Testing**: Handlers are easily unit-tested by mocking dependencies provided by Dishka.
3. **Middleware Support**: Shared logic (like logging or authorization checks) can be applied globally via the bus.
4. **Read/Write Separation**: Allows optimizing read paths (e.g. using specific SQL views or caching) without affecting write models.

## Consequences
- More boilerplate (Commands/Queries + Handlers + Registrations).
- Indirect flow: finding the implementation of an API endpoint requires tracing the bus dispatch.
- Requires Dishka container management for handler registration.

## References
- `app/cqrs/base.py`
- `app/cqrs/bus.py`
- `app/cqrs/queries.py` (`GetScheduleQuery` and `GetScheduleHandler`)
