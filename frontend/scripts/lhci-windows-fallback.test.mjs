import assert from "node:assert/strict"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"

import {
  assertCompleteLighthouseResults,
  buildSafeCommandInvocation,
  DEFAULT_PATHS,
  normalizePath,
  parseLhr,
  resolveNpmCliPath,
  resolveLhciPaths,
} from "./lhci-windows-fallback.mjs"
import routePolicyConfig from "./lhci-route-policy-config.cjs"

test("Windows fallback uses the canonical ten-route LHCI inventory", () => {
  assert.deepEqual(DEFAULT_PATHS, routePolicyConfig.defaultLhciPaths)
  assert.equal(DEFAULT_PATHS.length, 10)
  assert.deepEqual(DEFAULT_PATHS, [
    "/",
    "/login/",
    "/dashboard/",
    "/news/",
    "/schedule/",
    "/events/",
    "/activity/",
    "/map/",
    "/messenger/",
    "/404/",
  ])
})

test("Windows LHCI path normalization preserves explicit directory slashes", () => {
  assert.equal(normalizePath(""), "/")
  assert.equal(normalizePath("dashboard"), "/dashboard")
  assert.equal(normalizePath("dashboard/"), "/dashboard/")
  assert.equal(normalizePath("/events/"), "/events/")
  assert.equal(normalizePath("  /messenger///  "), "/messenger/")
})

test("Windows fallback uses defaults only for an omitted or empty override", () => {
  assert.deepEqual(resolveLhciPaths(undefined), DEFAULT_PATHS)
  assert.deepEqual(resolveLhciPaths(""), DEFAULT_PATHS)
  assert.deepEqual(resolveLhciPaths(",dashboard/,,events"), ["/", "/dashboard/", "/events"])
})

test("Windows npm invocation runs the JavaScript CLI without cmd.exe", () => {
  const unsafeUrl = "https://127.0.0.1:4174/login&whoami"
  const invocation = buildSafeCommandInvocation(
    "npm",
    ["exec", "--yes", "--", "lighthouse", unsafeUrl],
    {
      platform: "win32",
      execPath: "C:\\node\\node.exe",
      npmCliPath: "C:\\node\\node_modules\\npm\\bin\\npm-cli.js",
    }
  )

  assert.equal(invocation.executable, "C:\\node\\node.exe")
  assert.equal(invocation.args[0], "C:\\node\\node_modules\\npm\\bin\\npm-cli.js")
  assert.deepEqual(invocation.args.slice(1), ["exec", "--yes", "--", "lighthouse", unsafeUrl])
  assert.notEqual(invocation.executable.toLowerCase(), "cmd.exe")
})

test("Windows refuses an unresolved npm CLI instead of falling back to cmd.exe", () => {
  assert.throws(
    () =>
      buildSafeCommandInvocation("npm", ["run", "build"], {
        platform: "win32",
        execPath: "C:\\node\\node.exe",
        env: {},
        exists: () => false,
      }),
    /refusing to invoke cmd\.exe/u
  )
})

test("Windows rejects accidental npx use so shell injection cannot regress", () => {
  assert.throws(
    () =>
      buildSafeCommandInvocation("npx", ["lighthouse", "https://example.test/a&b"], {
        platform: "win32",
        npmCliPath: "C:\\node\\npm-cli.js",
      }),
    /npx is not supported on Windows/u
  )
})

test("Windows rejects a cmd shim supplied as the npm CLI path", () => {
  assert.throws(
    () =>
      buildSafeCommandInvocation("npm", ["run", "build"], {
        platform: "win32",
        execPath: "C:\\node\\node.exe",
        npmCliPath: "C:\\node\\npm.cmd",
      }),
    /refusing to invoke cmd\.exe/u
  )
})

test("npm CLI resolution prefers npm's package-script entrypoint", () => {
  const configured = "/tooling/npm-cli.js"
  const resolved = resolveNpmCliPath({
    env: { npm_execpath: configured },
    execPath: "/node/node.exe",
    exists: (candidate) => candidate === configured,
  })
  assert.equal(resolved, configured)
})

test("Lighthouse fallback rejects a partial URL/run result set", () => {
  const measured = { perf: 1, a11y: 1, bp: 1, seo: 1, cls: 0, lcp: 100, tbt: 0 }
  const complete = new Map([
    ["/login", [measured, measured]],
    ["/events", [measured, measured]],
  ])
  assert.doesNotThrow(() => assertCompleteLighthouseResults(complete, 2))

  const partial = new Map([
    ["/login", [measured, null]],
    ["/events", [measured]],
  ])
  assert.throws(
    () => assertCompleteLighthouseResults(partial, 2),
    /did not produce a valid LHR for every URL\/run/u
  )
})

test("parseLhr rejects malformed or structurally incomplete reports", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "lhci-fallback-test-"))
  try {
    const malformed = path.join(root, "malformed.json")
    await writeFile(malformed, JSON.stringify({ categories: {}, audits: {} }), "utf8")
    await assert.rejects(() => parseLhr(malformed), /Invalid Lighthouse result/u)

    const valid = path.join(root, "valid.json")
    await writeFile(
      valid,
      JSON.stringify({
        categories: {
          performance: { score: 1 },
          accessibility: { score: 1 },
          "best-practices": { score: 1 },
          seo: { score: 1 },
        },
        audits: {
          "cumulative-layout-shift": { numericValue: 0 },
          "largest-contentful-paint": { numericValue: 100 },
          "total-blocking-time": { numericValue: 0 },
        },
      }),
      "utf8"
    )
    await assert.doesNotReject(() => parseLhr(valid))
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
