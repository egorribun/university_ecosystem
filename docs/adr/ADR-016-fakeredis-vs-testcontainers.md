# ADR-016: Selection of FakeRedis vs Testcontainers for Redis Testing

## Status
Accepted

## Context
Our Python backend relies heavily on Redis for caching, session management, rate limiting, and background job queuing (via Arq). To ensure the reliability of these components, we needed a robust testing strategy for our Redis interactions.

The two main approaches considered were:
1. **[FakeRedis](https://github.com/cunla/fakeredis-py)**: An in-memory, pure-Python mock of the Redis API.
2. **[Testcontainers](https://testcontainers.com/)**: A framework for spinning up real Docker containers (including Redis) during test execution.

## Decision
We chose to use **FakeRedis** for our unit and integration test suites, while reserving **Testcontainers** (or a fixed local Docker instance) for a small subset of critical end-to-end (E2E) and concurrency tests.

## Rationale
1. **Speed and Resource Efficiency**: FakeRedis runs entirely in-memory within the Python process. It eliminates the overhead of pulling Docker images, starting containers, and managing network bindings. This allows our test suite to execute in seconds rather than minutes, encouraging frequent local test runs and fast CI feedback.
2. **Test Isolation**: FakeRedis makes it trivial to ensure a clean state for every test case. We can simply instantiate a new `FakeRedis` client or flush the existing one without the latency of clearing a real database over a socket connection.
3. **Sufficient API Coverage**: FakeRedis implements the vast majority of the Redis commands we use (e.g., SET, GET, INCR, HSET, EXPIRE, PUBLISH, SUBSCRIBE). For standard caching and session operations, it provides a perfectly adequate fidelity.
4. **Drawbacks of Testcontainers**: While Testcontainers provides 100% fidelity by using the real Redis engine, the setup latency and Docker dependency make the local development experience brittle (especially on Windows or macOS where Docker Desktop is required).

## Mitigations for FakeRedis Limitations
FakeRedis is an emulation, and therefore might drift from actual Redis behavior in complex scenarios (like Lua scripts or specific blocking operations).
- To mitigate this, our `test_mfa_challenge_race_condition` and other highly concurrent tests are designed to be run against a real Redis instance if needed, and we rely on the staging environment for final validation of complex Redis Lua scripts.

## Consequences
- Developers do not need Docker running locally to execute the vast majority of the backend test suite.
- Tests involving Redis are fast and deterministic.
- If a new, highly specific Redis module or command is used (e.g., RedisJSON or RediSearch), FakeRedis may not support it, forcing a re-evaluation or the targeted introduction of Testcontainers for those specific tests.
