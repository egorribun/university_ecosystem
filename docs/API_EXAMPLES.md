# API Examples

These examples follow the checked-in [OpenAPI schema](../frontend/openapi.json).
Use `/api/openapi.json` from a development instance for the live schema. All
identifiers and tokens below are placeholders.

## Login and MFA

### JSON login

```http
POST /api/v1/auth/login/json
Content-Type: application/json

# pragma: allowlist nextline secret -- documentation-only placeholder; never use as a credential
{"email":"student@example.test","password":"replace-me","trust_device":false}
```

The successful response contains the user/session payload and sets the
HttpOnly `access_token_v2` cookie. It does not return a bearer token field in
the JSON body. Keep the response cookie in the client cookie jar.

If another factor is required, the endpoint returns `202 Accepted` with a
challenge envelope similar to:

```json
{
  "status": "mfa_required",
  "user_id": "00000000-0000-0000-0000-000000000000",
  "session_id": "00000000-0000-0000-0000-000000000000",
  "default_method": "totp",
  "methods": [{
    "method": "totp",
    "challenge_token": "placeholder-challenge-token",
    "challenge_expires_at": "2026-01-01T00:00:00Z",
    "revision": 1
  }]
}
```

Verify the challenge with the method returned by the server:

```http
POST /api/v1/auth/mfa/verify
Content-Type: application/json
Cookie: mfa_pre_auth_v1=<challenge cookie>

{"method":"totp","challenge_token":"<challenge token>","code":"123456"}
```

The same operation accepts `email_otp` or `recovery_code` when the challenge
and account support that method. A recovery code is single-use. The form login
endpoint is `POST /api/v1/auth/login` with form fields `username`, `password`,
and optional `trust_device`. For an authenticated step-up challenge, retain
the `access_token_v2` cookie instead of the pending-login cookie.

### CSRF bootstrap

```http
GET /api/v1/auth/csrf-cookie
```

For cookie-authenticated state-changing requests, send the CSRF value from
the browser-readable `csrf_token` cookie in the header required by the client
contract. Do not log or persist cookie values.

## Registration

```http
POST /api/v1/auth/register
Content-Type: application/json

# pragma: allowlist nextline secret -- documentation-only placeholder; never use as a credential
{"email":"new@example.test","password":"replace-me","full_name":"Jane Smith"}
```

Registration does not establish an authenticated session; call the login
endpoint separately.

## Events and attendance

```http
GET /api/v1/events?limit=20&cursor=<cursor>
Cookie: access_token_v2=<cookie value>
```

```http
POST /api/v1/events/attendance
Content-Type: application/json
Cookie: access_token_v2=<cookie value>

{"event_id":"00000000-0000-0000-0000-000000000000"}
```

Cancel attendance with `DELETE /api/v1/events/attendance` using the request
shape documented by OpenAPI. Event uploads use the explicit
`/api/v1/events/{event_id}/upload_file` and
`/api/v1/events/upload_image` operations.

## Notifications

```http
GET /api/v1/notifications?limit=20&cursor=<cursor>
Cookie: access_token_v2=<cookie value>
```

Mark one notification with
`PATCH /api/v1/notifications/{notif_id}/read`, or all notifications with
`POST /api/v1/notifications/read-all`. The exact response and request models
are defined in OpenAPI; do not assume every collection uses the same cursor
fields.

## WebSocket ticket

```http
POST /ws/ticket
Cookie: access_token_v2=<cookie value>
```

The response is `201 Created` with a short-lived, single-use `ticket` and
`expires_in`. Connect the WebSocket at `/ws?ticket=<ticket>` before it expires.
The ticket is preferred over placing a JWT in a WebSocket query parameter or
protocol header.

## Errors

Validation and application errors use the JSON shape `{"detail":"..."}`.
Handle the status codes declared for each operation in OpenAPI, including
`401` for missing/invalid authentication, `422` for request validation, and
`429` with `Retry-After` when a rate limit is exceeded.
