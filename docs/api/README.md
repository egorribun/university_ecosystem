# University Ecosystem API

The FastAPI application exposes the versioned REST surface under
`/api/v1`. The checked-in [OpenAPI 3.1 schema](../../frontend/openapi.json) is
the route and request/response source of truth; this page is an orientation,
not a second schema.

## Runtime documentation

In development, testing, or local environments the application serves:

- Swagger UI: `/api/docs`
- ReDoc: `/api/redoc`
- Raw schema: `/api/openapi.json`

Interactive documentation is disabled in other environments. Health probes are
available at `GET /health/live`, `GET /health/ready`, `GET /healthz`, and
`GET /ready`. The root endpoint is `GET /`.

## Authentication and cookies

Most `/api/v1` operations require the authenticated session established by
`POST /api/v1/auth/login/json` or the form-compatible
`POST /api/v1/auth/login`. Successful authentication sets the HttpOnly
`access_token_v2` cookie; the token is not returned in the JSON response.
Clients should send requests with their cookie jar enabled and must not copy
the token into local storage or an API payload.

The login/MFA flow may also set the short-lived `mfa_pre_auth_v1` cookie while
an MFA challenge is pending, and `trusted_device` when the user explicitly
chooses a trusted device. `GET /api/v1/auth/csrf-cookie` establishes the
browser-readable CSRF cookie used by state-changing cookie-authenticated
requests. Cookie flags and lifetimes are environment configuration; consult
the OpenAPI responses and deployment configuration rather than assuming a
fixed domain or `Secure` setting in local development.

## Route index

The following route families are present in the current OpenAPI schema. Use
the schema for exact parameters, security requirements, status codes, and
models.

| Area | Paths and operations |
| --- | --- |
| Auth and MFA | `/api/v1/auth/login`, `/api/v1/auth/login/json`, `/api/v1/auth/logout`, `/api/v1/auth/register`, `/api/v1/auth/csrf-cookie`; MFA enrollment/verification under `/api/v1/auth/mfa/{email,totp,recovery-codes,step-up}`; sessions under `/api/v1/auth/sessions` |
| Password | `POST /api/v1/password/forgot`, `POST /api/v1/password/reset` |
| Users and groups | `/api/v1/users`, `/api/v1/users/me`, `/api/v1/groups`, including profile, avatar/cover, email, password, export, and deletion operations |
| Events | `/api/v1/events`, `/api/v1/events/{event_id}`, `/api/v1/events/my`, `/api/v1/events/search/semantic`, `/api/v1/events/attendance`, and event file/image operations |
| News | `/api/v1/news`, `/api/v1/news/{id}`, comments, likes, interactions, semantic search, and image upload operations |
| Stories | `/api/v1/stories`, `/api/v1/stories/{story_id}`, and cover upload |
| Schedule | `/api/v1/schedule`, `/api/v1/schedule/{id}`, and `/api/v1/schedule/ics` |
| Chats | `/api/v1/chats`, `/api/v1/chats/{chat_id}`, messages, participants, reactions, read/typing, clear, forward, and group-chat operations |
| Notifications | `/api/v1/notifications`, read/delete operations, `/api/v1/notifications/read-all`, and notification dead-letter operations |
| Push | `/api/v1/push/subscribe`, `/api/v1/push/unsubscribe`, `/api/v1/push/topics`, VAPID key, broadcast/test, and admin topic operations |
| Search, statistics, integrations | `/api/v1/search`, `/api/v1/stats/{summary,attendance,grades,participation}`, `/api/v1/spotify/*` |
| Performance and media | `/api/v1/cwv/*`, `POST /api/v1/csp-report`, and `GET /api/v1/img/{path}` |
| WebSocket bootstrap | `POST /ws/ticket` issues a short-lived upgrade ticket; the WebSocket endpoint is `/ws` |
| Admin (non-versioned) | `GET /admin/audit`, `GET /admin/audit/time-travel`, and `GET /admin/feature-flags` |

Internal `/api/v1` routes and GraphQL are mounted with `include_in_schema=False`
and are intentionally absent from the public OpenAPI route index.

## Request examples

See [API examples](../API_EXAMPLES.md) for cookie-aware login, MFA, event,
notification, and WebSocket-ticket requests. Examples use placeholders and
never contain real credentials or tokens.
