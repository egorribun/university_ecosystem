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

async function createBundleFixture({ mainBytes = 16, lazyBytes = 16 } = {}) {
  const distDir = await mkdtemp(path.join(tmpdir(), "bundle-budget-test-"))
  const assetsDir = path.join(distDir, "client", "assets")
  await mkdir(assetsDir, { recursive: true })
  await writeFile(
    path.join(distDir, "client", "index.html"),
    [
      '<link rel="modulepreload" href="/assets/vendor-react-ABC.js">',
      '<script type="module" src="/assets/index-ABC.js"></script>',
    ].join("\n")
  )
  await writeFile(path.join(assetsDir, "index-ABC.js"), Buffer.alloc(mainBytes, 97))
  await writeFile(path.join(assetsDir, "vendor-react-ABC.js"), Buffer.alloc(32, 98))
  await writeFile(path.join(assetsDir, "Feature-ABC.js"), Buffer.alloc(lazyBytes, 99))
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

test("reports the real HTML preload graph and writes useful JSON", async () => {
  const distDir = await createBundleFixture()
  try {
    const report = await analyzeBundle(distDir, { commitSha: "abc123" })

    assert.equal(report.schemaVersion, 1)
    assert.equal(report.commitSha, "abc123")
    assert.equal(report.summary.mainJsRawBytes, 16)
    assert.equal(report.summary.initialJsAssetCount, 2)
    assert.equal(report.summary.lazyJsAssetCount, 1)
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
