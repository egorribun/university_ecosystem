import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./auth-login-lockout.live.spec.ts", import.meta.url)
const lockoutSettingsUrl = new URL(
  "../../../app/core/config/mixins/rate_limit_settings.py",
  import.meta.url
)
const liveComposeUrl = new URL("../../../docker-compose.live.yml", import.meta.url)
const routeLimiterUrl = new URL("../../../app/core/ratelimit/fastapi.py", import.meta.url)
const middlewareLimiterUrl = new URL("../../../app/core/ratelimit/middleware.py", import.meta.url)

const requireMatch = (source, pattern, message) => assert.ok(pattern.test(source), message)
const requireNoMatch = (source, pattern, message) => assert.ok(!pattern.test(source), message)

test("Auth lockout live acceptance isolates a synthetic identity and preserves lockout semantics", async () => {
  const [spec, settings, liveCompose, routeLimiter, middlewareLimiter] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(lockoutSettingsUrl, "utf8"),
    readFile(liveComposeUrl, "utf8"),
    readFile(routeLimiterUrl, "utf8"),
    readFile(middlewareLimiterUrl, "utf8"),
  ])

  requireMatch(
    settings,
    /auth_lockout_thresholds:\s*str\s*\|\s*list\[str\]\s*=\s*"5:30/u,
    "the live attempt count must track the configured first lockout threshold"
  )
  requireMatch(liveCompose, /RATE_LIMIT_AUTH_LOGIN:\s*"60\/minute"/u, "live login limit changed")
  requireMatch(
    routeLimiter,
    /user_id\s*=\s*extract_user_id_for_ratelimit\(request\)/u,
    "authenticated rate-limit identity extraction changed"
  )
  requireMatch(
    routeLimiter,
    /if user_id:\s*key\s*=\s*f"\{key_prefix\}:user:\{user_id\}:/u,
    "authenticated route limiting must remain user-scoped"
  )
  requireMatch(
    middlewareLimiter,
    /request\.cookies\.get\(\s*"access_token_v2"\s*\)/u,
    "middleware must retain the authenticated cookie-based limiter key"
  )

  requireMatch(
    spec,
    /synthetic account reaches account lockout/u,
    "synthetic lockout scenario missing"
  )
  requireMatch(
    spec,
    /const email = `live-auth-lockout-\$\{randomUUID\(\)\}@university\.dev`/u,
    "the target email must be unique to this run"
  )
  requireMatch(spec, /loginAs\(adminPage, "admin"\)/u, "test-owned account setup is missing")
  requireMatch(spec, /fetch\("\/api\/v1\/users"/u, "test-owned account setup must use the real API")
  requireMatch(spec, /role: "student"/u, "test target must be a synthetic student account")
  requireMatch(
    spec,
    /await submitLogin\(page, email, wrongPassword\)/u,
    "real UI login attempt missing"
  )
  requireMatch(
    spec,
    /uiFailureResponse\.status\(.*?\)\.toBe\(401\)/u,
    "wrong password must return 401"
  )
  requireMatch(
    spec,
    /await loginWith\(page, email, password\)/u,
    "synthetic user success login missing"
  )
  requireMatch(
    spec,
    /identityResponse\.json\(\)\)\.id\)\.toBe\(createdUserId\)/u,
    "the authenticated browser must belong to the created synthetic account"
  )
  requireMatch(
    spec,
    /cookie\.name === "access_token_v2"/u,
    "synthetic account session cookie missing"
  )

  requireMatch(
    spec,
    /const LOCKOUT_ATTEMPTS = 5/u,
    "failed attempt count must match configured threshold"
  )
  requireMatch(
    spec,
    /page\.request\.post\("\/api\/v1\/auth\/login"/u,
    "real login API attempts missing"
  )
  requireMatch(spec, /\.toBe\(\s*423\s*\)/u, "account lockout must retain HTTP 423 semantics")
  requireMatch(
    spec,
    /response\.headers\(\)\["retry-after"\]/u,
    "lockout cooldown header must be asserted"
  )
  requireMatch(
    spec,
    /retryAfter <= 30/u,
    "asserted cooldown must respect the configured 30-second first threshold"
  )

  requireMatch(
    spec,
    /if \(createdUserId\) await deleteOwnedAccount\(adminPage, createdUserId\)/u,
    "cleanup must be bounded to the created account id"
  )
  requireMatch(spec, /"X-CSRF-Token"/u, "account cleanup must include CSRF protection")
  requireNoMatch(spec, /\/auth\/register/u, "registration would consume a shared rate-limited path")
  requireNoMatch(
    spec,
    /page\.route\(|route\.fulfill\(/u,
    "the live auth endpoints must not be mocked"
  )
  requireNoMatch(
    spec,
    /loginAs\(page,\s*"(?:student|teacher|admin)"/u,
    "the lockout target must not be a seeded role"
  )
})
