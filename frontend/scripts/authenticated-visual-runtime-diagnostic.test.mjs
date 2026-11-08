import assert from "node:assert/strict"
import test from "node:test"
import { readFile } from "node:fs/promises"
import path from "node:path"
import vm from "node:vm"
import {
  classifyAuthenticatedAuditSummaries,
  requestFailureRecord,
} from "./visual-smoke-contract.mjs"
import * as audit from "./authenticated-visual-audit.mjs"

const capture = { locale: "ru", theme: "dark", width: 390 }
const makeDiagnostics = () =>
  audit.summarizeAuthenticatedVisualDiagnostics({
    expectedOrigin: "https://stand.invalid",
    consoleMessages: [
      { type: "warning", text: "React warning private-marker" },
      { type: "error", text: "Refused to connect due to Content Security Policy private-marker" },
      { type: "pageerror", text: "Failed to fetch dynamically imported module private-marker" },
      { type: "error", text: "blocked by CORS policy private-marker" },
      { type: "error", text: "Refused MIME type private-marker" },
    ],
    requestFailures: [
      {
        method: "GET",
        url: "https://third.invalid/private?secret=private-marker",
        errorText: "net::ERR_BLOCKED_BY_CLIENT private-marker",
      },
    ],
    httpFailures: [
      {
        method: "GET",
        url: "https://stand.invalid/api/v1/private?token=private-marker",
        status: 503,
      },
    ],
  })

test("public runtime diagnostics expose error-only classes and separate HTTP/network buckets", () => {
  const diagnostics = makeDiagnostics()
  assert.equal(diagnostics.consoleErrorClassCounts.content_security_policy, 1)
  assert.equal(diagnostics.consoleErrorClassCounts.cors_failure, 1)
  assert.equal(diagnostics.consoleErrorClassCounts.module_load_failure, 1)
  assert.equal(diagnostics.consoleErrorClassCounts.mime_type, 1)
  assert.equal(diagnostics.consoleErrorClassCounts.react_other, 0)
  assert.equal(diagnostics.httpFailureOriginCounts.same_origin, 1)
  assert.equal(diagnostics.httpFailureEndpointCounts.api, 1)
  const lines = []
  audit.emitAuthenticatedVisualRuntimeDiagnostics("/dashboard", capture, diagnostics, (line) =>
    lines.push(line)
  )
  assert.equal(lines.length, 1)
  assert.ok(lines[0].length <= 4096)
  assert.ok(lines[0].startsWith("visual-runtime-diagnostics "))
  const record = JSON.parse(lines[0].slice("visual-runtime-diagnostics ".length))
  assert.equal(record.route, "/dashboard")
  assert.equal(record.locale, "ru")
  assert.equal(record.theme, "dark")
  assert.equal(record.width, 390)
  assert.equal(record.consoleTypeCounts.error, 3)
  assert.equal(record.consoleTypeCounts.pageerror, 1)
  assert.equal(record.consoleErrorClassCounts.react_other, 0)
  assert.equal(record.requestOriginCounts.external, 1)
  assert.equal(record.requestReasonCounts.blocked, 1)
  assert.equal(record.httpFailureCount, 1)
  assert.equal(record.httpStatusClassCounts["5xx"], 1)
  assert.doesNotMatch(
    lines[0],
    /private-marker|third\.invalid|stand\.invalid|token=|secret=|Refused|React warning/
  )
})

test("public projection ignores extra fields and normalizes unsupported capture identifiers", () => {
  const diagnostics = makeDiagnostics()
  diagnostics.private = "private-marker"
  diagnostics.toJSON = () => {
    throw new Error("private-marker")
  }
  diagnostics.consoleTypeCounts.private = "private-marker"
  const lines = []
  audit.emitAuthenticatedVisualRuntimeDiagnostics(
    "/private?token=private-marker",
    { locale: "private-marker", theme: "private-marker", width: "private-marker" },
    diagnostics,
    (line) => lines.push(line)
  )
  const record = JSON.parse(lines[0].slice("visual-runtime-diagnostics ".length))
  assert.equal(record.route, "other")
  assert.equal(record.locale, "other")
  assert.equal(record.theme, "other")
  assert.equal(record.width, 0)
  assert.doesNotMatch(lines[0], /private-marker|private/)
})

test("malformed counts and throwing getters or sinks cannot leak or change gate classification", () => {
  for (const value of [
    -1,
    NaN,
    Infinity,
    10000,
    1.5,
    "private-marker",
    { toJSON: () => "private-marker" },
  ]) {
    const diagnostics = makeDiagnostics()
    diagnostics.consoleTypeCounts.error = value
    let calls = 0
    assert.doesNotThrow(() =>
      audit.emitAuthenticatedVisualRuntimeDiagnostics(
        "/dashboard",
        capture,
        diagnostics,
        () => calls++
      )
    )
    assert.equal(calls, 0)
  }
  let calls = 0
  assert.doesNotThrow(() =>
    audit.emitAuthenticatedVisualRuntimeDiagnostics(
      "/dashboard",
      capture,
      makeDiagnostics(),
      () => {
        calls++
        throw new Error("private-marker")
      }
    )
  )
  assert.equal(calls, 1)
  const diagnostics = makeDiagnostics()
  Object.defineProperty(diagnostics, "consoleTypeCounts", {
    get() {
      throw new Error("private-marker")
    },
  })
  assert.doesNotThrow(() =>
    audit.emitAuthenticatedVisualRuntimeDiagnostics("/dashboard", capture, diagnostics, () => {
      throw new Error("unexpected output")
    })
  )
})

test("empty and saturated diagnostic summaries stay finite and bounded", () => {
  for (const diagnostics of [
    audit.summarizeAuthenticatedVisualDiagnostics(),
    audit.summarizeAuthenticatedVisualDiagnostics({
      consoleMessages: Array.from({ length: 10000 }, () => ({
        type: "error",
        text: "private-marker",
      })),
    }),
  ]) {
    const lines = []
    audit.emitAuthenticatedVisualRuntimeDiagnostics("/news", null, diagnostics, (line) =>
      lines.push(line)
    )
    assert.equal(lines.length, 1)
    assert.ok(lines[0].length <= 4096)
    assert.doesNotMatch(lines[0], /private-marker/)
  }
})

test("route event capture emits classifications without changing runtime failure gates", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("async function auditRoute(")
  const end = source.indexOf("\nfunction printSummary", start)
  assert.ok(start >= 0 && end > start)
  const run = async (failOutput) => {
    const lines = []
    let sidecars = 0
    const listeners = new Map()
    const context = {
      URL,
      path,
      setTimeout,
      clearTimeout,
      ORIGIN: "http://localhost",
      AXE_SOURCE_PATH: "/unused/axe.js",
      console: { log() {} },
      safeAuditUrl: (value) => {
        const url = new URL(value)
        return url.origin + url.pathname
      },
      redactDiagnostic: (value) => value,
      requestFailureRecord,
      summarizeAuthenticatedVisualDiagnostics: audit.summarizeAuthenticatedVisualDiagnostics,
      emitAuthenticatedVisualRuntimeDiagnostics: (...args) =>
        audit.emitAuthenticatedVisualRuntimeDiagnostics(...args, (line) => {
          if (failOutput) throw new Error("private-marker")
          lines.push(line)
        }),
      emitAxeDiagnostics() {},
      requireFromProject: () => ({ getRules: () => [] }),
      dashboardCardsAreVisible() {},
      canCaptureAuthenticatedScreenshot: audit.canCaptureAuthenticatedScreenshot,
      buildAuthenticatedCaptureBasename: audit.buildAuthenticatedCaptureBasename,
      createAuthenticatedCaptureMetadata: audit.createAuthenticatedCaptureMetadata,
      writeFile: async () => {
        sidecars++
      },
    }
    const auditRoute = vm.runInNewContext(`(${source.slice(start, end).trim()})`, context)
    const page = {
      on: (event, listener) => listeners.set(event, listener),
      off: (event) => listeners.delete(event),
      emulateMedia: async () => {},
      addInitScript: async () => {},
      goto: async () => {
        listeners.get("console")({
          type: () => "error",
          text: () => "Failed to load resource private-marker",
        })
        listeners.get("pageerror")(new TypeError("private-marker"))
        const request = {
          method: () => "GET",
          url: () => "http://localhost/api/v1/private?token=private-marker",
          failure: () => ({ errorText: "net::ERR_CONNECTION_RESET private-marker" }),
        }
        listeners.get("request")(request)
        listeners.get("response")({ url: request.url, status: () => 503 })
        listeners.get("requestfailed")(request)
        return { status: () => 200 }
      },
      url: () => "http://localhost/dashboard",
      waitForTimeout: async () => {},
      waitForFunction: async () => {},
      evaluate: async () => ({ violations: [] }),
    }
    const result = await auditRoute(page, "/dashboard", "/unused-private-output")
    assert.equal(listeners.size, 0)
    assert.equal(sidecars, 1)
    assert.equal(result.consoleErrorCount, 2)
    assert.equal(result.failedNetworkRequestCount, 2)
    assert.equal(result.hydrationErrorCount, 0)
    assert.equal(result.axeViolationCount, 0)
    assert.equal(classifyAuthenticatedAuditSummaries([result]).runtimeIssues.length, 1)
    assert.equal(lines.length, failOutput ? 0 : 1)
    if (!failOutput) {
      const record = JSON.parse(lines[0].slice("visual-runtime-diagnostics ".length))
      assert.equal(record.consoleErrorClassCounts.resource_failure, 1)
      assert.equal(record.consoleErrorClassCounts.other, 1)
      assert.equal(record.httpFailureEndpointCounts.api, 1)
      assert.equal(record.requestReasonCounts.connection, 1)
      assert.doesNotMatch(lines[0], /private-marker|localhost|token=|\/api\//)
    }
    return JSON.stringify(result)
  }
  assert.equal(await run(false), await run(true))
})

test("stateful getters cannot swap allowed values for private payloads during projection", () => {
  const diagnostics = makeDiagnostics()
  const config = {}
  const reads = { capped: 0, locale: 0, theme: 0, width: 0 }
  Object.defineProperty(diagnostics, "capped", {
    get() {
      return ++reads.capped === 1 ? false : "private-marker"
    },
  })
  for (const [key, value] of Object.entries(capture)) {
    Object.defineProperty(config, key, {
      get() {
        return ++reads[key] === 1 ? value : "private-marker"
      },
    })
  }
  const lines = []
  audit.emitAuthenticatedVisualRuntimeDiagnostics("/dashboard", config, diagnostics, (line) =>
    lines.push(line)
  )
  assert.equal(lines.length, 1)
  assert.doesNotMatch(lines[0], /private-marker/)
  const record = JSON.parse(lines[0].slice("visual-runtime-diagnostics ".length))
  assert.equal(record.capped, false)
  assert.equal(record.locale, "ru")
  assert.equal(record.theme, "dark")
  assert.equal(record.width, 390)
  assert.deepEqual(reads, { capped: 1, locale: 1, theme: 1, width: 1 })
})
