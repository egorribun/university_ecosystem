import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./admin-feature-flags-rbac.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const adminRouteUrl = new URL("../../src/routes/_admin/admin.feature-flags.tsx", import.meta.url)
const adminLayoutUrl = new URL("../../src/routes/_admin.tsx", import.meta.url)
const adminGuardUrl = new URL("../../src/routes/guards.ts", import.meta.url)
const featureFlagHookUrl = new URL("../../src/api/hooks/adminFeatureFlags.ts", import.meta.url)
const backendRouteUrl = new URL("../../../app/api/admin/feature_flags.py", import.meta.url)
const backendRouterUrl = new URL("../../../app/api/admin/__init__.py", import.meta.url)

test("live feature-flag RBAC coverage uses real role sessions and is discoverable", async () => {
  const spec = await readFile(specUrl, "utf8").catch(() => null)
  assert.ok(spec, "the focused feature-flag RBAC live spec must exist")
  const config = await readFile(configUrl, "utf8")

  assert.ok(
    spec.includes("admin can access feature-flag diagnostics"),
    "the live suite must verify the admin feature-flag page"
  )
  assert.ok(
    spec.includes('await loginAs(page, "admin")'),
    "the admin page check must authenticate through the real seeded fixture"
  )
  assert.ok(
    spec.includes('for (const role of ["student", "teacher"] as const)') &&
      spec.includes("is denied access to feature-flag diagnostics") &&
      /featureFlags\.status\(\),\s*`\$\{role\} GET \/api\/v1\/admin\/feature-flags status`\)\.toBe\(403\)/u.test(
        spec
      ),
    "student and teacher must both be denied at the feature-flag page and endpoint"
  )
  assert.ok(
    /for \(const role of \["student", "teacher"\] as const\)[\s\S]*?const rejectedWrite = await page\.evaluate/u.test(
      spec
    ) &&
      spec.includes("const rejectedWrite = await page.evaluate(async () => {") &&
      spec.includes('"/api/v1/admin/feature-flags/rbac-probe-no-such-flag"') &&
      spec.includes('method: "PATCH"') &&
      spec.includes('"X-CSRF-Token": csrfToken') &&
      spec.includes("return response.status") &&
      /rejectedWrite,[\s\S]*?\.toBe\(403\)/u.test(spec),
    "student and teacher must be denied by the real API on the legacy PATCH route with valid CSRF and a synthetic target"
  )
  assert.ok(
    spec.includes('"/api/v1/admin/feature-flags"') &&
      /featureFlags\.status\(\),\s*"admin GET \/api\/v1\/admin\/feature-flags should be allowed"\s*\)\.toBe\(\s*200\s*\)/u.test(
        spec
      ),
    "the protected backend endpoint must be checked without an authorization mock"
  )
  assert.ok(
    !/\b(?:vi\.mock|server\.use|page\.route|routeWebSocket)\b/u.test(spec),
    "live role authorization must not be mocked"
  )
  assert.ok(
    config.includes('testDir: "./tests/e2e-live"') &&
      /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u.test(config),
    "Playwright must discover this live spec through its existing pattern"
  )
})

test("feature-flag diagnostics remain admin-only and read-only across UI and API routes", async () => {
  const [adminRoute, adminLayout, adminGuard, featureFlagHook, backendRoute, backendRouter] =
    await Promise.all([
      readFile(adminRouteUrl, "utf8"),
      readFile(adminLayoutUrl, "utf8"),
      readFile(adminGuardUrl, "utf8"),
      readFile(featureFlagHookUrl, "utf8"),
      readFile(backendRouteUrl, "utf8"),
      readFile(backendRouterUrl, "utf8"),
    ])

  assert.match(adminRoute, /createFileRoute\("\/_admin\/admin\/feature-flags"\)/u)
  assert.match(
    adminLayout,
    /beforeLoad:\s*\(\{\s*context\s*\}\)\s*=>\s*evaluateAdminGuard\(\s*import\.meta\.env\.SSR\s*\?\s*\{\s*user:\s*context\.auth\.isAuth\s*\?\s*context\.auth\.user\s*:\s*null,\s*loading:\s*context\.auth\.loading,\s*\}\s*:\s*useAuthStore\.getState\(\)\s*\)/u
  )
  assert.match(adminGuard, /return state\.user\.role === "admin" \? null : "\/dashboard"/u)
  assert.match(featureFlagHook, /api\.get<FeatureFlag\[\]>\("\/admin\/feature-flags"/u)
  assert.match(backendRoute, /@router\.get\("",\s*response_model=/u)
  assert.match(backendRoute, /Depends\(get_current_admin_user_from_dishka\)/u)
  assert.match(backendRoute, /return list_feature_flag_snapshots\(\)/u)
  assert.match(backendRouter, /include_router\(feature_flags_router\)/u)
  assert.match(backendRoute, /@router\.patch\("\/\{name\}", include_in_schema=False\)/u)
  assert.match(backendRoute, /status_code=status\.HTTP_405_METHOD_NOT_ALLOWED/u)
})
