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

## HTTP Security Headers & Browser Hardening

Our FastAPI middleware enables a strict set of transport and browser security headers in production:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` – enables one year of HSTS for all subdomains and opts into the Chromium preload list so browsers remember to use HTTPS.
- `Content-Security-Policy` denies inline script execution by default and issues a per-response nonce for any inline scripts that must run (`script-src 'self' 'nonce-…'`). The policy further blocks framing (`frame-ancestors 'none'`), upgrades legacy HTTP links (`upgrade-insecure-requests`), and limits images to our origin plus `data:` URLs to support avatar uploads and QR codes without relaxing the whole policy.
- `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` isolate browsing contexts to mitigate cross-origin data leaks (Spectre, XS-Leaks). If future features require cross-origin embeddings (e.g., Spotify or Telegram previews), they must be proxied or explicitly opted in via dedicated endpoints; the default policy forbids direct third-party frames.
- Existing headers remain in place: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Permissions-Policy: geolocation=(), microphone=(), camera=()`.

Cross-Origin Resource Sharing (CORS) is also tightened: wildcard origins are rejected, non-local HTTP origins are ignored in strict mode, and cookies/credentials are only permitted for HTTPS origins or localhost during development/testing. Configure additional trusted origins via `FRONTEND_ORIGINS` if external dashboards need access.
