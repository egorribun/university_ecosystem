import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./admin-audit-rbac.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const roleFixturesUrl = new URL("./fixtures.ts", import.meta.url)
const adminRouteUrl = new URL("../../src/routes/_admin/admin.audit.tsx", import.meta.url)
const adminQueryUrl = new URL("../../src/api/hooks/adminAudit.ts", import.meta.url)
const backendRouteUrl = new URL("../../../app/api/admin/audit.py", import.meta.url)

const [spec, config, roleFixtures, adminRoute, adminQuery, backendRoute] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(roleFixturesUrl, "utf8"),
  readFile(adminRouteUrl, "utf8"),
  readFile(adminQueryUrl, "utf8"),
  readFile(backendRouteUrl, "utf8"),
])

test("live audit RBAC covers a real admin route with seeded student and teacher roles", () => {
  assert.match(spec, /await loginAs\(page, "admin"\)/u)
  assert.match(spec, /page\.goto\("\/admin\/audit"\)/u)
  assert.match(spec, /GET \/api\/v1\/admin\/audit should be allowed[\s\S]*?\.toBe\(200\)/u)
  assert.match(spec, /for \(const role of \["student", "teacher"\] as const\)/u)
  assert.match(spec, /await loginAs\(page, role\)/u)
  assert.match(spec, /redirected from \/admin\/audit[\s\S]*?\/dashboard/u)
  assert.match(spec, /GET \/api\/v1\/admin\/audit status[\s\S]*?\.toBe\(403\)/u)
  assert.match(roleFixtures, /student:\s*\{/u)
  assert.match(roleFixtures, /teacher:\s*\{/u)
  assert.match(roleFixtures, /admin:\s*\{/u)

  assert.match(adminRoute, /createFileRoute\("\/_admin\/admin\/audit"\)/u)
  assert.match(adminQuery, /api\.get<AuditLogList>\("\/admin\/audit"/u)
  assert.match(backendRoute, /Depends\(get_current_admin_user_from_dishka\)/u)
  assert.doesNotMatch(spec, /\b(?:vi\.mock|server\.use|page\.route|routeWebSocket)\b/u)
  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
})
