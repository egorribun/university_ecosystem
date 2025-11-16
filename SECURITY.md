# Security Policy

## Supported Versions
We actively maintain and provide security updates for the latest released version of this project. Older versions may no longer receive security fixes, so upgrading to the most recent release is strongly recommended.

## Reporting a Vulnerability
If you discover a vulnerability, please report it privately so we can address it promptly. We aim to acknowledge new reports within 72 hours.

## Private Vulnerability Reporting
To report a vulnerability, use the **Security** tab on GitHub and open a new **Private vulnerability report**. Issues are disabled for vulnerability discussions; instead, please submit a GitHub Security Advisory so the team can work with you directly on mitigation and disclosure.

## Password Storage & Policy

- We hash passwords with Argon2id via Passlib using time cost **3**, memory cost **65536 KiB** (~64 MB) and parallelism **4**.
- Legacy bcrypt hashes are accepted for login and rehashed to Argon2id on success; bcrypt's 72-byte input limit is enforced during legacy hashing to prevent silent truncation issues.
- Password length requirements: **8–200 characters**. Unicode is fully supported and input is stored verbatim (no trimming or normalization).
- Password changes and account provisioning use the same policy and algorithm, and the behaviour is covered by automated tests.

## Authentication Audit Logging

- Authentication and password-recovery endpoints emit structured JSON audit events through the `app.auth` and `app.users.audit` loggers. The payloads include the `event` name, a stringified `user_id` when known, the caller IP (`ip`) when available, and the current request correlation identifier (`request_id`). Reasons for success or failure are normalised tokens such as `authenticated`, `invalid_credentials`, `token_expired`, etc.
- Logs inherit the JSON formatter defined in [`app/core/observability.py`](root/app/core/observability.py), so downstream consumers can parse them without regexes. Example pipelines include shipping stdout to your SIEM or subscribing to the OTLP stream when observability exporters are enabled.
- Sensitive fields (passwords, reset tokens, email addresses) are never included. If additional context is required for an investigation, correlate by `request_id` or session identifiers rather than augmenting the log payloads with PII.
- Operators should alert on high volumes of `auth.login.failure` or `password.reset.failed` events from a single IP, and reconcile `auth.logout.revoked` events with expected device revocations to detect account takeovers.

## Multi-factor Authentication Management

- Disabling an individual MFA factor now triggers an automatic refresh of the user's MFA preferences. If other confirmed TOTP enrollments remain, the default factor stays on an active authenticator; otherwise the platform clears `mfa_default_method` and temporarily turns off MFA until another authenticator is added.
- When the last interactive factor is removed, the platform clears `mfa_default_method` and turns off the `mfa_required` flag to prevent users from being locked in an MFA loop on their next login.
- Administrators should advise users that removing every factor effectively disables MFA until a new authenticator app is added.

## HTTP Security Headers & Browser Hardening

Our FastAPI middleware enables a strict set of transport and browser security headers in production:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` – enables one year of HSTS for all subdomains and opts into the Chromium preload list so browsers remember to use HTTPS.
- `Content-Security-Policy` denies inline script execution by default and issues a per-response nonce for any inline scripts that must run (`script-src 'self' 'nonce-…'`). The policy further blocks framing (`frame-ancestors 'none'`), upgrades legacy HTTP links (`upgrade-insecure-requests`), and limits images to our origin plus `data:` URLs to support avatar uploads and QR codes without relaxing the whole policy.
- `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` isolate browsing contexts to mitigate cross-origin data leaks (Spectre, XS-Leaks). If future features require cross-origin embeddings (e.g., Spotify or Telegram previews), they must be proxied or explicitly opted in via dedicated endpoints; the default policy forbids direct third-party frames.
- Existing headers remain in place: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Permissions-Policy: geolocation=(), microphone=(), camera=()`.

Cross-Origin Resource Sharing (CORS) is also tightened: wildcard origins are rejected, non-local HTTP origins are ignored in strict mode, and cookies/credentials are only permitted for HTTPS origins or localhost during development/testing. Configure additional trusted origins via `FRONTEND_ORIGINS` if external dashboards need access.

## Push Subscription Hygiene

- VAPID `subject` **must** be configured as a valid `mailto:` address or HTTPS URL. Invalid values will raise a configuration error at startup; use `VAPID_SUBJECT=mailto:security@example.com` (or an HTTPS URL under your control) in production. Plain HTTP origins are only accepted for local development hosts (`localhost`, `127.0.0.1`).
- Subscription identifiers are masked in logs and cryptographic keys are never logged to avoid leaking Web Push credentials.
- To revoke all push subscriptions for a user (e.g., during account deletion or in response to a compromise):
  1. Authenticate as an administrator.
  2. Call `POST /push/admin/disable-user` with the target `user_id`. The endpoint removes every `PushSubscription` row for that account and returns the number of deleted entries.
  3. Confirm the user no longer has active subscriptions before finalising account removal.

## Notification Retention

- Read notifications are purged automatically after **90 days** by default. Unread notifications are preserved regardless of age so users can review unseen alerts.
- The cleanup job runs on a dedicated background scheduler; tune its cadence with `NOTIFICATIONS_RETENTION_CLEANUP_INTERVAL_SECONDS` (defaults to 86,400 seconds / 24 hours).
- Set `NOTIFICATIONS_RETENTION_DAYS=0` to disable automatic notification retention if your policy mandates manual review before deletion.

## Frontend Profile Cache Hardening

- The React auth context now persists a **versioned, minimal snapshot** of the authenticated user. Only the fields required for optimistic UI (currently the numeric `id`, `full_name`, and `avatar_url`) are written to `localStorage`.
- Snapshots are wrapped in a short-lived envelope (five-minute TTL) and include a deterministic signature so tampering can be detected even if the data is replayed across tabs.
- Whenever a schema version bump is detected—or when a logout/device revocation event fires—the cache is purged before the next render. Future additions default to server fetches unless they are explicitly whitelisted, reducing the blast radius of cached sensitive data.
- Each authenticated session receives a random signing key that lives on the server-side `ActiveSession` record. The frontend only caches the key in `sessionStorage` so a full tab closure destroys the client copy.
- Profile snapshots are signed with HMAC-SHA256 using that session key. The backend refuses `/users/me` requests that present forged envelopes and rotates the signing key whenever a logout revokes the session, preventing replay of stale signatures.
