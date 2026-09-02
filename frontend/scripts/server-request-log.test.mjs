import assert from "node:assert/strict"
import test from "node:test"

import { sanitizeRequestTarget } from "./server-request-log.mjs"

test("access-log target strips query and fragment credentials", () => {
  const raw = "/oauth/callback?code=oauth-secret&state=csrf-secret#fragment-secret"
  const safe = sanitizeRequestTarget(raw)

  assert.equal(safe, "/oauth/callback")
  for (const secret of ["oauth-secret", "csrf-secret", "fragment-secret"]) {
    assert.equal(safe.includes(secret), false)
  }
})

test("access-log target redacts password-reset bearer tokens", () => {
  const rawToken = "reset-token-that-must-never-reach-loki"
  const safe = sanitizeRequestTarget(`/reset-password/${rawToken}?lang=ru`)

  assert.equal(safe, "/reset-password/[REDACTED]")
  assert.equal(safe.includes(rawToken), false)
})

test("access-log target preserves ordinary route diagnostics", () => {
  assert.equal(sanitizeRequestTarget("/dashboard"), "/dashboard")
  assert.equal(sanitizeRequestTarget(undefined), "/")
})
