import assert from "node:assert/strict"
import { randomBytes } from "node:crypto"
import { readFile } from "node:fs/promises"
import test from "node:test"

test("live admin fixture requires a runtime password and has no static admin fallback", async () => {
  const fixture = await readFile(new URL("../tests/e2e-live/fixtures.ts", import.meta.url), "utf8")
  const adminRole = fixture.match(/admin:\s*\{[^}]*\}/su)?.[0]
  assert.ok(adminRole, "the live admin role must remain defined")
  assert.match(adminRole, /password:\s*requireLiveAdminPassword\(\)/u)
  assert.doesNotMatch(adminRole, /password:\s*["']/u)
})

test("live admin password resolver fails closed when TEST_PASSWORD is missing or blank", async () => {
  const { requireLiveAdminPassword } = await import("./live-e2e-credentials.mjs")
  assert.throws(() => requireLiveAdminPassword({}), /TEST_PASSWORD/u)
  assert.throws(() => requireLiveAdminPassword({ TEST_PASSWORD: " \t " }), /TEST_PASSWORD/u)

  const runtimePassword = `${randomBytes(32).toString("base64url")}!Aa0`
  if (requireLiveAdminPassword({ TEST_PASSWORD: runtimePassword }) !== runtimePassword) {
    assert.fail("the live fixture must preserve the caller's per-run password")
  }
})

test("live Playwright disables reports and attachments that could retain credentials", async () => {
  const config = await readFile(new URL("../playwright.live.config.ts", import.meta.url), "utf8")
  assert.match(config, /reporter:\s*["']list["']/u)
  assert.doesNotMatch(config, /["']html["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(config, /outputDir:\s*process\.env\.LIVE_E2E_OUTPUT_DIR/u)

  for (const file of [
    "../tests/e2e-live/auth-roles.live.spec.ts",
    "../tests/e2e-live/password-reset.live.spec.ts",
  ]) {
    const spec = await readFile(new URL(file, import.meta.url), "utf8")
    assert.doesNotMatch(spec, /trace:\s*["'](?:on|retain-on-failure)["']/u)
    assert.doesNotMatch(spec, /screenshot:\s*["']only-on-failure["']/u)
  }
})
