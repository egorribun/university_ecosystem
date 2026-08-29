import assert from "node:assert/strict"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { test } from "node:test"

import {
  BUNDLE_BUDGETS,
  analyzeBundle,
  assertBundleBudgets,
  normalizeAssetPath,
} from "./check-bundle-budget.mjs"

const dictionaryChunkPath = "client/assets/vendor-password-strength-en-ABC.js"

const routeStyleBoundaries = [
  ["Dashboard", "dashboard", "_auth/dashboard.tsx"],
  ["News", "news", "_auth/news.index.tsx"],
  ["NewsDetail", "news", "_auth/news.$id.tsx"],
  ["Events", "events", "_auth/events.index.tsx"],
  ["EventDetail", "events", "_auth/events.$id.tsx"],
  ["Schedule", "schedule", "_auth/schedule.tsx"],
  ["Activity", "activity", "_auth/activity.tsx"],
  ["Map", "map", "_auth/map.tsx"],
  ["Messenger", "messenger", "_auth/messenger.tsx"],
  ["Profile", "profile", "_auth/profile.tsx"],
  ["Settings", "settings", "_auth/settings.tsx"],
  ["Login", "auth", "_public/login.tsx"],
  ["Register", "auth", "_public/register.tsx"],
  ["ForgotPassword", "auth", "_public/forgot-password.tsx"],
  ["ResetPassword", "auth", "_public/reset-password.tsx"],
  ["AdminUsers", "admin", "_admin/admin.users.tsx"],
  ["AdminAudit", "admin", "_admin/admin.audit.tsx"],
  ["AdminFeatureFlags", "admin", "_admin/admin.feature-flags.tsx"],
  ["AdminNotifications", "admin", "_admin/admin.notifications.tsx"],
  ["StoriesAdmin", "admin", "_admin/admin.stories.tsx"],
]

async function createBundleFixture({ mainBytes = 16, lazyBytes = 16, initialCssBytes } = {}) {
  const distDir = await mkdtemp(path.join(tmpdir(), "bundle-budget-test-"))
  const assetsDir = path.join(distDir, "client", "assets")
  await mkdir(assetsDir, { recursive: true })
  await writeFile(
    path.join(distDir, "client", "index.html"),
    [
      '<link rel="modulepreload" href="/assets/vendor-react-ABC.js">',
      ...(initialCssBytes === undefined
        ? []
        : ['<link rel="stylesheet" href="/assets/index-ABC.css">']),
      '<script type="module" src="/assets/index-ABC.js"></script>',
    ].join("\n")
  )
  await writeFile(path.join(assetsDir, "index-ABC.js"), Buffer.alloc(mainBytes, 97))
  await writeFile(path.join(assetsDir, "vendor-react-ABC.js"), Buffer.alloc(32, 98))
  await writeFile(path.join(assetsDir, "Feature-ABC.js"), Buffer.alloc(lazyBytes, 99))
  if (initialCssBytes !== undefined) {
    await writeFile(path.join(assetsDir, "index-ABC.css"), Buffer.alloc(initialCssBytes, 100))
  }
  return distDir
}

test("normalizes Windows asset paths before classifying chunks", () => {
  assert.equal(normalizeAssetPath("client\\assets\\index-ABC.js"), "client/assets/index-ABC.js")
})

test("locks baseline-aware initial and general lazy ratchets", () => {
  assert.equal(BUNDLE_BUDGETS.initialJsGzipKb, 420)
  assert.equal(BUNDLE_BUDGETS.generalLazyJsGzipKb, 280)
  assert.equal(BUNDLE_BUDGETS.passwordDictionaryRawKb, 1250)
})

test("keeps feature token CSS inside the matching lazy route boundary", async () => {
  const themeSource = await readFile(new URL("../src/styles/theme.css", import.meta.url), "utf8")

  assert.doesNotMatch(
    themeSource,
    /@import "\.\/tokens\/(?:dashboard|news|events|schedule|activity|map|admin|messenger|profile|settings|auth)\.css"/u
  )

  await Promise.all(
    routeStyleBoundaries.map(async ([pageName, tokenName, routePath]) => {
      const [pageSource, routeSource] = await Promise.all([
        readFile(new URL(`../src/pages/${pageName}.tsx`, import.meta.url), "utf8"),
        readFile(new URL(`../src/routes/${routePath}`, import.meta.url), "utf8"),
      ])

      assert.match(pageSource, new RegExp(`import "@/styles/tokens/${tokenName}\\.css"`))

      // Routes that explicitly opt into SSR must keep their page in the
      // server entry graph. Requiring a lazy import for every route made the
      // contract reject the dashboard's intentional SSR boundary and caused
      // bundle analysis to fail before it could inspect the actual artifact.
      // Non-SSR routes remain lazy so their feature chunks stay out of the
      // initial delivery graph.
      if (/^\s*ssr:\s*true\b/mu.test(routeSource)) {
        assert.match(routeSource, new RegExp(`import ${pageName} from "@/pages/${pageName}"`))
      } else {
        assert.match(
          routeSource,
          new RegExp(`lazy\\(\\(\\) => import\\("@/pages/${pageName}"\\)\\)`)
        )
      }
    })
  )
})

test("reports the real HTML preload graph and writes useful JSON", async () => {
  const distDir = await createBundleFixture()
  try {
    const report = await analyzeBundle(distDir, { commitSha: "abc123" })

    assert.equal(report.schemaVersion, 1)
    assert.equal(report.commitSha, "abc123")
    assert.equal(report.summary.mainJsRawBytes, 16)
    assert.equal(report.summary.initialJsAssetCount, 2)
    assert.equal(report.summary.lazyJsAssetCount, 1)
    assert.equal(report.summary.initialCssAssetCount, 0)
    assert.equal(report.summary.initialCssGzipBytes, 0)
    assert.deepEqual(
      report.assets
        .filter((asset) => asset.isInitial)
        .map((asset) => asset.path)
        .sort(),
      ["client/assets/index-ABC.js", "client/assets/vendor-react-ABC.js"]
    )

    const serialized = JSON.parse(JSON.stringify(report))
    assert.equal(serialized.budgets.mainJsRawKb, 500)
    assert.ok(serialized.assets.every((asset) => asset.rawBytes > 0))
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("reports stylesheets in the initial delivery graph", async () => {
  const distDir = await createBundleFixture({ initialCssBytes: 24 })
  try {
    const report = await analyzeBundle(distDir)

    assert.equal(report.summary.initialCssAssetCount, 1)
    assert.ok(report.summary.initialCssGzipBytes > 0)
    assert.deepEqual(
      report.assets
        .filter((asset) => asset.type === "stylesheet" && asset.isInitial)
        .map((asset) => asset.path),
      ["client/assets/index-ABC.css"]
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("keeps server-rendering artifacts out of browser chunk budgets", async () => {
  const distDir = await createBundleFixture()
  try {
    const serverAssets = path.join(distDir, "server", "assets")
    await mkdir(serverAssets, { recursive: true })
    await writeFile(path.join(serverAssets, "server-entry-ABC.js"), Buffer.alloc(64, 100))

    const report = await analyzeBundle(distDir)

    assert.ok(report.assets.every((asset) => asset.path.startsWith("client/")))
    assert.equal(
      report.assets.some((asset) => asset.path.includes("server-entry")),
      false
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("fails closed when the main raw chunk exceeds 500 KiB", async () => {
  const distDir = await createBundleFixture({ mainBytes: BUNDLE_BUDGETS.mainJsRawKb * 1024 + 1 })
  try {
    const report = await analyzeBundle(distDir)
    assert.throws(
      () => assertBundleBudgets(report),
      /Main JS chunk .* exceeds raw budget: 500\.00 KiB > 500 KiB/
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("fails closed when the initial preload graph exceeds its compressed ratchet", async () => {
  const report = {
    assets: [],
    summary: {
      mainJsRawBytes: 1,
      mainJsPath: "client/assets/index-ABC.js",
      initialJsGzipBytes: BUNDLE_BUDGETS.initialJsGzipKb * 1024 + 1,
      largestGeneralLazyJsGzipBytes: 1,
      largestGeneralLazyJsPath: "client/assets/Feature-ABC.js",
      largestPasswordDictionaryGzipBytes: 1,
      largestPasswordDictionaryRawBytes: 1,
      largestPasswordDictionaryPath: dictionaryChunkPath,
    },
  }

  assert.throws(() => assertBundleBudgets(report), /Initial JS preload graph exceeds gzip budget/)
})

test("fails closed when the initial stylesheet delivery graph exceeds its compressed ratchet", () => {
  const report = {
    assets: [],
    summary: {
      mainJsRawBytes: 1,
      mainJsPath: "client/assets/index-ABC.js",
      initialJsGzipBytes: 1,
      initialCssGzipBytes: BUNDLE_BUDGETS.initialCssGzipKb * 1024 + 1,
      largestGeneralLazyJsGzipBytes: 1,
      largestGeneralLazyJsPath: "client/assets/Feature-ABC.js",
      largestPasswordDictionaryGzipBytes: 1,
      largestPasswordDictionaryRawBytes: 1,
      largestPasswordDictionaryPath: dictionaryChunkPath,
    },
  }

  assert.throws(() => assertBundleBudgets(report), /Initial CSS delivery graph exceeds gzip budget/)
})

test("keeps a bounded exception for lazy password dictionaries", () => {
  const report = {
    assets: [],
    summary: {
      mainJsRawBytes: 1,
      mainJsPath: "client/assets/index-ABC.js",
      initialJsGzipBytes: 1,
      largestGeneralLazyJsGzipBytes: BUNDLE_BUDGETS.generalLazyJsGzipKb * 1024,
      largestGeneralLazyJsPath: "client/assets/Feature-ABC.js",
      largestPasswordDictionaryGzipBytes: BUNDLE_BUDGETS.passwordDictionaryGzipKb * 1024,
      largestPasswordDictionaryRawBytes: BUNDLE_BUDGETS.passwordDictionaryRawKb * 1024,
      largestPasswordDictionaryPath: dictionaryChunkPath,
    },
  }

  assert.doesNotThrow(() => assertBundleBudgets(report))
})

test("fails closed when an interactive password dictionary exceeds its raw ceiling", () => {
  const report = {
    assets: [],
    summary: {
      mainJsRawBytes: 1,
      mainJsPath: "client/assets/index-ABC.js",
      initialJsGzipBytes: 1,
      largestGeneralLazyJsGzipBytes: 1,
      largestGeneralLazyJsPath: "client/assets/Feature-ABC.js",
      largestPasswordDictionaryRawBytes: BUNDLE_BUDGETS.passwordDictionaryRawKb * 1024 + 1,
      largestPasswordDictionaryGzipBytes: 1,
      largestPasswordDictionaryPath: dictionaryChunkPath,
    },
  }

  assert.throws(() => assertBundleBudgets(report), /Password dictionary .* exceeds raw budget/u)
})

test("the checked-in analyzer remains directly executable", async () => {
  const source = await readFile(new URL("./check-bundle-budget.mjs", import.meta.url), "utf8")
  assert.match(source, /import\.meta\.url/)
  assert.match(source, /bundle-report\.json/)
})

test("Vite chunk warnings use the largest machine-enforced raw chunk budget", async () => {
  const source = await readFile(new URL("../vite.config.mts", import.meta.url), "utf8")

  assert.match(source, /chunkSizeWarningLimit:\s*BUNDLE_BUDGETS\.passwordDictionaryRawKb/u)
  assert.doesNotMatch(source, /chunkSizeWarningLimit:\s*\d+/u)
})
