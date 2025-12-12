# Load testing profiles

This folder contains reproducible k6 and Locust scenarios that cover the
high-traffic API routes used in benchmarks:

* `/schedule/{GROUP_ID}`
* `/news`
* `/events`
* `/chat/{CHAT_ID}/messages`

Both runners accept the same environment variables so you can compare cache
profiles quickly:

* `BASE_URL` – API base URL (default: `http://localhost:8000`).
* `AUTH_TOKEN` – bearer token for authenticated routes.
* `GROUP_ID` / `CHAT_ID` – identifiers for the schedule/chat paths.
* `CACHE_PROFILE` – tag value forwarded as the `X-Cache-Profile` header to
  distinguish Redis vs in-memory test runs.

## k6

```bash
BASE_URL=http://localhost:8000 \
AUTH_TOKEN="Bearer ..." \
k6 run scripts/loadtesting/k6-scenarios.js
```

The scenario matrix exercises cache hits (`If-None-Match` / ETag) and
compression negotiation (`Accept-Encoding: br,gzip`) for each route.

## Locust

```bash
BASE_URL=http://localhost:8000 \
AUTH_TOKEN="Bearer ..." \
locust -f scripts/loadtesting/locustfile.py
```

Weights mirror the k6 scenarios so results are comparable across Redis and
memory cache backends.
