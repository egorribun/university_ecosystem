import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import vm from "node:vm"

import {
  buildAuthenticatedCaptureBasename,
  createAuthenticatedCaptureMetadata,
  createAuthenticatedLoginSidecar,
  createAuthenticatedCaptureRunDirectory,
  canCaptureAuthenticatedScreenshot,
  findDashboardReadinessIssues,
  findNewsReadinessIssues,
  isAuthenticatedNewsCaptureReady,
  parseAuthenticatedRemoteBrowserConnection,
  parseAuthenticatedVisualCaptureMatrix,
  parseAuthenticatedVisualRoutes,
} from "./authenticated-visual-audit.mjs"

import {
  classifyAuthenticatedAuditSummaries,
  classifySmokeFailures,
  requestFailureRecord,
  responseRecord,
} from "./visual-smoke-contract.mjs"

function validAuthenticatedMatrixEnvironment(outputDir) {
  return {
    VISUAL_CAPTURE_MATRIX: "1",
    VISUAL_WIDTHS: "390,768,1440",
    VISUAL_LOCALES: "en,ru",
    VISUAL_THEMES: "light,dark",
    VISUAL_HEIGHT: "800",
    SOURCE_SHA: "a".repeat(40),
    ORIGIN: "http://localhost",
    TEST_EMAIL: "synthetic-student@example.test",
    TEST_PASSWORD: randomUUID(),
    OUT_DIR: outputDir,
  }
}

test("authenticated visual matrix validates its private output and dimensions before use", async () => {
  const temporaryRoot = await import("node:fs/promises").then(({ mkdtemp }) =>
    mkdtemp(path.join(os.tmpdir(), "authenticated-visual-matrix-"))
  )
  const checkoutRoot = path.join(temporaryRoot, "checkout")
  const privateOutput = path.join(temporaryRoot, "private-output")
  const credentialedOrigin = new URL("https://example.test/path")
  credentialedOrigin.username = randomUUID()
  credentialedOrigin.password = randomUUID()
  try {
    const config = parseAuthenticatedVisualCaptureMatrix(
      validAuthenticatedMatrixEnvironment(privateOutput),
      { checkoutRoot }
    )
    assert.deepEqual(config.widths, [390, 768, 1440])
    assert.deepEqual(config.locales, ["en", "ru"])
    assert.deepEqual(config.themes, ["light", "dark"])
    assert.equal(config.height, 800)
    assert.equal(config.sourceSha, "a".repeat(40))
    assert.equal(config.outputDir, privateOutput)

    assert.equal(
      parseAuthenticatedVisualCaptureMatrix({ VISUAL_CAPTURE_MATRIX: "0" }),
      null,
      "the default audit path remains opt-in and unchanged"
    )
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix(
          validAuthenticatedMatrixEnvironment(path.join(checkoutRoot, ".screenshots")),
          { checkoutRoot }
        ),
      /outside the checkout/u
    )
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix(
          { ...validAuthenticatedMatrixEnvironment(privateOutput), VISUAL_WIDTHS: "390,0" },
          { checkoutRoot }
        ),
      /320 through 2560/u
    )
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix(
          { ...validAuthenticatedMatrixEnvironment(privateOutput), VISUAL_LOCALES: "en,fr" },
          { checkoutRoot }
        ),
      /supported, unique values/u
    )
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix(
          { ...validAuthenticatedMatrixEnvironment(privateOutput), VISUAL_THEMES: "system" },
          { checkoutRoot }
        ),
      /supported, unique values/u
    )
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix(
          { ...validAuthenticatedMatrixEnvironment(privateOutput), SOURCE_SHA: "not-a-sha" },
          { checkoutRoot }
        ),
      /40-character/u
    )
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix(
          {
            ...validAuthenticatedMatrixEnvironment(privateOutput),
            ORIGIN: credentialedOrigin.toString(),
          },
          { checkoutRoot }
        ),
      /clean HTTP\(S\) origin/u
    )
  } finally {
    await import("node:fs/promises").then(({ rm }) =>
      rm(temporaryRoot, { recursive: true, force: true })
    )
  }
})

test("authenticated route preflight rejects unknown, sensitive, and URL-bearing routes without echoing them", () => {
  const opaqueResetToken = "opaque-reset-secret-must-not-be-echoed"
  const invalidRoutes = [
    "/reset-password/" + opaqueResetToken,
    "/events?token=" + opaqueResetToken,
    "/news?cat=science",
    "/news#" + opaqueResetToken,
    "/../schedule",
    "/unknown-route",
  ]

  for (const route of invalidRoutes) {
    assert.throws(
      () =>
        parseAuthenticatedVisualCaptureMatrix({
          VISUAL_CAPTURE_MATRIX: "0",
          ROUTES: route,
        }),
      (error) => {
        assert.equal(error.message, "ROUTES contains an unsupported application path")
        assert.doesNotMatch(error.message, /opaque-reset-secret-must-not-be-echoed/u)
        return true
      },
      "route validation must run even when matrix capture is disabled"
    )
  }
})

test("remote visual browser connection is optional by default and fail-closed when required", () => {
  assert.equal(parseAuthenticatedRemoteBrowserConnection({}), null)
  assert.throws(
    () =>
      parseAuthenticatedRemoteBrowserConnection({
        VISUAL_REMOTE_CHROMIUM_REQUIRED: "1",
      }),
    (error) => {
      assert.equal(error.message, "Required remote Chromium endpoint is missing")
      return true
    }
  )

  const connection = parseAuthenticatedRemoteBrowserConnection({
    ORIGIN: "http://localhost:4174",
    VISUAL_REMOTE_CHROMIUM_REQUIRED: "1",
    VISUAL_REMOTE_CHROMIUM_WS_ENDPOINT: "ws://127.0.0.1:32123/playwright/session",
  })
  assert.deepEqual(connection, {
    endpoint: "ws://127.0.0.1:32123/playwright/session",
    exposeNetwork: "localhost:4174",
  })

  assert.throws(
    () =>
      parseAuthenticatedRemoteBrowserConnection({
        ORIGIN: "http://localhost:4174",
        VISUAL_REMOTE_CHROMIUM_REQUIRED: "1",
        VISUAL_REMOTE_CHROMIUM_WS_ENDPOINT: "ws://127.0.0.1:32123/playwright/%2fsecret",
      }),
    (error) => {
      assert.equal(error.message, "Remote Chromium endpoint is invalid")
      assert.doesNotMatch(error.message, /secret/u)
      return true
    }
  )
})

test("authenticated route allowlist preserves legacy routes and a seeded messenger UUID detail", () => {
  assert.deepEqual(parseAuthenticatedVisualRoutes({}), [
    "/dashboard",
    "/events",
    "/news",
    "/schedule",
    "/profile",
    "/settings",
    "/map",
    "/activity",
    "/messenger",
  ])
  assert.deepEqual(parseAuthenticatedVisualRoutes({ ROUTES: "dashboard,/events" }), [
    "/dashboard",
    "/events",
  ])

  assert.deepEqual(parseAuthenticatedVisualRoutes({ ROUTES: "news" }), ["/news"])

  const seededChatRoute = "/messenger/0f8fad5b-d9cb-469f-a165-70867728950e"
  assert.deepEqual(parseAuthenticatedVisualRoutes({ ROUTES: seededChatRoute }), [seededChatRoute])
  assert.equal(
    parseAuthenticatedVisualCaptureMatrix({ VISUAL_CAPTURE_MATRIX: "0", ROUTES: seededChatRoute }),
    null
  )
})

test("authenticated matrix filenames and metadata retain every requested dimension", () => {
  const capture = { locale: "ru", theme: "dark", width: 390, height: 800 }
  assert.equal(buildAuthenticatedCaptureBasename("/dashboard"), "dashboard")
  assert.equal(buildAuthenticatedCaptureBasename("/dashboard", capture), "dashboard_ru_dark_w390")
  assert.deepEqual(
    createAuthenticatedCaptureMetadata(capture, {
      sourceSha: "b".repeat(40),
      visualConfigurationMatches: true,
      screenshotPath: "dashboard_ru_dark_w390.png",
    }),
    {
      captureMode: "authenticated-live-matrix",
      sourceSha: "b".repeat(40),
      locale: "ru",
      theme: "dark",
      viewport: { width: 390, height: 800 },
      visualConfigurationMatches: true,
      visualConfigurationError: null,
      screenshotPath: "dashboard_ru_dark_w390.png",
    }
  )
})

test("authenticated matrix uses fresh run directories without replacing earlier captures", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "authenticated-capture-run-"))
  try {
    const priorCapture = path.join(temporaryRoot, "prior-capture.png")
    await writeFile(priorCapture, "owner-supplied baseline")
    const first = await createAuthenticatedCaptureRunDirectory(temporaryRoot)
    const second = await createAuthenticatedCaptureRunDirectory(temporaryRoot)

    assert.notEqual(first, second)
    assert.match(path.basename(first), /^run-/u)
    assert.match(path.basename(second), /^run-/u)
    assert.equal(await readFile(priorCapture, "utf8"), "owner-supplied baseline")
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true })
  }
})

test("authenticated login sidecar omits subject, token ID, and raw identity claims", () => {
  const sidecar = createAuthenticatedLoginSidecar({
    cookies: [{ name: "access_token_v2" }],
    jwtAlgorithm: "RS256",
    jwtAudience: "university-ecosystem-api",
    jwtHeader: { alg: "RS256" },
    jwtPayload: { sub: "private-subject", jti: "private-token-id", email: "private@example.test" },
  })
  const serialized = JSON.stringify(sidecar)
  assert.equal(sidecar.loginVerified, true)
  assert.equal(sidecar.jwtAlgorithm, "RS256")
  assert.doesNotMatch(
    serialized,
    /private-subject|private-token-id|private@example\.test|"sub"|"jti"/u
  )
})

test("authenticated matrix preflight and filenames stay outside the legacy artifact contract", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const mainSource = source.slice(source.indexOf("async function main()"))
  const routePreflightIndex = mainSource.indexOf("parseAuthenticatedVisualRoutes(process.env)")
  assert.notEqual(routePreflightIndex, -1, "all audit modes validate routes before work starts")
  for (const sideEffect of [
    "console.log(",
    "checkJwksEndpoint()",
    "connectAuthenticatedRemoteChromium(",
    "chromium.launch",
    "createAuthenticatedCaptureRunDirectory(",
    "writeFile(",
  ]) {
    assert.ok(
      routePreflightIndex < mainSource.indexOf(sideEffect),
      `route validation must precede ${sideEffect}`
    )
  }
  assert.ok(
    mainSource.indexOf("parseAuthenticatedVisualCaptureMatrix()") <
      mainSource.indexOf("checkJwksEndpoint()"),
    "invalid matrix input must fail before JWKS network access"
  )
  assert.ok(
    mainSource.indexOf("parseAuthenticatedVisualCaptureMatrix()") <
      mainSource.indexOf("chromium.launch"),
    "invalid matrix input must fail before browser launch"
  )
  assert.match(source, /path\.join\(outputDir, "matrix\.json"\)/u)
  assert.match(source, /if \(process\.argv\[1\].*=== __filename\)/u)
  assert.equal(buildAuthenticatedCaptureBasename("/dashboard"), "dashboard")
  assert.equal(
    buildAuthenticatedCaptureBasename("/dashboard", {
      locale: "en",
      theme: "light",
      width: 1440,
    }),
    "dashboard_en_light_w1440"
  )
})

test("dashboard capture rejects loaded skeleton content that is still transparent", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("function dashboardCardsAreVisible() {")
  const end = source.indexOf("\n\nexport function canCaptureAuthenticatedScreenshot", start)
  assert.notEqual(start, -1)
  assert.notEqual(end, -1)
  const cards = new Map()
  const predicate = vm.runInNewContext(`(${source.slice(start, end).trim()})`, {
    document: { querySelector: (selector) => cards.get(selector) ?? null },
    window: { getComputedStyle: (element) => element.style },
  })

  for (const name of ["schedule", "news", "events"]) {
    const content = {
      style: { opacity: "0", display: "block", visibility: "visible" },
      getAttribute: (attribute) => (attribute === "data-loaded" ? "true" : null),
      getClientRects: () => [{}],
    }
    cards.set(`.vt-dash-${name}`, {
      style: { opacity: "1", transform: "none" },
      parentElement: { style: { opacity: "1", transform: "none" } },
      querySelector: (selector) =>
        selector === '.skeleton-morph-content[data-loaded="true"]' ? content : null,
      content,
    })
  }

  const wrapperOnlyProof = [...cards.values()].every(
    (card) => card.style.opacity === "1" && card.parentElement.style.opacity === "1"
  )
  assert.equal(wrapperOnlyProof, true)
  assert.equal(predicate(), false)

  for (const card of cards.values()) card.content.style.opacity = "1"
  assert.equal(predicate(), true)
})

test("News visual readiness requires a settled heading, default filter, and non-empty visible cards", () => {
  const readyState = {
    pathnameMatches: true,
    headingMatches: true,
    toolbarVisible: true,
    activeFilterCount: 1,
    activeFilterAll: true,
    defaultFilterUrl: true,
    visibleArticleCount: 2,
    hasNextPageSkeleton: false,
    hasRefetchIndicator: false,
  }
  assert.equal(isAuthenticatedNewsCaptureReady(readyState), true)
  assert.equal(isAuthenticatedNewsCaptureReady({ ...readyState, activeFilterAll: false }), false)
  assert.equal(isAuthenticatedNewsCaptureReady({ ...readyState, visibleArticleCount: 0 }), false)

  const unready = {
    path: "/news",
    newsReadinessRequired: true,
    newsReady: false,
    newsArticleCount: 0,
    newsActiveFilterState: "unexpected",
  }
  assert.deepEqual(findNewsReadinessIssues([unready]), [unready])
  assert.deepEqual(
    findNewsReadinessIssues([
      {
        ...unready,
        newsReady: true,
        newsArticleCount: 2,
        newsActiveFilterState: "all",
      },
    ]),
    []
  )
  assert.deepEqual(findNewsReadinessIssues([{ path: "/news", newsReadinessRequired: false }]), [])
})

test("News readiness bounds page evaluation and clips settle waits to its total deadline", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("async function waitForAuthenticatedNewsReady(page, locale) {")
  const end = source.indexOf("\n\nexport function findNewsReadinessIssues", start)
  assert.notEqual(start, -1)
  assert.notEqual(end, -1)

  const clock = { now: 100, timeoutDelays: [], cleared: [], waits: [], fireTimer: null }
  let timerId = 0
  const waitForReady = vm.runInNewContext("(" + source.slice(start, end).trim() + ")", {
    Date: { now: () => clock.now },
    Promise,
    Number,
    Math,
    JSON,
    authenticatedNewsStateInPage: () => null,
    isAuthenticatedNewsCaptureReady: (state) => state?.ready === true,
    setTimeout: (callback, delay) => {
      const id = ++timerId
      clock.timeoutDelays.push(delay)
      if (clock.fireTimer) clock.fireTimer(callback, delay)
      return id
    },
    clearTimeout: (id) => clock.cleared.push(id),
  })

  clock.fireTimer = (callback, delay) => {
    clock.now += delay
    callback()
  }
  const timedOut = await waitForReady({ evaluate: () => new Promise(() => {}) }, "en")
  assert.equal(timedOut.ready, false)
  assert.equal(timedOut.error, "news_heading_filter_or_nonempty_list_not_stable")
  assert.deepEqual(clock.timeoutDelays, [30_000])
  assert.equal(clock.cleared.length, 1)

  clock.now = 100
  clock.timeoutDelays = []
  clock.cleared = []
  clock.waits = []
  clock.fireTimer = null
  const clipped = await waitForReady(
    {
      evaluate: async () => {
        clock.now = 29_900
        return { ready: true, visibleArticleCount: 4, activeFilterAll: true }
      },
      waitForTimeout: async (milliseconds) => {
        clock.waits.push(milliseconds)
        clock.now += milliseconds
      },
    },
    "ru"
  )
  assert.equal(clipped.ready, false)
  assert.deepEqual(clock.timeoutDelays, [30_000])
  assert.deepEqual(clock.waits, [200])
  assert.equal(clock.cleared.length, 1)
})

test("unready dashboard summaries fail aggregation and cannot produce a screenshot", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  assert.match(source, /canCaptureAuthenticatedScreenshot\(/u)
  assert.match(source, /findDashboardReadinessIssues\(summaries\)/u)

  const unready = { path: "/dashboard", dashboardCardsVisible: false }
  const screenshotOptions = {
    captureConfig: {},
    visualConfigurationMatches: true,
    routePath: "/dashboard",
    httpStatus: 200,
    redirectedToLogin: false,
    finalUrl: "http://localhost/dashboard",
    dashboardCardsVisible: false,
  }
  assert.deepEqual(findDashboardReadinessIssues([unready]), [unready])
  assert.equal(canCaptureAuthenticatedScreenshot(screenshotOptions), false)
  assert.equal(
    canCaptureAuthenticatedScreenshot({
      ...screenshotOptions,
      routePath: "/news",
      finalUrl: "http://localhost/news",
      newsReadinessRequired: true,
      newsReady: false,
    }),
    false
  )
  assert.equal(
    canCaptureAuthenticatedScreenshot({
      ...screenshotOptions,
      routePath: "/news",
      finalUrl: "http://localhost/news",
      newsReadinessRequired: true,
      newsReady: true,
    }),
    true
  )
  assert.equal(
    canCaptureAuthenticatedScreenshot({ ...screenshotOptions, dashboardCardsVisible: true }),
    true
  )
  assert.deepEqual(
    findDashboardReadinessIssues([
      { path: "/dashboard", dashboardCardsVisible: true },
      { path: "/news", dashboardCardsVisible: null },
    ]),
    []
  )
})

test("unauthenticated smoke blocks service workers for deterministic SSR lifecycle", async () => {
  const source = await readFile(
    new URL("./unauthenticated-routes-smoke.mjs", import.meta.url),
    "utf8"
  )

  assert.match(
    source,
    /browser\.newContext\(\{[\s\S]*serviceWorkers:\s*["']block["']/u,
    "SSR smoke must not allow a PWA service worker to replace or hold the document while it closes"
  )
})

test("authenticated audit classification fails closed when axe never completes", () => {
  const failures = classifyAuthenticatedAuditSummaries([
    {
      httpStatus: 200,
      redirectedToLogin: false,
      hydrationErrorCount: 0,
      axeError: "axe-analyze-timeout-60s",
      axeViolationCount: 0,
      consoleErrorCount: 0,
      failedNetworkRequestCount: 0,
    },
  ])

  assert.equal(failures.axeErrors.length, 1)
  assert.deepEqual(failures.axeIssues, [])
})

test("responseRecord binds status and method to the response URL", () => {
  const record = responseRecord({
    url: () => "http://localhost/api/v1/users/me",
    status: () => 401,
    request: () => ({ method: () => "GET" }),
  })

  assert.deepEqual(record, {
    method: "GET",
    url: "http://localhost/api/v1/users/me",
    status: 401,
  })
})

test("requestFailureRecord binds transport failures to their request URL", () => {
  assert.deepEqual(
    requestFailureRecord({
      method: () => "GET",
      url: () => "http://localhost/assets/missing.js",
      failure: () => ({ errorText: "net::ERR_CONNECTION_RESET" }),
    }),
    {
      method: "GET",
      url: "http://localhost/assets/missing.js",
      errorText: "net::ERR_CONNECTION_RESET",
    }
  )
})

test("classifySmokeFailures rejects console errors, page errors, and non-2xx/3xx responses", () => {
  const failures = classifySmokeFailures({
    consoleMessages: [
      { type: "warning", text: "allowed warning" },
      { type: "error", text: "request failed" },
      { type: "pageerror", text: "render exploded" },
    ],
    networkResponses: [
      { method: "GET", url: "http://localhost/ok", status: 200 },
      { method: "GET", url: "http://localhost/redirect", status: 302 },
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
    ],
    networkFailures: [{ method: "GET", url: "http://localhost/assets/app.js", errorText: "reset" }],
  })

  assert.equal(failures.consoleErrors.length, 2)
  assert.deepEqual(failures.nonSuccessfulResponses, [
    { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
  ])
  assert.equal(failures.networkFailures.length, 1)
})

test("classifySmokeFailures recognizes minified and descriptive hydration failures", () => {
  const failures = classifySmokeFailures({
    consoleMessages: [
      { type: "error", text: "Minified React error #418" },
      { type: "error", text: "Hydration did not match" },
    ],
    networkResponses: [],
  })

  assert.equal(failures.hydrationErrors.length, 2)
})

test("classifySmokeFailures accepts exactly one located unauthenticated profile probe", () => {
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
    ],
    networkResponses: [{ method: "GET", url: "http://localhost/api/v1/users/me", status: 401 }],
  })

  assert.deepEqual(failures.consoleErrors, [])
  assert.deepEqual(failures.nonSuccessfulResponses, [])
})

test("classifySmokeFailures accepts every exact profile probe without hiding unrelated failures", () => {
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/admin" },
      },
      {
        type: "pageerror",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "profile request failed with 401",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me?retry=1" },
      },
    ],
    networkResponses: [
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
      { method: "GET", url: "http://localhost/api/v1/admin", status: 401 },
      { method: "POST", url: "http://localhost/api/v1/users/me", status: 401 },
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 403 },
      { method: "GET", url: "http://localhost/api/v1/users/me?retry=1", status: 401 },
    ],
  })

  assert.equal(failures.consoleErrors.length, 4)
  assert.equal(failures.nonSuccessfulResponses.length, 4)
})

test("classifySmokeFailures rejects a foreign-origin profile 401", () => {
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "https://foreign.example/api/v1/users/me" },
      },
    ],
    networkResponses: [
      { method: "GET", url: "https://foreign.example/api/v1/users/me", status: 401 },
    ],
  })

  assert.equal(failures.consoleErrors.length, 1)
  assert.equal(failures.nonSuccessfulResponses.length, 1)
})

test("classifySmokeFailures retains profile console errors beyond matched network probes", () => {
  const profileConsoleError = {
    type: "error",
    text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
    location: { url: "http://localhost/api/v1/users/me" },
  }
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [profileConsoleError, { ...profileConsoleError }],
    networkResponses: [{ method: "GET", url: "http://localhost/api/v1/users/me", status: 401 }],
  })

  assert.equal(failures.consoleErrors.length, 1)
  assert.deepEqual(failures.nonSuccessfulResponses, [])
})
