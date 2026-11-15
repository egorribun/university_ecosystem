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

test("minified React diagnostics retain only known numeric codes from errors", () => {
  const diagnostics = audit.summarizeAuthenticatedVisualDiagnostics({
    consoleMessages: [
      {
        type: "error",
        text: "Minified React error #418; visit https://react.dev/errors/418?args[]=private-marker",
      },
      { type: "pageerror", text: "Minified React error #423; private-marker" },
      { type: "warning", text: "Minified React error #418; private-marker" },
      ...["#4180;", "#0418;", "#418private-marker", "#999;", "#418.1;"].map((suffix) => ({
        type: "error",
        text: `Minified React error ${suffix}`,
      })),
    ],
  })
  assert.equal(diagnostics.reactErrorCodeCounts[418], 1)
  assert.equal(diagnostics.reactErrorCodeCounts[423], 1)
  assert.equal(diagnostics.reactErrorCodeCounts.other, 5)
  diagnostics.reactErrorCodeCounts.private = "private-marker"
  const lines = []
  audit.emitAuthenticatedVisualRuntimeDiagnostics("/events", capture, diagnostics, (line) =>
    lines.push(line)
  )
  const record = JSON.parse(lines[0].slice("visual-runtime-diagnostics ".length))
  assert.equal(record.reactErrorCodeCounts[418], 1)
  assert.equal(record.reactErrorCodeCounts[423], 1)
  assert.equal(record.consoleErrorClassCounts.react_minified_error, 7)
  assert.ok(lines[0].length <= 4096)
  assert.doesNotMatch(lines[0], /private|react\.dev|args|999|4180|0418/)
})

test("React code projection rejects malformed counts and caps saturated input", () => {
  const diagnostics = audit.summarizeAuthenticatedVisualDiagnostics({
    consoleMessages: Array.from({ length: 10000 }, () => ({
      type: "error",
      text: "Minified React error #418;",
    })),
  })
  assert.equal(diagnostics.reactErrorCodeCounts[418], 9999)
  assert.equal(diagnostics.capped, true)
  for (const value of [-1, 1.5, Infinity, 10000, "private-marker"]) {
    diagnostics.reactErrorCodeCounts[418] = value
    let calls = 0
    audit.emitAuthenticatedVisualRuntimeDiagnostics("/events", capture, diagnostics, () => calls++)
    assert.equal(calls, 0)
  }
})

test("closed React code inventory matches the locked installed client runtime", async () => {
  const root = new URL("../", import.meta.url)
  const lock = JSON.parse(await readFile(new URL("package-lock.json", root), "utf8"))
  const installed = JSON.parse(
    await readFile(new URL("node_modules/react-dom/package.json", root), "utf8")
  )
  assert.equal(installed.version, lock.packages["node_modules/react-dom"].version)
  assert.equal(installed.version, "19.3.1")
  const source = await readFile(
    new URL("node_modules/react-dom/cjs/react-dom-client.production.js", root),
    "utf8"
  )
  const codes = [
    ...new Set([...source.matchAll(/formatProdErrorMessage\(\s*(\d+)/gu)].map((match) => match[1])),
  ].sort()
  const actual = Object.keys(audit.summarizeAuthenticatedVisualDiagnostics().reactErrorCodeCounts)
    .filter((code) => code !== "other")
    .sort()
  assert.deepEqual(actual, codes)
})

test("React numeric identity survives earlier classifier words in decoder arguments", () => {
  for (const [argument, expectedClass] of [
    ["object%20with%20keys%20%7Bhydration%7D", "react_hydration"],
    ["each child in a list should have a unique key prop", "react_key_warning"],
    ["server rendered html did not match", "react_hydration"],
  ]) {
    for (const type of ["error", "pageerror"]) {
      const diagnostics = audit.summarizeAuthenticatedVisualDiagnostics({
        consoleMessages: [
          {
            type,
            text: `Minified React error #31; visit https://react.dev/errors/31?args[]=${argument}&args[]=private-marker`,
          },
        ],
      })
      assert.equal(diagnostics.reactErrorCodeCounts[31], 1)
      assert.equal(diagnostics.reactErrorCodeCounts.other, 0)
      assert.equal(diagnostics.consoleErrorClassCounts[expectedClass], 1)
      const lines = []
      audit.emitAuthenticatedVisualRuntimeDiagnostics("/events", capture, diagnostics, (line) =>
        lines.push(line)
      )
      const record = JSON.parse(lines[0].slice("visual-runtime-diagnostics ".length))
      assert.equal(record.reactErrorCodeCounts[31], 1)
      assert.equal(record.consoleErrorClassCounts[expectedClass], 1)
      assert.doesNotMatch(lines[0], /private-marker|react\.dev|args\[\]|object%20|unique key/)
    }
  }
})

const validNavbarGeometry = () => ({
  controlsValid: true,
  headerContained: true,
  nameHidden: false,
  nameVisible: true,
  naturalWidth: 120,
  visibleWidth: 80,
  fallbackComplete: false,
  labelExpected: true,
})

test("navbar geometry rejects clipped fragments, missing controls and overflow without rejecting short names", () => {
  const valid = validNavbarGeometry()
  assert.equal(audit.isAuthenticatedNavbarGeometryValid(valid), true)
  assert.equal(
    audit.isAuthenticatedNavbarGeometryValid({ ...valid, naturalWidth: 12, visibleWidth: 12 }),
    true
  )
  for (const invalid of [
    null,
    { ...valid, visibleWidth: 5 },
    { ...valid, controlsValid: false },
    { ...valid, headerContained: false },
    { ...valid, nameVisible: false },
    { ...valid, naturalWidth: NaN },
    { ...valid, visibleWidth: Infinity },
    { ...valid, visibleWidth: -1 },
    { ...valid, naturalWidth: -1 },
  ]) {
    assert.equal(audit.isAuthenticatedNavbarGeometryValid(invalid), false)
  }
  const hidden = {
    ...valid,
    nameHidden: true,
    nameVisible: false,
    labelExpected: false,
    fallbackComplete: true,
  }
  assert.equal(audit.isAuthenticatedNavbarGeometryValid(hidden), true)
  assert.equal(
    audit.isAuthenticatedNavbarGeometryValid({ ...hidden, fallbackComplete: false }),
    false
  )
  assert.equal(audit.isAuthenticatedNavbarGeometryValid({ ...hidden, labelExpected: true }), false)
  assert.equal(
    audit.findNavbarGeometryIssues([
      { viewportWidth: 390 },
      { viewportWidth: 1440, navbarGeometry: valid },
      { viewportWidth: 1440, navbarGeometry: null },
    ]).length,
    1
  )
})

test("navbar observation measures clipping and full-name references without returning text", async () => {
  const { JSDOM } = await import("jsdom")
  const dom = new JSDOM(
    `<style>* { opacity:1; visibility:visible } html { font-size:16px }</style><nav class="vt-navbar"><a id="navbar-logo-link" href="/dashboard">Logo</a><ul class="navbar-desktop-nav">${["dashboard", "news", "schedule", "events", "activity", "map"].map((route) => `<li><a id="navbar-link-${route}" href="/${route}">${route}</a></li>`).join("")}</ul><div id="actions"><button id="global-messenger-btn"></button><button id="global-notifications-btn"></button><div><button id="avatar"></button><div class="navbar-user-name"><button id="name">Private Synthetic Name</button></div><button id="navbar-settings-btn"></button></div></div></nav>`
  )
  const originals = ["document", "window"].map((key) => [
    key,
    Object.getOwnPropertyDescriptor(globalThis, key),
  ])
  try {
    const { document } = dom.window
    Object.defineProperty(globalThis, "document", { value: document, configurable: true })
    Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true })
    const rect = (left, width, height = 44) => ({
      left,
      right: left + width,
      top: 0,
      bottom: height,
      width,
      height,
    })
    for (const element of document.querySelectorAll("*"))
      element.getBoundingClientRect = () => rect(0, 1440, 64)
    Object.defineProperty(document.documentElement, "clientWidth", { value: 1440 })
    const nav = document.querySelector("nav")
    Object.defineProperties(nav, { clientWidth: { value: 1440 }, scrollWidth: { value: 1440 } })
    for (const [index, id] of [
      "global-messenger-btn",
      "global-notifications-btn",
      "avatar",
      "navbar-settings-btn",
    ].entries())
      document.getElementById(id).getBoundingClientRect = () => rect(index * 50, 44)
    const navigation = [...document.querySelectorAll("#navbar-logo-link, .navbar-desktop-nav a")]
    navigation.forEach((link, index) => {
      link.getBoundingClientRect = () => rect(300 + index * 100, 90)
    })
    document.getElementById("actions").getBoundingClientRect = () => rect(0, 260)
    const name = document.querySelector(".navbar-user-name")
    name.getBoundingClientRect = () => rect(200, 5)
    document.getElementById("name").getBoundingClientRect = () => rect(200, 5)
    document.createRange = () => ({
      selectNodeContents() {},
      getBoundingClientRect: () => rect(200, 120),
    })
    const observe = () => audit.measureAuthenticatedNavbarGeometry()
    const clipped = observe()
    assert.equal(clipped.visibleWidth, 5)
    assert.equal(audit.isAuthenticatedNavbarGeometryValid(clipped), false)
    name.style.display = "none"
    document.getElementById("avatar").setAttribute("aria-describedby", "name")
    const hidden = observe()
    assert.equal(audit.isAuthenticatedNavbarGeometryValid(hidden), true)
    assert.equal(
      Object.values(hidden).every(
        (value) => typeof value === "number" || typeof value === "boolean"
      ),
      true
    )
    assert.equal(JSON.stringify(hidden).includes("Private"), false)
    for (const link of navigation) {
      const parent = link.parentElement
      const next = link.nextSibling
      link.remove()
      assert.equal(observe(), null, "missing expected navigation must fail closed")
      parent.insertBefore(link, next)
      const originalRect = link.getBoundingClientRect
      link.getBoundingClientRect = () => rect(100, 44)
      assert.equal(
        audit.isAuthenticatedNavbarGeometryValid(observe()),
        false,
        "navigation/action collision must fail"
      )
      link.getBoundingClientRect = originalRect
    }
    assert.equal(audit.isAuthenticatedNavbarGeometryValid(observe()), true)

    document.getElementById("avatar").setAttribute("aria-describedby", "missing")
    assert.equal(audit.isAuthenticatedNavbarGeometryValid(observe()), false)
    document.getElementById("global-messenger-btn").remove()
    assert.equal(observe(), null)
  } finally {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
    dom.window.close()
  }
})
