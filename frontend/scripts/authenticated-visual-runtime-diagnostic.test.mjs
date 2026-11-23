import assert from "node:assert/strict"
import test from "node:test"
import { readFile } from "node:fs/promises"
import path from "node:path"
import vm from "node:vm"
import {
  classifyAuthenticatedAuditSummaries,
  classifySmokeFailures,
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
      classifySmokeFailures,
      isPublicVisualRoute: audit.isPublicVisualRoute,
      classifyVisualNavigation: audit.classifyVisualNavigation,
      visualPageReadinessSelector: audit.visualPageReadinessSelector,
      isVisualPageHeadingReady: audit.isVisualPageHeadingReady,
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
        listeners.get("response")({ url: request.url, request: () => request, status: () => 503 })
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

test("visual routes accept only exact public pages and UUID detail paths", () => {
  const id = "018f1234-5678-7123-8123-123456789abc"
  const routes = ["/login", "/register", `/news/${id}`, `/events/${id}`, `/messenger/${id}`]
  assert.deepEqual(audit.parseAuthenticatedVisualRoutes({ ROUTES: routes.join(",") }), routes)
  assert.deepEqual(audit.parseAuthenticatedVisualRoutes({ ROUTES: "login,register" }), [
    "/login",
    "/register",
  ])
  for (const invalid of [
    "/sign-up",
    "/login/",
    "/register?next=dashboard",
    "/news/article-slug",
    "/news/00000000-0000-0000-0000-000000000000",
    `/news/${id}/edit`,
    `/events/${id}?x=1`,
    `/events/${id}#x`,
    `/events/%2f${id}`,
    `/messenger/${id}/extra`,
    "/../login",
  ]) {
    assert.throws(
      () => audit.parseAuthenticatedVisualRoutes({ ROUTES: invalid }),
      { message: "ROUTES contains an unsupported application path" },
      invalid
    )
  }
})

test("public captures cover every matrix configuration before the owned login", async () => {
  const id = "018f1234-5678-7123-8123-123456789abc"
  const routes = ["/register", "/dashboard", "/login", `/news/${id}`, `/events/${id}`]
  const configurations = ["ru", "en"].flatMap((locale) =>
    ["light", "dark"].flatMap((theme) =>
      [1440, 390].map((width) => ({ locale, theme, width, height: 800 }))
    )
  )
  const operations = []
  await audit.captureVisualRoutePhases({
    routes,
    configurations,
    capture: async (route, configuration, capturePhase) =>
      operations.push({ route, configuration, capturePhase }),
    authenticate: async () => operations.push("login"),
  })
  const loginIndex = operations.indexOf("login")
  assert.equal(loginIndex, 16)
  assert.equal(operations.length, routes.length * configurations.length + 1)
  for (const configuration of configurations) {
    for (const route of routes) {
      const index = operations.findIndex(
        (operation) => operation.route === route && operation.configuration === configuration
      )
      assert.ok(index >= 0, `missing ${route} matrix cell`)
      assert.equal(index < loginIndex, route === "/login" || route === "/register")
      assert.equal(operations[index].capturePhase, index < loginIndex ? "pre-login" : "post-login")
    }
  }
})

test("a failed public capture or login prevents later authenticated captures", async () => {
  const operations = []
  await assert.rejects(
    audit.captureVisualRoutePhases({
      routes: ["/login", "/dashboard"],
      configurations: [null],
      capture: async (route) => {
        operations.push(route)
        throw new Error("capture failed")
      },
      authenticate: async () => operations.push("login"),
    }),
    /capture failed/u
  )
  assert.deepEqual(operations, ["/login"])
  operations.length = 0
  await assert.rejects(
    audit.captureVisualRoutePhases({
      routes: ["/login", "/dashboard"],
      configurations: [null],
      capture: async (route) => operations.push(route),
      authenticate: async () => {
        operations.push("login")
        throw new Error("login failed")
      },
    }),
    /login failed/u
  )
  assert.deepEqual(operations, ["/login", "login"])
})

test("public login sidecars do not overwrite the owned session report", () => {
  assert.notEqual(audit.buildAuthenticatedCaptureBasename("/login"), "login")
  assert.equal(
    audit.buildAuthenticatedCaptureBasename("/login", {
      locale: "ru",
      theme: "dark",
      width: 390,
    }),
    "login_ru_dark_w390"
  )
})

test("public pages require their exact destination but no authenticated navbar", () => {
  for (const route of ["/login", "/register"]) {
    assert.deepEqual(audit.classifyVisualNavigation(route, `http://localhost${route}`), {
      redirectedToLogin: false,
      publicNavigationMismatch: false,
      exactNavigationMismatch: false,
    })
    assert.equal(
      audit.classifyVisualNavigation(route, "http://localhost/dashboard").publicNavigationMismatch,
      true
    )
    assert.equal(
      audit.classifyVisualNavigation(route, `http://localhost${route}?next=%2Fdashboard`)
        .publicNavigationMismatch,
      true
    )
    assert.deepEqual(
      audit.findNavbarGeometryIssues([{ path: route, viewportWidth: 1440, navbarGeometry: null }]),
      []
    )
  }
  assert.equal(
    audit.classifyVisualNavigation("/dashboard", "http://localhost/login?next=%2Fdashboard")
      .redirectedToLogin,
    true
  )
})

test("public and detail destinations reject a different origin, query, fragment, or path", () => {
  const id = "018f1234-5678-7123-8123-123456789abc"
  for (const route of ["/login", "/register", `/news/${id}`, `/events/${id}`]) {
    assert.equal(
      audit.classifyVisualNavigation(route, `http://localhost${route}`).exactNavigationMismatch,
      false
    )
    for (const destination of [
      `http://elsewhere.invalid${route}`,
      `http://localhost${route}?x=1`,
      `http://localhost${route}#x`,
      "http://localhost/dashboard",
      null,
    ]) {
      assert.equal(audit.classifyVisualNavigation(route, destination).exactNavigationMismatch, true)
    }
  }
})

test("new public and seeded detail captures require the correct loaded heading", async () => {
  const id = "018f1234-5678-7123-8123-123456789abc"
  for (const [route, selector] of [
    ["/login", "#login-heading"],
    ["/register", "#register-heading"],
    [`/news/${id}`, ".news-theme article h1"],
    [`/events/${id}`, ".events-theme article h1"],
  ]) {
    assert.equal(audit.visualPageReadinessSelector(route), selector)
  }
  for (const route of ["/dashboard", "/news", "/events", `/messenger/${id}`]) {
    assert.equal(audit.visualPageReadinessSelector(route), null)
  }

  const { JSDOM } = await import("jsdom")
  const dom = new JSDOM('<div class="news-theme"><article><h1>Seeded title</h1></article></div>')
  const originals = ["document", "window"].map((key) => [
    key,
    Object.getOwnPropertyDescriptor(globalThis, key),
  ])
  try {
    Object.defineProperty(globalThis, "document", {
      value: dom.window.document,
      configurable: true,
    })
    Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true })
    const heading = dom.window.document.querySelector("h1")
    heading.getBoundingClientRect = () => ({ width: 100, height: 30 })
    assert.equal(audit.isVisualPageHeadingReady(".news-theme article h1"), true)
    assert.equal(audit.isVisualPageHeadingReady("#login-heading"), false)
    heading.textContent = " "
    assert.equal(audit.isVisualPageHeadingReady(".news-theme article h1"), false)
    heading.textContent = "Seeded title"
    heading.parentElement.style.opacity = "0"
    assert.equal(audit.isVisualPageHeadingReady(".news-theme article h1"), false)
    heading.parentElement.style.opacity = "1"
    heading.style.display = "none"
    assert.equal(audit.isVisualPageHeadingReady(".news-theme article h1"), false)
    heading.style.display = "block"
    heading.getBoundingClientRect = () => ({ width: 0, height: 30 })
    assert.equal(audit.isVisualPageHeadingReady(".news-theme article h1"), false)
    heading.getBoundingClientRect = () => ({ width: Number.NaN, height: 30 })
    assert.equal(audit.isVisualPageHeadingReady(".news-theme article h1"), false)
  } finally {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
    dom.window.close()
  }
})

test("public capture classifies only the exact unauthenticated profile probe as expected", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("async function auditRoute(")
  const end = source.indexOf("\nfunction printSummary", start)
  const run = async (probeUrl, status = 401, route = "/login", options = {}) => {
    const listeners = new Map()
    const sidecars = []
    const screenshots = []
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
      classifySmokeFailures,
      isPublicVisualRoute: audit.isPublicVisualRoute,
      classifyVisualNavigation: audit.classifyVisualNavigation,
      visualPageReadinessSelector: audit.visualPageReadinessSelector,
      isVisualPageHeadingReady: audit.isVisualPageHeadingReady,
      summarizeAuthenticatedVisualDiagnostics: audit.summarizeAuthenticatedVisualDiagnostics,
      emitAuthenticatedVisualRuntimeDiagnostics() {},
      emitAxeDiagnostics() {},
      requireFromProject: () => ({ getRules: () => [] }),
      canCaptureAuthenticatedScreenshot: audit.canCaptureAuthenticatedScreenshot,
      buildAuthenticatedCaptureBasename: audit.buildAuthenticatedCaptureBasename,
      createAuthenticatedCaptureMetadata: audit.createAuthenticatedCaptureMetadata,
      writeFile: async (name, contents) => {
        if (typeof contents === "string") sidecars.push([name, JSON.parse(contents)])
        else screenshots.push([name, contents])
      },
    }
    const auditRoute = vm.runInNewContext(`(${source.slice(start, end).trim()})`, context)
    let urlReadCount = 0
    let screenshotComplete = false
    const page = {
      on: (event, listener) => listeners.set(event, listener),
      off: (event) => listeners.delete(event),
      emulateMedia: async () => {},
      setViewportSize: async () => {},
      addInitScript: async () => {},
      goto: async () => {
        const request = { method: () => "GET", url: () => probeUrl }
        let consoleStatus = status
        if (options.concurrentRequests) {
          const post = { method: () => "POST", url: () => probeUrl }
          const secondGet = { method: () => "GET", url: () => probeUrl }
          for (const candidate of [request, post, secondGet]) listeners.get("request")(candidate)
          const getStatus = options.concurrentRequests === "get-probe" ? 401 : 200
          const postStatus = options.concurrentRequests === "get-probe" ? 200 : 401
          for (const [candidate, responseStatus] of [
            [secondGet, 200],
            [request, getStatus],
            [post, postStatus],
          ]) {
            listeners.get("response")({
              url: candidate.url,
              request: () => candidate,
              status: () => responseStatus,
            })
          }
          consoleStatus = 401
        } else {
          listeners.get("request")(request)
          listeners.get("response")({
            url: request.url,
            request: () => request,
            status: () => status,
          })
        }
        if (consoleStatus !== 200) {
          listeners.get("console")({
            type: () => "error",
            text: () =>
              `Failed to load resource: the server responded with a status of ${consoleStatus}`,
            location: () => ({ url: probeUrl }),
          })
        }
        return { status: () => 200 }
      },
      url: () =>
        screenshotComplete && options.screenshotRedirect
          ? options.screenshotRedirect
          : `http://localhost${++urlReadCount === 1 ? route : (options.finalRoute ?? route)}`,
      waitForTimeout: async () => {},
      waitForFunction: async (fn, selector, { timeout } = {}) => {
        if (fn === audit.isVisualPageHeadingReady) {
          assert.equal(selector, audit.visualPageReadinessSelector(route))
          assert.equal(timeout, 30_000)
          if (options.unready) throw new Error("heading unavailable")
        }
      },
      evaluate: async (fn) => {
        if (fn === audit.isVisualPageHeadingReady) return !options.headingMissingAfterScreenshot
        if (String(fn).includes("documentElement")) {
          return screenshotComplete && options.configurationAfterScreenshot
            ? options.configurationAfterScreenshot
            : { locale: "en", theme: "light", width: 1440, height: 800 }
        }
        return { violations: [] }
      },
      screenshot: async () => {
        screenshotComplete = true
        if (options.failureDuringScreenshot) {
          const request = { method: () => "GET", url: () => "http://localhost/api/v1/news" }
          listeners.get("request")?.(request)
          listeners.get("response")?.({
            request: () => request,
            status: () => 503,
          })
          listeners.get("console")?.({
            type: () => "error",
            text: () => "Failed to load resource: the server responded with a status of 503",
            location: () => ({ url: request.url() }),
          })
        }
        return Buffer.from("local screenshot")
      },
    }
    const result = await auditRoute(
      page,
      route,
      "/private",
      { locale: "en", theme: "light", width: 1440, height: 800 },
      null,
      audit.isPublicVisualRoute(route) ? "pre-login" : "post-login"
    )
    assert.equal(listeners.size, 0)
    assert.equal(sidecars.length, 1)
    return { result, sidecar: sidecars[0][1], screenshots }
  }
  const expected = await run("http://localhost/api/v1/users/me")
  assert.equal(expected.result.redirectedToLogin, false)
  assert.equal(expected.result.consoleErrorCount, 0)
  assert.equal(expected.result.failedNetworkRequestCount, 0)
  assert.equal(expected.result.visualPageReady, true)
  assert.equal(expected.result.screenshotPath, "login_en_light_w1440.png")
  assert.equal(expected.sidecar.networkRequests[0].status, 401)
  assert.equal(expected.sidecar.capturePhase, "pre-login")
  assert.equal(expected.sidecar.captureMode, "authenticated-live-matrix")
  for (const [url, status] of [
    ["http://localhost/api/v1/users/me?x=1", 401],
    ["http://localhost/api/v1/users/me", 403],
    ["http://elsewhere.invalid/api/v1/users/me", 401],
  ]) {
    const actual = await run(url, status, "/register")
    assert.equal(actual.sidecar.capturePhase, "pre-login")
    assert.equal(actual.result.consoleErrorCount, 1)
    assert.equal(actual.result.failedNetworkRequestCount, 1)
  }
  const legitimateProbe = await run("http://localhost/api/v1/users/me", 200, "/login", {
    concurrentRequests: "get-probe",
  })
  assert.equal(legitimateProbe.result.consoleErrorCount, 0)
  assert.equal(legitimateProbe.result.failedNetworkRequestCount, 0)
  assert.deepEqual(
    legitimateProbe.sidecar.networkRequests.map(({ method, status }) => [method, status]),
    [
      ["GET", 401],
      ["POST", 200],
      ["GET", 200],
    ]
  )
  const failedPost = await run("http://localhost/api/v1/users/me", 200, "/login", {
    concurrentRequests: "post-failed",
  })
  assert.equal(failedPost.result.consoleErrorCount, 1)
  assert.equal(failedPost.result.failedNetworkRequestCount, 1)
  assert.deepEqual(
    failedPost.sidecar.networkRequests.map(({ method, status }) => [method, status]),
    [
      ["GET", 200],
      ["POST", 401],
      ["GET", 200],
    ]
  )
  const unready = await run("http://localhost/api/v1/users/me", 401, "/login", { unready: true })
  assert.equal(unready.result.visualPageReady, false)
  assert.equal(unready.result.screenshotPath, null)
  assert.equal(unready.sidecar.visualPageReadinessError, "required_heading_not_visible")
  const redirected = await run("http://localhost/api/v1/users/me", 401, "/login", {
    finalRoute: "/dashboard",
  })
  assert.equal(redirected.result.publicNavigationMismatch, true)
  assert.equal(redirected.result.screenshotPath, null)
  assert.equal(redirected.sidecar.finalUrl, "http://localhost/dashboard")
  const id = "018f1234-5678-7123-8123-123456789abc"
  for (const route of [`/news/${id}`, `/events/${id}`]) {
    const loaded = await run("http://localhost/api/v1/users/me", 200, route)
    assert.equal(loaded.result.visualPageReady, true)
    assert.equal(loaded.sidecar.capturePhase, "post-login")
    assert.equal(loaded.sidecar.captureMode, "authenticated-live-matrix")
    assert.ok(loaded.result.screenshotPath)
    const pending = await run("http://localhost/api/v1/users/me", 200, route, { unready: true })
    assert.equal(pending.result.visualPageReady, false)
    assert.equal(pending.result.screenshotPath, null)
  }
  for (const route of ["/login", `/news/${id}`, `/events/${id}`]) {
    const destination = `http://elsewhere.invalid${route}?private=private-marker`
    const changed = await run("http://localhost/api/v1/users/me", 200, route, {
      screenshotRedirect: destination,
    })
    assert.equal(changed.result.exactNavigationMismatch, true)
    assert.equal(changed.result.screenshotPath, null)
    assert.equal(changed.sidecar.screenshotPath, null)
    assert.equal(changed.screenshots.length, 0)
    assert.doesNotMatch(JSON.stringify(changed.sidecar), /private-marker/)
    const missingHeading = await run("http://localhost/api/v1/users/me", 200, route, {
      headingMissingAfterScreenshot: true,
    })
    assert.equal(missingHeading.result.visualPageReady, false)
    assert.equal(missingHeading.sidecar.visualPageReadinessError, "required_heading_not_visible")
    assert.equal(missingHeading.sidecar.screenshotPath, null)
    assert.equal(missingHeading.screenshots.length, 0)
    for (const changedConfig of [
      { locale: "ru", theme: "light", width: 1440, height: 800 },
      { locale: "en", theme: "dark", width: 1440, height: 800 },
      { locale: "en", theme: "light", width: 390, height: 800 },
    ]) {
      const changed = await run("http://localhost/api/v1/users/me", 200, route, {
        configurationAfterScreenshot: changedConfig,
      })
      assert.equal(changed.result.captureConfigMatches, false)
      assert.equal(changed.sidecar.screenshotPath, null)
      assert.equal(changed.screenshots.length, 0)
    }
  }
  const lateFailure = await run("http://localhost/api/v1/users/me", 200, "/login", {
    failureDuringScreenshot: true,
  })
  assert.equal(lateFailure.result.consoleErrorCount, 1)
  assert.equal(lateFailure.result.failedNetworkRequestCount, 1)
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

test("capture summary labels the recorded authentication phase", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("function printSummary(")
  const end = source.indexOf("\nasync function connectAuthenticatedRemoteChromium", start)
  assert.ok(start >= 0 && end > start)
  const lines = []
  const printSummary = vm.runInNewContext(`(${source.slice(start, end).trim()})`, {
    console: { log: (line) => lines.push(line) },
  })
  const summary = (path, capturePhase, redirectedToLogin = false) => ({
    path,
    capturePhase,
    redirectedToLogin,
    httpStatus: 200,
    consoleErrorCount: 0,
    hydrationErrorCount: 0,
    axeViolationCount: 0,
    networkRequestCount: 0,
    finalUrl: null,
  })
  printSummary([
    summary("/login", "pre-login"),
    summary("/register", "pre-login"),
    summary("/dashboard", "post-login"),
    summary("/profile", "post-login", true),
    summary("/unknown", null),
  ])
  for (const [route, label] of [
    ["/login", "PUBLIC"],
    ["/register", "PUBLIC"],
    ["/dashboard", "AUTHED"],
    ["/profile", "REDIRECT"],
    ["/unknown", "UNKNOWN"],
  ]) {
    assert.match(
      lines.find((line) => line.startsWith(route)),
      new RegExp(`^${route}\\s+200\\s+${label}\\b`)
    )
  }
})
