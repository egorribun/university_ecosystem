import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { requireLiveAdminPassword, resolveLiveRolePassword } from "./live-e2e-credentials.mjs"

const fixtureUrl = new URL("../tests/e2e-live/fixtures.ts", import.meta.url)
const redirectSpecUrl = new URL(
  "../tests/e2e-live/auth-safe-redirect.live.spec.ts",
  import.meta.url
)
const fallbackPassword = randomUUID()
const ownerPassword = randomUUID()

test("owned student login selects the per-run seeded password without exposing it", () => {
  const actualMatchesRuntime =
    resolveLiveRolePassword("student", fallbackPassword, true, {
      TEST_PASSWORD: ownerPassword,
    }) === ownerPassword
  assert.equal(actualMatchesRuntime, true)
})

test("standalone student and seeded teacher preserve their fallback passwords", () => {
  const standaloneStudentMatchesFallback =
    resolveLiveRolePassword("student", fallbackPassword, false, {
      TEST_PASSWORD: ownerPassword,
    }) === fallbackPassword
  const ownedTeacherMatchesFallback =
    resolveLiveRolePassword("teacher", fallbackPassword, true, {
      TEST_PASSWORD: ownerPassword,
    }) === fallbackPassword
  assert.equal(standaloneStudentMatchesFallback, true)
  assert.equal(ownedTeacherMatchesFallback, true)
})

test("owned student resolution fails closed for missing or blank injected passwords", () => {
  assert.throws(
    () => resolveLiveRolePassword("student", fallbackPassword, true, {}),
    /TEST_PASSWORD/u
  )
  assert.throws(
    () =>
      resolveLiveRolePassword("student", fallbackPassword, true, {
        TEST_PASSWORD: " \t ",
      }),
    /TEST_PASSWORD/u
  )
})

test("admin runtime-password contract remains unchanged", () => {
  const adminMatchesInjectedPassword =
    requireLiveAdminPassword({ TEST_PASSWORD: ownerPassword }) === ownerPassword
  assert.equal(adminMatchesInjectedPassword, true)
  assert.throws(() => requireLiveAdminPassword({}), /TEST_PASSWORD/u)
})

test("fixture uses owner scope for role resolution and retains the standalone student fallback", async () => {
  const fixture = await readFile(fixtureUrl, "utf8")
  assert.match(
    fixture,
    /export function loginPasswordForRole\(role: Role\): string \{\s*return resolveLiveRolePassword\(\s*role,\s*ROLES\[role\]\.password,\s*activeOwnedSessionScope !== undefined,?\s*\)\s*\}/u,
    "the student resolver must use the fallback only outside owned-session scope"
  )
  assert.match(fixture, /student:\s*\{\s*email:\s*"[^"]+",\s*password:\s*"[^"]+",/u)
  assert.match(fixture, /ROLES\[role\]\.email,\s*loginPasswordForRole\(role\),/u)
  assert.match(fixture, /admin:\s*\{[^}]*password:\s*requireLiveAdminPassword\(\)/su)
})

test("the direct redirect-login flow uses the same owned student password resolver", async () => {
  const redirectSpec = await readFile(redirectSpecUrl, "utf8")
  assert.match(redirectSpec, /import \{[^}]*loginPasswordForRole[^}]*\} from "\.\/fixtures"/u)
  assert.match(redirectSpec, /fill\(loginPasswordForRole\("student"\)\)/u)
  assert.doesNotMatch(redirectSpec, /ROLES\.student\.password/u)
})
