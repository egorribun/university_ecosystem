import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"

const staticSsrRoutes = [
  ["Dashboard", "dashboard"],
  ["News", "news.index"],
  ["NewsDetail", "news.$id"],
  ["Events", "events.index"],
  ["EventDetail", "events.$id"],
  ["Schedule", "schedule"],
  ["Profile", "profile"],
]

function assertStaticSsrBoundary(pageName, routeSource, parentSource) {
  assert.match(parentSource, /^\s*ssr:\s*true\b/mu)
  assert.match(routeSource, /^\s*ssr:\s*true\b/mu)
  assert.doesNotMatch(routeSource, /^\s*ssr:\s*(?!true\b)\S/mu)
  assert.ok(routeSource.split("\n").includes(`import ${pageName} from "@/pages/${pageName}"`))
  assert.doesNotMatch(routeSource, /\blazy\s*\(/u)
}

// Keep the reviewed bundle analyzer tests byte-exact. These route-specific
// guards retain the full-SSR hydration constraints without dynamic regexes.
test("keeps static SSR page imports and explicit full SSR boundaries", async () => {
  const parent = await readFile(new URL("../src/routes/_auth.tsx", import.meta.url), "utf8")
  for (const [pageName, routeName] of staticSsrRoutes) {
    const source = await readFile(
      new URL(`../src/routes/_auth/${routeName}.tsx`, import.meta.url),
      "utf8"
    )
    assertStaticSsrBoundary(pageName, source, parent)
  }
})

test("rejects restricted SSR and nested lazy hydration boundaries", () => {
  const parent = "  ssr: true,"
  const source = 'import News from "@/pages/News"\n  ssr: true,'
  assert.doesNotThrow(() => assertStaticSsrBoundary("News", source, parent))
  for (const restriction of ["false", '"data-only"']) {
    assert.throws(() => assertStaticSsrBoundary("News", source, `  ssr: ${restriction},`))
    assert.throws(() =>
      assertStaticSsrBoundary("News", source.replace("ssr: true", `ssr: ${restriction}`), parent)
    )
  }
  assert.throws(() => assertStaticSsrBoundary("News", source.replace("  ssr: true,", ""), parent))
  assert.throws(() =>
    assertStaticSsrBoundary(
      "News",
      'const News = lazy(() => import("@/pages/News"))\n  ssr: true,',
      parent
    )
  )
  assert.throws(() =>
    assertStaticSsrBoundary(
      "News",
      `${source}\nconst Nested = lazy(() => import("./Nested"))`,
      parent
    )
  )
})

const lazyRoutes = [
  ["Activity", "_auth/activity"],
  ["Map", "_auth/map"],
  ["Messenger", "_auth/messenger"],
  ["Settings", "_auth/settings"],
  ["Login", "_public/login"],
  ["Register", "_public/register"],
  ["ForgotPassword", "_public/forgot-password"],
  ["ResetPassword", "_public/reset-password"],
  ["AdminUsers", "_admin/admin.users"],
  ["AdminAudit", "_admin/admin.audit"],
  ["AdminFeatureFlags", "_admin/admin.feature-flags"],
  ["AdminNotifications", "_admin/admin.notifications"],
  ["StoriesAdmin", "_admin/admin.stories"],
]

function assertLazyBoundary(pageName, source) {
  assert.ok(source.includes(`lazy(() => import("@/pages/${pageName}"))`))
  assert.ok(
    !source
      .split("\n")
      .some((line) => line.startsWith("import ") && line.includes(` from "@/pages/${pageName}"`))
  )
}

test("keeps all other feature pages behind their existing lazy boundaries", async () => {
  for (const [pageName, routeName] of lazyRoutes) {
    const source = await readFile(
      new URL(`../src/routes/${routeName}.tsx`, import.meta.url),
      "utf8"
    )
    assertLazyBoundary(pageName, source)
  }
  const source = 'const Settings = lazy(() => import("@/pages/Settings"))'
  assert.doesNotThrow(() => assertLazyBoundary("Settings", source))
  assert.throws(() => assertLazyBoundary("Settings", 'import Settings from "@/pages/Settings"'))
  assert.throws(() =>
    assertLazyBoundary("Settings", `${source}\nimport Settings from "@/pages/Settings"`)
  )
})
