# Security Policy

## Supported Versions
We actively maintain and provide security updates for the latest released version of this project. Older versions may no longer receive security fixes, so upgrading to the most recent release is strongly recommended.

## Reporting a Vulnerability
If you discover a vulnerability, please report it privately so we can address it promptly. We aim to acknowledge new reports within 72 hours.

## Dependency Audit Notes

- `npm audit --audit-level=high` (March 2025) currently reports **no outstanding issues** because we force `glob@11.1.0` through `package.json#overrides`. This pulls in the patched release while keeping Tailwind CSS on the stable `3.4.x` train.
- Keep the override until the Tailwind 4 migration lands so that future installs do not regress to the vulnerable `glob` CLI when `sucrase` updates.

### Automated security pipeline

- CI runs `npm audit --audit-level=high` against `root/frontend/package-lock.json` and `pip-audit` against `root/requirements.txt` + `root/requirements-dev.txt`. The jobs **fail** when a new advisory is detected or when a declared override disappears.
- Temporary exceptions live in [`security/audit-allowlist.yaml`](security/audit-allowlist.yaml). Every entry must include an owner and an `expires` date; expired entries fail the pipeline so they cannot silently drift.
- The current allowlist records the `glob@11.1.0` override (owner: `frontend@university.example`, expires: `2025-06-30`) to keep the Tailwind 3.x toolchain on the patched release.

#### Refreshing allowlists and overrides

1. Run `python scripts/audit_dependencies.py --allowlist security/audit-allowlist.yaml --npm root/frontend --pip root/requirements.txt root/requirements-dev.txt` locally. Pip-audit will download advisories; this may take a minute while it builds a virtual environment.
2. If the command reports new advisories, either patch the dependency or add a **temporary** entry to `security/audit-allowlist.yaml` with `owner`, `expires`, `reason`, and (for npm) the pinned override version. Avoid long expirations.
3. Commit both the dependency fix/override and the allowlist change together so CI and developers stay in sync.
4. Remove allowlist entries as soon as upstream releases make the override unnecessary.

## Private Vulnerability Reporting
To report a vulnerability, use the **Security** tab on GitHub and open a new **Private vulnerability report**, or email **security@university.example.com**. Issues are disabled for vulnerability discussions; instead, please submit a GitHub Security Advisory so the team can work with you directly on mitigation and disclosure.

### Response SLA (MOD-W8-03)

| Severity | Acknowledgement | Triage | Fix |
|----------|----------------|--------|-----|
| Critical | 24 hours | 48 hours | 7 days |
| High | 48 hours | 5 days | 30 days |
| Medium | 5 days | 14 days | 90 days |
| Low | 5 days | 30 days | Best-effort |

We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure): findings are kept confidential until a fix is released and deployed to production.

### Scope

**In scope:** Authentication/authorization bypasses, data exposure, injection vulnerabilities (SQLi, XSS, SSRF, command injection), cryptographic weaknesses in token handling or MFA, privilege escalation, denial-of-service via resource exhaustion.

**Out of scope:** Social engineering, physical access attacks, third-party services not under our control, vulnerabilities requiring local network access to unexposed internal ports.

## Password Storage & Policy

- **Algorithm**: We hash passwords with Argon2id via Passlib (Time: 3, Mem: 64MB, Parallelism: 4).
- **Exceptions**: SHA-1 is used *exclusively* for the [Have I Been Pwned API](https://haveibeenpwned.com/API/v3#PwnedPasswords) k-anonymity check. Only the first 5 characters of the hash are transmitted; the full hash is never stored. This usage is intentional and safe.
- **Legacy**: Pre-existing bcrypt hashes are automatically rehashed to Argon2id upon successful login.

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
