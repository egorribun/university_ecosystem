import assert from "node:assert/strict"
import { createHash } from "node:crypto"
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

test("reports direct HTML preload roots and writes useful JSON", async () => {
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

test("classifies uppercase HTML tag names as direct initial assets", async () => {
  const distDir = await createBundleFixture({ initialCssBytes: 24 })
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      [
        '<LINK rel="modulepreload" href="/assets/vendor-react-ABC.js">',
        '<LINK rel="stylesheet" href="/assets/index-ABC.css">',
        '<script type="module" src="/assets/index-ABC.js"></script>',
      ].join("\n")
    )

    const report = await analyzeBundle(distDir)

    assert.equal(report.summary.initialJsAssetCount, 2)
    assert.equal(report.summary.initialCssAssetCount, 1)
    assert.deepEqual(
      report.assets.filter((asset) => asset.isInitial).map((asset) => asset.path),
      [
        "client/assets/index-ABC.css",
        "client/assets/index-ABC.js",
        "client/assets/vendor-react-ABC.js",
      ]
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("classifies unquoted attributes, spacing and relation tokens", async () => {
  const distDir = await createBundleFixture({ initialCssBytes: 24 })
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      [
        '<LINK HREF = /assets/vendor-react-ABC.js REL = "preload modulepreload">',
        '<LINK REL = stylesheet HREF = /assets/index-ABC.css>',
        '<SCRIPT TYPE = module SRC = /assets/index-ABC.js></SCRIPT>',
      ].join("\n")
    )

    const report = await analyzeBundle(distDir)

    assert.equal(report.summary.initialJsAssetCount, 2)
    assert.equal(report.summary.initialCssAssetCount, 1)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("counts script and stylesheet preloads as direct initial transfers", async () => {
  const distDir = await createBundleFixture({ initialCssBytes: 24 })
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      [
        '<link rel="preload" as="script" href="/assets/Feature-ABC.js">',
        '<link rel="preload" as="style" href="/assets/index-ABC.css">',
        '<script type="module" src="/assets/index-ABC.js"></script>',
      ].join("\n")
    )

    const report = await analyzeBundle(distDir)

    assert.equal(report.summary.initialJsAssetCount, 2)
    assert.equal(report.summary.initialCssAssetCount, 1)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("rejects unmodeled preloads of measured JS or CSS while allowing font preloads", async () => {
  const distDir = await createBundleFixture()
  try {
    const entry = path.join(distDir, "client", "index.html")
    const script = '<script type="module" src="/assets/index-ABC.js"></script>'
    const largeBytes = Buffer.concat(
      Array.from({ length: 9500 }, (_, index) =>
        createHash("sha256").update(String(index)).digest()
      )
    )
    await writeFile(path.join(distDir, "client", "assets", "Feature-ABC.js"), largeBytes)
    await writeFile(entry, '<link rel="preload" as="font" href="/assets/font.woff2">' + script)
    const report = await analyzeBundle(distDir)
    assert.equal(report.summary.initialJsAssetCount, 1)

    for (const tag of [
      '<link rel="preload" as="fetch" href="/assets/Feature-ABC.js" crossorigin>',
      '<link rel="preload" as="audio" href="/assets/index-ABC.css">',
      '<link rel="preload" as="fetch" href="/assets/Feature-ABC.mjs">',
      '<link rel="preload" as=" script " href="/assets/Feature-ABC.js">',
      '<link rel="modulepreload" as=" script " href="/assets/Feature-ABC.js">',
    ]) {
      await writeFile(entry, tag + script)
      await assert.rejects(analyzeBundle(distDir), /unsupported|invalid|malformed/iu, tag)
    }
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("counts external classic JavaScript while leaving JSON data blocks inert", async () => {
  const distDir = await createBundleFixture()
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      [
        '<script src="/assets/Feature-ABC.js"></script>',
        '<script type="application/json" src="/assets/vendor-react-ABC.js">{}</script>',
        '<script type="module" src="/assets/index-ABC.js"></script>',
      ].join("\n")
    )

    const report = await analyzeBundle(distDir)

    assert.deepEqual(
      report.assets.filter((asset) => asset.isInitial).map((asset) => asset.path),
      ["client/assets/Feature-ABC.js", "client/assets/index-ABC.js"]
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("does not treat inert template or scripting-enabled noscript contents as roots", async () => {
  const distDir = await createBundleFixture()
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      '<!DOCTYPE html><html><head>' +
        '<template><base href="/other/"><link rel="modulepreload" href="/assets/Feature-ABC.js"></template>' +
        '<noscript><link rel="modulepreload" href="/assets/vendor-react-ABC.js"></noscript>' +
        '</head><body><script type="module" src="/assets/index-ABC.js"></script></body></html>'
    )

    const report = await analyzeBundle(distDir)

    assert.deepEqual(
      report.assets.filter((asset) => asset.isInitial).map((asset) => asset.path),
      ["client/assets/index-ABC.js"]
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("ignores links discarded by browser parsing and accepts passive SVG icons", async () => {
  const distDir = await createBundleFixture()
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      '<svg><g><path d="M0 0"></path></g></svg>' +
        '<select><link rel="modulepreload" href="/assets/Feature-ABC.js"></select>' +
        '<script type="module" src="/assets/index-ABC.js"></script>'
    )

    const report = await analyzeBundle(distDir)

    assert.equal(report.assets.find((asset) => asset.path.endsWith("/Feature-ABC.js")).isInitial, false)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("uses decoded HTML attributes for supported local paths", async () => {
  const distDir = await createBundleFixture()
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      '<link rel="module&#112;reload" href="/assets/Feature&#45;ABC.js">' +
        '<script type="module" src="/assets/index-ABC.js"></script>'
    )

    const report = await analyzeBundle(distDir)

    assert.equal(report.assets.find((asset) => asset.path.endsWith("/Feature-ABC.js")).isInitial, true)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("counts .mjs as JavaScript and applies the general lazy budget", async () => {
  const distDir = await createBundleFixture()
  try {
    const moduleName = "vendor-password-strength-en-ABC.mjs"
    const modulePath = path.join(distDir, "client", "assets", moduleName)
    const largeBytes = Buffer.concat(
      Array.from({ length: 9500 }, (_, index) =>
        createHash("sha256").update(String(index)).digest()
      )
    )
    await writeFile(modulePath, largeBytes)
    const lazyReport = await analyzeBundle(distDir)
    const module = lazyReport.assets.find((asset) => asset.path.endsWith(`/${moduleName}`))
    assert.equal(module?.type, "javascript")
    assert.equal(module?.isInitial, false)
    assert.equal(module?.isPasswordDictionary, false)
    assert.throws(() => assertBundleBudgets(lazyReport), /Lazy JS chunk .* exceeds gzip budget/u)

    await writeFile(path.join(distDir, "client", "assets", "Feature-ABC.mjs"), Buffer.alloc(16))
    await writeFile(
      path.join(distDir, "client", "index.html"),
      '<link rel="modulepreload" href="/assets/Feature-ABC.mjs">' +
        '<script type="module" src="/assets/index-ABC.js"></script>'
    )
    const initialReport = await analyzeBundle(distDir)
    assert.equal(
      initialReport.assets.find((asset) => asset.path.endsWith("/Feature-ABC.mjs")).isInitial,
      true
    )
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("enforces the raw ceiling on highly compressible lazy .mjs dictionaries", async () => {
  const distDir = await createBundleFixture()
  const name = "vendor-password-strength-en-RAW.mjs"
  try {
    await writeFile(
      path.join(distDir, "client", "assets", name),
      Buffer.alloc(BUNDLE_BUDGETS.passwordDictionaryRawKb * 1024 + 1, 97)
    )
    const report = await analyzeBundle(distDir)
    const dictionary = report.assets.find((asset) => asset.path.endsWith(`/${name}`))

    assert.equal(dictionary.isPasswordDictionary, false)
    assert.ok(dictionary.gzipBytes < BUNDLE_BUDGETS.generalLazyJsGzipKb * 1024)
    assert.equal(report.summary.largestPasswordDictionaryRawPath, `client/assets/${name}`)
    assert.throws(() => assertBundleBudgets(report), /vendor-password-strength-en-RAW\.mjs.*raw budget/u)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("only deduplicates unqualified module roots with the same asset path", async () => {
  const distDir = await createBundleFixture()
  try {
    const entry = path.join(distDir, "client", "index.html")
    await writeFile(
      entry,
      '<link rel="modulepreload" href="/assets/index-ABC.js">' +
        '<script type="module" src="/assets/index-ABC.js"></script>'
    )
    const report = await analyzeBundle(distDir)
    assert.equal(report.summary.initialJsAssetCount, 1)

    for (const fragment of [
      '<link rel="modulepreload" crossorigin="anonymous" href="/assets/Feature-ABC.js">' +
        '<script type="module" src="/assets/Feature-ABC.js"></script>',
      '<link rel="modulepreload" href="/assets/Feature-ABC.js">' +
        '<script src="/assets/Feature-ABC.js"></script>',
    ]) {
      await writeFile(entry, fragment + '<script type="module" src="/assets/index-ABC.js"></script>')
      await assert.rejects(analyzeBundle(distDir), /unsupported|invalid|malformed/iu, fragment)
    }
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("rejects initial password dictionaries regardless of size or compression", async () => {
  const distDir = await createBundleFixture()
  try {
    for (const extension of ["js", "mjs"]) {
      const name = `vendor-password-strength-en-RAW.${extension}`
      const dictionary = path.join(distDir, "client", "assets", name)
      await writeFile(
        path.join(distDir, "client", "index.html"),
        `<link rel="modulepreload" href="/assets/${name}">` +
          '<script type="module" src="/assets/index-ABC.js"></script>'
      )
      for (const size of [16, BUNDLE_BUDGETS.passwordDictionaryRawKb * 1024 + 1]) {
        await writeFile(dictionary, Buffer.alloc(size, 97))
        await assert.rejects(analyzeBundle(distDir), /password dictionary.*initial/iu)
      }
    }
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("rejects script escaped-state markup before it can exempt a large lazy chunk", async () => {
  const distDir = await createBundleFixture()
  try {
    const largeBytes = Buffer.concat(
      Array.from({ length: 9500 }, (_, index) =>
        createHash("sha256").update(String(index)).digest()
      )
    )
    await writeFile(path.join(distDir, "client", "assets", "Feature-ABC.js"), largeBytes)
    await writeFile(
      path.join(distDir, "client", "index.html"),
      '<script type="module" src="/assets/index-ABC.js"></script>' +
        '<script><!--<script></script><link rel="modulepreload" href="/assets/Feature-ABC.js">' +
        '<script type="module" src="/assets/index-ABC.js"></script>'
    )

    await assert.rejects(analyzeBundle(distDir), /unsupported|invalid|malformed/iu)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("does not count a link inside a correctly closed double-escaped script", async () => {
  const distDir = await createBundleFixture()
  try {
    await writeFile(
      path.join(distDir, "client", "index.html"),
      '<script type="module" src="/assets/index-ABC.js"></script>' +
        '<script><!--<script></script><link rel="modulepreload" href="/assets/Feature-ABC.js"></script>'
    )

    const report = await analyzeBundle(distDir)

    assert.equal(report.assets.find((asset) => asset.path.endsWith("/Feature-ABC.js")).isInitial, false)
  } finally {
    await rm(distDir, { recursive: true, force: true })
  }
})

test("does not exempt lazy chunks mentioned only in comments or raw text", async () => {
  const fakeLink = '<link rel="modulepreload" href="/assets/Feature-ABC.js">'
  const fragments = [
    `<!-- ${fakeLink} -->`,
    `<script>const sample = '${fakeLink}'</script>`,
  ]
  const largeBytes = Buffer.concat(
    Array.from({ length: 9500 }, (_, index) => createHash("sha256").update(String(index)).digest())
  )

  for (const fragment of fragments) {
    const distDir = await createBundleFixture()
    try {
      await writeFile(path.join(distDir, "client", "assets", "Feature-ABC.js"), largeBytes)
      await writeFile(
        path.join(distDir, "client", "index.html"),
        `${fragment}\n<script type="module" src="/assets/index-ABC.js"></script>`
      )

      const report = await analyzeBundle(distDir)
      const feature = report.assets.find((asset) => asset.path.endsWith("/Feature-ABC.js"))

      assert.equal(feature.isInitial, false, fragment)
      assert.throws(() => assertBundleBudgets(report), /Lazy JS chunk .* exceeds gzip budget/u)
    } finally {
      await rm(distDir, { recursive: true, force: true })
    }
  }
})

test("ignores apparent links in other raw-text elements and quoted attributes", async () => {
  const fakeLink = '<link rel="modulepreload" href="/assets/Feature-ABC.js">'
  const fragments = [
    ...["style", "title", "textarea", "iframe", "xmp", "noembed", "noframes"].map(
      (tag) => `<${tag}>${fakeLink}</${tag}>`
    ),
    `<div data-sample='${fakeLink}'></div>`,
  ]
  for (const fragment of fragments) {
    const distDir = await createBundleFixture()
    try {
      await writeFile(
        path.join(distDir, "client", "index.html"),
        `${fragment}\n<script type="module" src="/assets/index-ABC.js"></script>`
      )
      const report = await analyzeBundle(distDir)
      const feature = report.assets.find((asset) => asset.path.endsWith("/Feature-ABC.js"))
      assert.equal(feature.isInitial, false, fragment)
    } finally {
      await rm(distDir, { recursive: true, force: true })
    }
  }
})

test("rejects ambiguous HTML grammar instead of guessing initial roots", async () => {
  const fragments = [
    '<base href="/other/">',
    '<svg><foreignObject><link rel="modulepreload" href="/assets/Feature-ABC.js"></foreignObject></svg>',
    '<svg><title><link rel="modulepreload" href="/assets/Feature-ABC.js"></title></svg>',
    '<svg><script href="/assets/Feature-ABC.js"></script></svg>',
    '<svg><script xlink:href="/assets/Feature-ABC.js"></script></svg>',
    '<link rel="modulepreload" href="./assets/Feature-ABC.js">',
    '<link rel="modulepreload" href="assets/Feature-ABC.js">',
    '<link rel="modulepreload" href="/assets//Feature-ABC.js">',
    '<link rel="modulepreload" href="/assets/Feature%2dABC.js">',
    '<link rel="modulepreload" href="/assets/Feature-ABC.js?v=1">',
    '<link rel="modulepreload" href="/assets/Feature-ABC.js#fragment">',
    '<link rel="modulepreload" href="/assets/Feature-ABC.js?v=1"><link rel="modulepreload" href="/assets/Feature-ABC.js?v=2">',
    '<link rel="modulepreload" href="/assets/../assets/Feature-ABC.js">',
    '<link rel="modulepreload" href="/assets\\Feature-ABC.js">',
    '<link rel="modulepreload" href="/assets/index-ABC.js" href="/assets/Feature-ABC.js">',
    '<link rel="modulepreload" href="/assets/Feature-ABC.js" media="not all">',
    '<link rel="modulepreload" href="/assets/Feature-ABC.js" disabled>',
    '<link rel="alternate modulepreload" href="/assets/Feature-ABC.js">',
    '<link rel="modulepreload" as="style" href="/assets/Feature-ABC.js">',
    '<link rel="modulepreload" as="font" href="/assets/Feature-ABC.js">',
    '<link rel="preload" as="script" type="text/plain" href="/assets/Feature-ABC.js">',
    '<link rel="preload" as="script" href="https://cdn.invalid/Feature-ABC.js">',
    '<script type="module" src="/assets/index-ABC.js" nomodule></script>',
    '<link rel="modulepreload" href="/assets/Feature-ABC.js"',
    '<!-- text --!><link rel="modulepreload" href="/assets/Feature-ABC.js"> -->',
    '<!--->',
    '<div><span></div></span>',
    '<iframe>unterminated',
  ]

  for (const fragment of fragments) {
    const distDir = await createBundleFixture()
    try {
      await writeFile(
        path.join(distDir, "client", "index.html"),
        `${fragment}\n<script type="module" src="/assets/index-ABC.js"></script>`
      )
      await assert.rejects(analyzeBundle(distDir), /unsupported|invalid|malformed/iu, fragment)
    } finally {
      await rm(distDir, { recursive: true, force: true })
    }
  }
})

test("rejects missing direct local HTML asset references", async () => {
  for (const tag of [
    '<link rel="modulepreload" href="/assets/missing.js">',
    '<link rel="stylesheet" href="/assets/missing.css">',
  ]) {
    const distDir = await createBundleFixture()
    try {
      await writeFile(
        path.join(distDir, "client", "index.html"),
        `${tag}\n<script type="module" src="/assets/index-ABC.js"></script>`
      )

      await assert.rejects(analyzeBundle(distDir), (error) => {
        assert.match(error.message, /client\/assets\/missing\.(?:js|css)/u)
        assert.doesNotMatch(error.message, /[?#]/u)
        assert.ok(!error.message.includes(distDir))
        return true
      })
    } finally {
      await rm(distDir, { recursive: true, force: true })
    }
  }
})

test("checks the raw maximum even when another dictionary has the largest gzip size", async () => {
  const distDir = await createBundleFixture()
  const rawPath = "client/assets/vendor-password-strength-en-RAW.js"
  const gzipPath = "client/assets/vendor-password-strength-ru-GZIP.js"
  try {
    const mixedBytes = Buffer.concat(
      Array.from({ length: 512 }, (_, index) =>
        createHash("sha256").update(String(index)).digest()
      )
    )
    await writeFile(
      path.join(distDir, rawPath),
      Buffer.alloc(BUNDLE_BUDGETS.passwordDictionaryRawKb * 1024 + 1, 97)
    )
    await writeFile(path.join(distDir, gzipPath), mixedBytes)

    const report = await analyzeBundle(distDir)
    const rawAsset = report.assets.find((asset) => asset.path === rawPath)
    const gzipAsset = report.assets.find((asset) => asset.path === gzipPath)

    assert.ok(gzipAsset.gzipBytes > rawAsset.gzipBytes)
    assert.equal(report.summary.largestPasswordDictionaryPath, gzipPath)
    assert.equal(report.summary.largestPasswordDictionaryRawPath, rawPath)
    assert.equal(report.summary.largestPasswordDictionaryRawBytes, rawAsset.rawBytes)
    assert.throws(() => assertBundleBudgets(report), /vendor-password-strength-en-RAW\.js.*raw budget/u)
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
