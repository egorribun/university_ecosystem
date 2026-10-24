import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { existsSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { tmpdir } from "node:os"
import test from "node:test"
import { fileURLToPath } from "node:url"

import {
  browserLaunchOptions,
  buildSmokeReport,
  createLoopbackFixture,
  inspectBrowserDependencies,
  runBrowserChecks,
} from "./browser-dependency-smoke.mjs"

const versions = {
  "@lhci/cli": "0.15.1",
  "@lhci/utils": "0.15.1",
  lighthouse: "13.5.0",
  "puppeteer-core": "25.13.0",
  "chromium-bidi": "157.0.8090-0",
  zod: "4.6.7",
  playwright: "1.64.1",
  "playwright-core": "1.64.1",
}
const fixtureValue = "browser-dependency-smoke"
const browserVersion = "Chrome/155.0.0.0"
const fixtureUrl = "http://127.0.0.1:8123/"

const mains = {
  lighthouse: "core/index.js",
  "puppeteer-core": "lib/puppeteer/puppeteer-core.js",
}

function packageFixture(name, version = versions[name]) {
  return {
    name,
    version,
    main: mains[name] ?? "index.js",
    ...(name === "playwright-core"
      ? { exports: { ".": "./index.js", "./package.json": "./package.json" } }
      : {}),
  }
}

function dependencyFixture() {
  const root = mkdtempSync(join(tmpdir(), "browser-dependencies-test-"))
  const put = (relative, value) => {
    const path = join(root, relative)
    mkdirSync(dirname(path), { recursive: true })
    writeFileSync(path, typeof value === "string" ? value : JSON.stringify(value))
  }
  put("package.json", { name: "owned-smoke-fixture", private: true })
  for (const [name, version] of Object.entries(versions)) {
    const manifest = packageFixture(name, version)
    put("node_modules/" + name + "/package.json", manifest)
    put("node_modules/" + name + "/" + manifest.main, "throw new Error('Must not execute')")
  }
  put("node_modules/playwright-core/browsers.json", {
    browsers: [{ name: "chromium", revision: "1234", installByDefault: true }],
  })
  return { root, put }
}

test("inspects the exact installed consumer chain without executing package code", () => {
  const { root } = dependencyFixture()
  try {
    assert.deepEqual(inspectBrowserDependencies(root), {
      versions,
      chromiumRevision: "1234",
      entrypoints: {
        lighthouse: join(root, "node_modules/lighthouse/core/index.js"),
        puppeteer: join(root, "node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js"),
        playwright: join(root, "node_modules/playwright/index.js"),
      },
    })
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("rejects every wrong installed package name or version", () => {
  const { root, put } = dependencyFixture()
  try {
    for (const [name, version] of Object.entries(versions)) {
      for (const changed of [
        { ...packageFixture(name, version), name: "other" },
        { ...packageFixture(name, version), version: "0.0.0" },
      ]) {
        put("node_modules/" + name + "/package.json", changed)
        assert.throws(() => inspectBrowserDependencies(root))
        put("node_modules/" + name + "/package.json", packageFixture(name, version))
      }
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("rejects missing, oversized and nonregular package manifests", () => {
  for (const [name, version] of Object.entries(versions)) {
    const { root, put } = dependencyFixture()
    const relative = "node_modules/" + name + "/package.json"
    try {
      rmSync(join(root, relative))
      assert.throws(() => inspectBrowserDependencies(root))
      put(relative, " ".repeat(65537))
      assert.throws(() => inspectBrowserDependencies(root))
      rmSync(join(root, relative))
      mkdirSync(join(root, relative))
      assert.throws(() => inspectBrowserDependencies(root))
      rmSync(join(root, relative), { recursive: true })
      put(relative, packageFixture(name, version))
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  }
})

test("rejects nested consumer substitutions even when their version is identical", () => {
  for (const [parent, name] of [
    ["@lhci/cli", "@lhci/utils"],
    ["@lhci/cli", "lighthouse"],
    ["@lhci/utils", "lighthouse"],
    ["lighthouse", "puppeteer-core"],
    ["puppeteer-core", "chromium-bidi"],
    ["chromium-bidi", "zod"],
    ["playwright", "playwright-core"],
  ]) {
    const { root, put } = dependencyFixture()
    try {
      const relative = "node_modules/" + parent + "/node_modules/" + name
      const manifest = packageFixture(name)
      put(relative + "/package.json", manifest)
      put(relative + "/" + manifest.main, "throw new Error('Must not execute')")
      assert.throws(() => inspectBrowserDependencies(root))
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  }
})

test("rejects package and entrypoint symlinks instead of escaping the owned graph", () => {
  for (const entrypoint of [false, true]) {
    const { root, put } = dependencyFixture()
    try {
      const relative = "node_modules/lighthouse" + (entrypoint ? "/core/index.js" : "")
      put("outside/core/index.js", "throw new Error('Must not execute')")
      put("outside/package.json", packageFixture("lighthouse"))
      rmSync(join(root, relative), { recursive: true })
      symlinkSync(
        join(root, "outside", entrypoint ? "core/index.js" : ""),
        join(root, relative),
        entrypoint ? "file" : "dir"
      )
      assert.throws(() => inspectBrowserDependencies(root))
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  }
})

test("requires one bounded numeric Chromium revision from the installed Playwright", () => {
  const { root, put } = dependencyFixture()
  try {
    for (const browsers of [
      [],
      [{ name: "firefox", revision: "1234" }],
      [{ name: "chromium", revision: "../outside" }],
      [{ name: "chromium", revision: "1".repeat(33) }],
      [
        { name: "chromium", revision: "1234" },
        { name: "chromium", revision: "5678" },
      ],
    ]) {
      put("node_modules/playwright-core/browsers.json", { browsers })
      assert.throws(() => inspectBrowserDependencies(root))
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("launch options bind paths, finite timeouts and a minimal child environment", () => {
  const profile = "/owned/profile"
  for (const protocol of ["cdp", "webDriverBiDi"]) {
    assert.deepEqual(browserLaunchOptions("/owned/chromium", profile, protocol), {
      executablePath: "/owned/chromium",
      userDataDir: profile,
      protocol,
      headless: true,
      debuggingPort: 0,
      timeout: 15000,
      protocolTimeout: 10000,
      args: ["--no-sandbox", "--disable-background-networking"],
      env: { HOME: profile, TMPDIR: profile, LANG: "C.UTF-8", TZ: "UTC" },
    })
  }
})

test("browser options reject remote, relative, missing and unsupported inputs", () => {
  for (const [executable, profile, protocol] of [
    ["https://example.test/chrome", "/owned/profile", "cdp"],
    ["relative/chrome", "/owned/profile", "cdp"],
    ["/owned/chrome", "relative/profile", "cdp"],
    ["", "/owned/profile", "cdp"],
    ["/owned/chrome", "", "cdp"],
    ["/owned/chrome", "/owned/profile", "other"],
  ]) {
    assert.throws(() => browserLaunchOptions(executable, profile, protocol))
  }
})

test("fixture owns an ephemeral loopback server and fixed self-contained HTML", async () => {
  const fixture = await createLoopbackFixture()
  assert.ok(fixture)
  try {
    const url = new URL(fixture.url)
    assert.equal(url.protocol, "http:")
    assert.equal(url.hostname, "127.0.0.1")
    assert.match(url.port, /^[1-9][0-9]{0,4}$/)
    assert.equal(url.pathname, "/")
    const response = await fetch(fixture.url)
    assert.equal(response.status, 200)
    assert.match(response.headers.get("content-type"), /^text\/html/)
    const body = await response.text()
    assert.match(body, /<title>Browser dependency smoke<\/title>/)
    assert.match(body, /id="smoke">browser-dependency-smoke</)
    assert(!/https?:|<script|<link|<img/i.test(body))
    assert.equal((await fetch(new URL("/not-owned", fixture.url))).status, 404)
  } finally {
    await fixture.close()
  }
  await assert.rejects(() => fetch(fixture.url))
})

function libraryFixture(change = {}) {
  const calls = []
  const profiles = []
  const closed = []
  const puppeteer = {
    async launch(options) {
      const mode = options.protocol
      profiles.push(options.userDataDir)
      calls.push(["launch", mode])
      if (change.launchFailure === mode) throw new Error("Synthetic launch failure")
      return {
        protocol: change.protocolMode === mode ? change.protocol : mode,
        async version() {
          return mode === "cdp" ? browserVersion : browserVersion + "/synthetic-revision"
        },
        wsEndpoint() {
          return change.endpoint ?? "ws://127.0.0.1:9234/devtools/browser/owned-fixture"
        },
        async newPage() {
          calls.push(["newPage", mode])
          return {
            async goto(url, options) {
              calls.push(["goto", mode, url, options])
              if (change.navigationFailure) throw new Error("Synthetic navigation failure")
              return { status: () => change.status ?? 200 }
            },
            async evaluate(fn) {
              assert.equal(typeof fn, "function")
              calls.push(["evaluate", mode])
              return change.domValue ?? fixtureValue
            },
          }
        },
        async close() {
          closed.push(mode)
        },
      }
    },
  }
  const lighthouse = async (...args) => {
    calls.push(["lighthouse", ...args])
    return {
      lhr: {
        lighthouseVersion: "13.5.0",
        requestedUrl: fixtureUrl,
        finalDisplayedUrl: fixtureUrl,
        audits: { "document-title": { score: 1 } },
        ...change.lhr,
      },
    }
  }
  return { puppeteer, lighthouse, calls, profiles, closed }
}

test("runs Lighthouse's own CDP connection and a separate real BiDi command sequence", async () => {
  const libraries = libraryFixture()
  const result = await runBrowserChecks(libraries, "/owned/chromium", fixtureUrl)
  assert.deepEqual(result, {
    browserVersion,
    lighthouseDocumentTitle: true,
    bidiDomValue: fixtureValue,
  })
  assert.deepEqual(libraries.calls, [
    ["launch", "cdp"],
    [
      "lighthouse",
      fixtureUrl,
      {
        hostname: "127.0.0.1",
        port: 9234,
        logLevel: "error",
        output: "json",
        onlyAudits: ["document-title"],
        throttlingMethod: "provided",
        maxWaitForLoad: 15000,
        disableStorageReset: true,
      },
    ],
    ["launch", "webDriverBiDi"],
    ["newPage", "webDriverBiDi"],
    ["goto", "webDriverBiDi", fixtureUrl, { waitUntil: "load", timeout: 10000 }],
    ["evaluate", "webDriverBiDi"],
  ])
  assert.deepEqual(libraries.closed, ["cdp", "webDriverBiDi"])
  assert.equal(new Set(libraries.profiles).size, 2)
  assert(libraries.profiles.every((path) => !existsSync(path)))
})

test("rejects any nonfixture target before launching browser children", async () => {
  for (const target of [
    "https://example.test/",
    "http://localhost:8123/",
    "http://127.0.0.1/",
    "http://127.0.0.1:8123/other",
    "http://name@127.0.0.1:8123/",
    "http://127.0.0.1:8123/?redirect=outside",
    "http://127.0.0.1:8123/#outside",
  ]) {
    const libraries = libraryFixture()
    await assert.rejects(() => runBrowserChecks(libraries, "/owned/chromium", target))
    assert.deepEqual(libraries.calls, [])
  }
})

test("rejects unsafe CDP endpoints and closes its owned browser", async () => {
  for (const endpoint of [
    "ws://example.test:9234/devtools/browser/owned",
    "wss://127.0.0.1:9234/devtools/browser/owned",
    "ws://name@127.0.0.1:9234/devtools/browser/owned",
  ]) {
    const libraries = libraryFixture({ endpoint })
    await assert.rejects(() => runBrowserChecks(libraries, "/owned/chromium", fixtureUrl))
    assert.deepEqual(libraries.closed, ["cdp"])
    assert(libraries.profiles.every((path) => !existsSync(path)))
  }
})

test("Lighthouse runtime errors or mismatched results fail closed with cleanup", async () => {
  for (const lhr of [
    { runtimeError: { code: "SYNTHETIC_ERROR" } },
    { lighthouseVersion: "12.6.1" },
    { requestedUrl: "http://example.test/" },
    { finalDisplayedUrl: "http://example.test/" },
    { audits: { "document-title": { score: 0 } } },
  ]) {
    const libraries = libraryFixture({ lhr })
    await assert.rejects(() => runBrowserChecks(libraries, "/owned/chromium", fixtureUrl))
    assert.deepEqual(libraries.closed, ["cdp"])
    assert(libraries.profiles.every((path) => !existsSync(path)))
  }
})

test("BiDi failures reject and remove owned profiles", async () => {
  for (const change of [
    { launchFailure: "webDriverBiDi" },
    { navigationFailure: true },
    { status: 500 },
    { domValue: "wrong" },
  ]) {
    const libraries = libraryFixture(change)
    await assert.rejects(() => runBrowserChecks(libraries, "/owned/chromium", fixtureUrl))
    assert.deepEqual(libraries.closed, change.launchFailure ? ["cdp"] : ["cdp", "webDriverBiDi"])
    assert(libraries.profiles.every((path) => !existsSync(path)))
  }
})

test("browser protocol mismatch is not accepted as BiDi coverage", async () => {
  for (const protocolMode of ["cdp", "webDriverBiDi"]) {
    const libraries = libraryFixture({ protocolMode, protocol: "other" })
    await assert.rejects(() => runBrowserChecks(libraries, "/owned/chromium", fixtureUrl))
    assert.deepEqual(libraries.closed, protocolMode === "cdp" ? ["cdp"] : ["cdp", "webDriverBiDi"])
    assert(libraries.profiles.every((path) => !existsSync(path)))
  }
})

function reportFixture() {
  return {
    sourceSha: "a".repeat(40),
    lockSha256: "b".repeat(64),
    runId: "123",
    runAttempt: "2",
    versions,
    chromiumRevision: "1234",
    results: { browserVersion, lighthouseDocumentTitle: true, bidiDomValue: fixtureValue },
  }
}

test("report emits bounded compatibility metadata, not Lighthouse acceptance", () => {
  const input = reportFixture()
  const report = buildSmokeReport(input)
  assert.deepEqual(report, {
    schemaVersion: 1,
    purpose: "browser-dependency-compatibility",
    sourceSha: input.sourceSha,
    lockSha256: input.lockSha256,
    runId: input.runId,
    runAttempt: input.runAttempt,
    versions,
    chromiumRevision: "1234",
    browserVersion,
    checks: { lighthouseDocumentTitle: true, bidiDomValue: fixtureValue },
    performanceAcceptance: false,
  })
  assert(JSON.stringify(report).length < 2048)
})

test("report rejects malformed provenance and failed checks instead of recording success", () => {
  for (const change of [
    { sourceSha: "egorribun" },
    { lockSha256: "not-a-digest" },
    { runId: "0" },
    { runAttempt: "-1" },
    { runId: "1".repeat(21) },
    { runAttempt: "1".repeat(21) },
    { chromiumRevision: "../outside" },
    { chromiumRevision: "1".repeat(33) },
    { versions: { ...versions, "puppeteer-core": "25.11.0" } },
    { results: { browserVersion, lighthouseDocumentTitle: false, bidiDomValue: fixtureValue } },
    { results: { browserVersion, lighthouseDocumentTitle: true, bidiDomValue: "wrong" } },
    {
      results: {
        browserVersion: "private endpoint",
        lighthouseDocumentTitle: true,
        bidiDomValue: fixtureValue,
      },
    },
  ]) {
    assert.throws(() => buildSmokeReport({ ...reportFixture(), ...change }))
  }
})

test("report never copies unbounded extra source fields or raw browser data", () => {
  const input = reportFixture()
  const report = buildSmokeReport({
    ...input,
    rawLhr: "do-not-copy",
    wsEndpoint: "do-not-copy",
    environment: { PRIVATE_VALUE: "do-not-copy" },
  })
  assert.ok(report)
  assert(!JSON.stringify(report).includes("do-not-copy"))
  assert.deepEqual(report, buildSmokeReport(input))
})

test("import is inert and direct CLI preflight cannot emit false success evidence", () => {
  const url = new URL("./browser-dependency-smoke.mjs", import.meta.url)
  const options = { env: {}, encoding: "utf8", timeout: 10000, maxBuffer: 4096 }
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", "import " + JSON.stringify(url.href)],
    options
  )
  assert.equal(imported.status, 0)
  assert.equal(imported.stdout, "")
  assert.equal(imported.stderr, "")
  const direct = spawnSync(process.execPath, [fileURLToPath(url)], options)
  assert.equal(direct.status, 1)
  assert.equal(direct.stdout, "")
  assert.equal(direct.stderr, "Browser dependency smoke rejected at stage: preflight\n")
})
