import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import vm from "node:vm"
import { fileURLToPath } from "node:url"

import {
  buildAuthenticatedCaptureBasename,
  createAuthenticatedCaptureMetadata,
  createAuthenticatedLoginSidecar,
  createAuthenticatedCaptureRunDirectory,
  canCaptureAuthenticatedScreenshot,
  findDashboardReadinessIssues,
  findNewsReadinessIssues,
  findEventsReadinessIssues,
  findScheduleReadinessIssues,
  isAuthenticatedNewsCaptureReady,
  unavailableNewsPaintDiagnostics,
  summarizeAuthenticatedVisualDiagnostics,
  isAuthenticatedEventsCaptureReady,
  isAuthenticatedScheduleCaptureReady,
  parseAuthenticatedRemoteBrowserConnection,
  parseAuthenticatedVisualCaptureMatrix,
  parseAuthenticatedVisualRoutes,
  parseAuthenticatedSelectedVisualRoute,
} from "./authenticated-visual-audit.mjs"

import {
  classifyAuthenticatedAuditSummaries,
  classifySmokeRouteOutcome,
  classifySmokeFailures,
  requestFailureRecord,
  responseRecord,
} from "./visual-smoke-contract.mjs"

const REPO_ROOT =
  process.env.REPO_ROOT ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..")
if (!path.isAbsolute(REPO_ROOT) || path.resolve(REPO_ROOT) !== REPO_ROOT) {
  throw new Error("REPO_ROOT must be an absolute canonical path")
}
const sourceFile = (...segments) => path.join(REPO_ROOT, ...segments)

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

test("selected visual route is an exact single-route allowlist before matrix work", () => {
  const selectedMatrix = parseAuthenticatedVisualCaptureMatrix({
    ...validAuthenticatedMatrixEnvironment(path.join(os.tmpdir(), "selected-route-matrix")),
    ROUTES: "/events",
    VISUAL_SELECTED_ROUTE: "/events",
  })
  assert.equal(selectedMatrix.selectedRoute, "/events")
  for (const route of ["/news", "/events", "/schedule"]) {
    assert.equal(
      parseAuthenticatedSelectedVisualRoute({ ROUTES: route, VISUAL_SELECTED_ROUTE: route }),
      route
    )
  }
  assert.throws(
    () =>
      parseAuthenticatedSelectedVisualRoute({ ROUTES: "/events", VISUAL_SELECTED_ROUTE: "/news" }),
    /match one supported single ROUTES entry/u
  )
  assert.throws(
    () =>
      parseAuthenticatedSelectedVisualRoute({
        ROUTES: "/events,/schedule",
        VISUAL_SELECTED_ROUTE: "/events",
      }),
    /match one supported single ROUTES entry/u
  )
  assert.throws(
    () =>
      parseAuthenticatedSelectedVisualRoute({
        ROUTES: "/events?token=private",
        VISUAL_SELECTED_ROUTE: "/events?token=private",
      }),
    (error) => {
      assert.equal(error.message, "ROUTES contains an unsupported application path")
      assert.doesNotMatch(error.message, /private/u)
      return true
    }
  )
})

test("Events visual readiness requires the linked loaded panel and visible cards", () => {
  const readyState = {
    pathnameMatches: true,
    headingMatches: true,
    panelVisible: true,
    busyCleared: true,
    activeTabLinked: true,
    visibleCardCount: 2,
    hasRefetchIndicator: false,
  }
  assert.equal(isAuthenticatedEventsCaptureReady(readyState), true)
  assert.equal(isAuthenticatedEventsCaptureReady({ ...readyState, panelVisible: false }), false)
  assert.equal(isAuthenticatedEventsCaptureReady({ ...readyState, busyCleared: false }), false)
  assert.equal(isAuthenticatedEventsCaptureReady({ ...readyState, visibleCardCount: 0 }), false)
  assert.equal(
    isAuthenticatedEventsCaptureReady({ ...readyState, hasRefetchIndicator: true }),
    false
  )
  const failed = {
    path: "/events",
    eventsReadinessRequired: true,
    eventsReady: false,
    eventsCardCount: 0,
    eventsBusyCleared: false,
    eventsReadinessError: "events_tabpanel_or_seeded_cards_not_stable",
  }
  assert.deepEqual(findEventsReadinessIssues([failed]), [failed])
  assert.deepEqual(
    findEventsReadinessIssues([
      {
        ...failed,
        eventsReady: true,
        eventsCardCount: 1,
        eventsBusyCleared: true,
        eventsReadinessError: null,
      },
    ]),
    []
  )
})

test("Events localized heading ignores the nested count badge while preserving visibility", async () => {
  const [audit, eventsHeader, eventsFeature] = await Promise.all([
    readFile(new URL("./authenticated-visual-audit.mjs", import.meta.url), "utf8"),
    readFile(
      sourceFile("frontend", "src", "features", "events", "components", "EventsHeader.tsx"),
      "utf8"
    ),
    readFile(sourceFile("frontend", "src", "features", "events", "EventsFeature.tsx"), "utf8"),
  ])
  const headingMarkup = eventsHeader.match(/<h1\b[\s\S]*?<\/h1>/u)?.[0] ?? ""
  assert.match(headingMarkup, /\{t\("events:pageTitle"\)\}/u)
  assert.match(headingMarkup, /\{eventsCount != null && \([\s\S]*?<span[\s\S]*?\{eventsCount\}/u)
  assert.match(
    eventsFeature,
    /<EventsHeader[\s\S]*?eventsCount=\{tab === "my" \? undefined : filteredEvents\.length\}/u
  )

  const start = audit.indexOf("function authenticatedEventsStateInPage(locale) {")
  const end = audit.indexOf("\nexport function isAuthenticatedEventsCaptureReady", start)
  assert.notEqual(start, -1)
  assert.notEqual(end, -1)
  const pageContext = {
    window: { getComputedStyle: (node) => node.style },
    document: {},
    location: { pathname: "/events" },
    Array,
    Boolean,
    Number,
    Object,
  }
  const stateInPage = vm.runInNewContext("(" + audit.slice(start, end).trim() + ")", pageContext)

  const observe = (locale, title, count, headingOpacity = "1") => {
    const element = (opacity = "1") => ({
      style: { display: "block", visibility: "visible", opacity },
      getBoundingClientRect: () => ({ width: 120, height: 32 }),
      getAttribute: () => null,
    })
    const heading = element(headingOpacity)
    heading.childNodes = [
      { nodeType: 3, textContent: title },
      { nodeType: 1, textContent: String(count) },
    ]
    heading.innerText = title + " " + count

    const cardTitle = element()
    cardTitle.textContent = "Seeded event"
    const card = element()
    card.querySelector = (selector) => (selector === "h3" ? cardTitle : null)

    const activeTab = element()
    activeTab.getAttribute = (name) => (name === "aria-controls" ? "events-tabpanel" : null)
    const panel = element()
    panel.children = []
    panel.getAttribute = (name) => {
      if (name === "aria-label") return title
      if (name === "aria-labelledby") return "events-active-tab"
      if (name === "aria-busy") return "false"
      return null
    }
    panel.querySelectorAll = (selector) =>
      selector === 'article[data-testid="event-card"]' ? [card] : []
    const tablist = element()
    tablist.querySelectorAll = (selector) =>
      selector === '[role="tab"][aria-selected="true"]' ? [activeTab] : []
    const elements = new Map([
      ["main h1", heading],
      ['#events-tabpanel[role="tabpanel"]', panel],
      ['[role="tablist"][aria-label]', tablist],
    ])
    pageContext.document = {
      querySelector: (selector) => elements.get(selector) ?? null,
      getElementById: (id) => (id === "events-active-tab" ? activeTab : null),
    }
    return stateInPage(locale)
  }

  const english = observe("en", "Events", 12)
  const russian = observe("ru", "Мероприятия", 7)
  assert.equal(english.headingMatches, true)
  assert.equal(russian.headingMatches, true)
  assert.equal(isAuthenticatedEventsCaptureReady(english), true)
  assert.equal(isAuthenticatedEventsCaptureReady(russian), true)
  const hidden = observe("en", "Events", 12, "0")
  assert.equal(hidden.headingMatches, false)
  assert.equal(isAuthenticatedEventsCaptureReady(hidden), false)
})

test("Schedule readiness follows the loaded responsive contract and permits a loaded empty mobile day", () => {
  const desktop = {
    pathnameMatches: true,
    mainHeadingVisible: true,
    studentHeadingMatches: true,
    loadedContentVisible: true,
    errorBannerVisible: false,
    desktop: true,
    viewLabelMatches: true,
    visibleLessonCardCount: 1,
    selectedDayTabCount: 0,
    selectedDayPanelVisible: false,
  }
  const mobileWeekday = {
    ...desktop,
    desktop: false,
    selectedDayTabCount: 1,
    selectedDayWeekend: false,
    selectedDayPanelVisible: true,
  }
  const mobileWeekend = {
    ...mobileWeekday,
    visibleLessonCardCount: 0,
    selectedDayWeekend: true,
  }
  assert.equal(isAuthenticatedScheduleCaptureReady(desktop), true)
  assert.equal(
    isAuthenticatedScheduleCaptureReady({ ...desktop, studentHeadingMatches: false }),
    false
  )
  assert.equal(isAuthenticatedScheduleCaptureReady(mobileWeekday), true)
  assert.equal(isAuthenticatedScheduleCaptureReady(mobileWeekend), true)
  assert.equal(
    isAuthenticatedScheduleCaptureReady({ ...mobileWeekend, selectedDayWeekend: false }),
    false
  )
  assert.equal(
    isAuthenticatedScheduleCaptureReady({ ...mobileWeekend, loadedContentVisible: false }),
    false
  )
  assert.equal(isAuthenticatedScheduleCaptureReady({ ...desktop, errorBannerVisible: true }), false)
  const failed = {
    path: "/schedule",
    scheduleReadinessRequired: true,
    viewportWidth: 768,
    scheduleReady: false,
    scheduleLoaded: false,
    scheduleHeadingMatches: false,
    scheduleViewMode: "unknown",
    scheduleLessonCardCount: 0,
    scheduleErrorVisible: false,
    scheduleReadinessError: "schedule_loaded_view_or_content_not_stable",
    scheduleSelectedDayPanelVisible: false,
    scheduleSelectedDayWeekend: false,
  }
  assert.deepEqual(findScheduleReadinessIssues([failed]), [failed])
  const readyMobile = {
    ...failed,
    scheduleReady: true,
    scheduleLoaded: true,
    scheduleHeadingMatches: true,
    scheduleViewMode: "mobile",
    scheduleReadinessError: null,
    scheduleSelectedDayPanelVisible: true,
    scheduleSelectedDayWeekend: true,
  }
  assert.deepEqual(
    findScheduleReadinessIssues([{ ...readyMobile, scheduleHeadingMatches: false }]),
    [{ ...readyMobile, scheduleHeadingMatches: false }]
  )
  assert.deepEqual(findScheduleReadinessIssues([readyMobile]), [])
})

test("selected Events and Schedule readiness selectors remain source-bound", async () => {
  const [
    eventsList,
    eventCard,
    schedule,
    scheduleHeader,
    skeletonMorph,
    mobileView,
    desktopView,
    dayColumn,
    tokens,
    audit,
  ] = await Promise.all([
    readFile(
      sourceFile("frontend", "src", "features", "events", "components", "EventsList.tsx"),
      "utf8"
    ),
    readFile(
      sourceFile("frontend", "src", "components", "events", "EventCard", "EventCardView.tsx"),
      "utf8"
    ),
    readFile(sourceFile("frontend", "src", "pages", "Schedule.tsx"), "utf8"),
    readFile(sourceFile("frontend", "src", "components", "schedule", "ScheduleHeader.tsx"), "utf8"),
    readFile(sourceFile("frontend", "src", "components", "ui", "SkeletonMorph.tsx"), "utf8"),
    readFile(
      sourceFile("frontend", "src", "components", "schedule", "ScheduleMobileView.tsx"),
      "utf8"
    ),
    readFile(
      sourceFile("frontend", "src", "components", "schedule", "ScheduleDesktopTable.tsx"),
      "utf8"
    ),
    readFile(sourceFile("frontend", "src", "components", "schedule", "DayColumn.tsx"), "utf8"),
    readFile(sourceFile("frontend", "src", "theme", "tokens.ts"), "utf8"),
    readFile(new URL("./authenticated-visual-audit.mjs", import.meta.url), "utf8"),
  ])
  assert.match(
    eventsList,
    /id="events-tabpanel"[\s\S]*?aria-busy=\{isInitialLoading \|\| \(tab === "my" && isFetching\) \|\| undefined\}/u
  )
  assert.match(eventCard, /data-testid="event-card"/u)
  assert.match(schedule, /<SkeletonMorph loaded=\{!isLoading\}/u)
  assert.match(
    scheduleHeader,
    /user\?\.role === "student" \? t\("schedule:title\.student"\) : t\("schedule:title\.default"\)/u
  )
  assert.match(audit, /expectedStudentTitle = locale === "ru" \? "Моё расписание" : "My schedule"/u)
  assert.match(audit, /studentHeadingMatches: isVisible\(mainHeading\) && studentHeadingMatches/u)
  assert.match(audit, /scheduleHeadingMatches !== true/u)
  assert.match(skeletonMorph, /data-loaded=\{loaded\}/u)
  assert.match(mobileView, /role="tablist"[\s\S]*?aria-selected=\{isActive\}/u)
  assert.match(desktopView, /role="grid"/u)
  assert.match(dayColumn, /role="tabpanel"[\s\S]*?aria-labelledby=\{`day-tab-\$\{day\}`\}/u)
  assert.match(tokens, /desktop: "1280px"/u)
  assert.match(audit, /const lessonContentRoot = desktop \? grid : selectedPanel/u)
  assert.ok(audit.includes("lessonContentRoot.querySelectorAll('[id^=\"lesson-card-\"]')"))
})

test("Schedule mobile empty-day allowance matches current weekday and demo seed contracts", async () => {
  const [mobileView, scheduleUtils, scheduleData, seed] = await Promise.all([
    readFile(
      sourceFile("frontend", "src", "components", "schedule", "ScheduleMobileView.tsx"),
      "utf8"
    ),
    readFile(sourceFile("frontend", "src", "components", "schedule", "scheduleUtils.ts"), "utf8"),
    readFile(sourceFile("frontend", "src", "hooks", "useScheduleData.ts"), "utf8"),
    readFile(sourceFile("scripts", "seed_demo_data.py"), "utf8"),
  ])
  const [english, russian] = await Promise.all([
    readFile(sourceFile("frontend", "src", "i18n", "locales", "en", "schedule.json"), "utf8"),
    readFile(sourceFile("frontend", "src", "i18n", "locales", "ru", "schedule.json"), "utf8"),
  ])
  const expectedWeekdays = ["mon", "tue", "wed", "thu", "fri", "sat"]
  assert.deepEqual(JSON.parse(english).weekdays.order, expectedWeekdays)
  assert.deepEqual(JSON.parse(russian).weekdays.order, expectedWeekdays)
  assert.equal(JSON.parse(english).title.student, "My schedule")
  assert.equal(JSON.parse(russian).title.student, "Моё расписание")
  assert.match(scheduleUtils, /const day = d\.getDay\(\)[\s\S]*?return day - 1/u)
  assert.match(scheduleData, /todayIdx >= 0 && todayIdx < weekdayBackend\.length/u)
  assert.match(mobileView, /hasToday && todayIdx >= 0 \? todayIdx : 0/u)
  const scheduleRows = seed.match(/SCHEDULE_DATA = \[([\s\S]*?)^\]/mu)?.[1] ?? ""
  const seededWeekdays = [
    ...new Set(Array.from(scheduleRows.matchAll(/^\s*\("([a-z]+)",/gmu), (match) => match[1])),
  ].sort()
  assert.deepEqual(seededWeekdays, ["friday", "monday", "thursday", "tuesday", "wednesday"])
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
    layoutPaintReady: true,
    articlePaintReady: true,
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

test("News readiness requires opaque layout and settled article ancestors", async () => {
  const source = await readFile(
    new URL("./authenticated-visual-audit.mjs", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("function authenticatedNewsStateInPage(locale) {")
  const end = source.indexOf("\nexport function isAuthenticatedNewsCaptureReady", start)
  assert.notEqual(start, -1)
  assert.notEqual(end, -1)

  const element = (style = {}, parentElement = null) => ({
    style: { display: "block", visibility: "visible", opacity: "1", ...style },
    parentElement,
    animations: [],
    getAnimations() {
      return this.animations
    },
    getBoundingClientRect: () => ({ width: 120, height: 80 }),
  })
  const layout = element()
  const html = element()
  const body = element({}, html)
  layout.parentElement = body
  const section = element({}, layout)
  const grid = element({}, section)
  const wrapper = element({ opacity: "0" }, grid)
  const card = element({}, wrapper)
  card.getAttribute = (name) => (name === "data-testid" ? "news-card" : null)
  const link = element({}, card)
  link.textContent = "A seeded news story"
  card.querySelector = (selector) => (selector === 'h2 a[href^="/news/"]' ? link : null)
  const activeFilter = element({}, layout)
  activeFilter.innerText = "All"
  activeFilter.getAttribute = (name) => (name === "aria-current" ? "page" : null)
  const toolbar = element({}, layout)
  toolbar.querySelectorAll = (selector) =>
    selector === 'button[aria-current="page"]' ? [activeFilter] : []
  const heading = element({}, layout)
  heading.innerText = "University news"
  section.children = []
  section.querySelectorAll = (selector) =>
    selector === 'article[data-testid="news-card"]' || selector === "article" ? [card] : []
  const elements = new Map([
    ["h1", heading],
    ['[role="toolbar"]', toolbar],
    ["[data-scroll-root]", layout],
    ["section[aria-label]", section],
  ])
  const stateInPage = vm.runInNewContext("(" + source.slice(start, end).trim() + ")", {
    URLSearchParams,
    window: { __APP_HYDRATED: false, getComputedStyle: (node) => node.style },
    document: {
      documentElement: html,
      querySelector: (selector) => elements.get(selector) ?? null,
    },
    location: { pathname: "/news", search: "" },
    Array,
    Boolean,
    Number,
    Object,
  })

  let state = stateInPage("en")
  assert.equal(state.layoutPaintReady, true)
  assert.equal(state.articlePaintReady, false)
  assert.equal(state.visibleArticleCount, 0)
  assert.deepEqual(JSON.parse(JSON.stringify(state.paintDiagnostics)), {
    schema: 1,
    status: "available",
    rootHydrated: false,
    headingBucket: "expected",
    layoutPresent: true,
    layoutGeometryVisible: true,
    layoutOpacityPermille: 1000,
    layoutFailureCategory: "none",
    layoutOpacityAnimationProbeAvailable: true,
    layoutActiveOpacityAnimations: 0,
    layoutActiveOpacityAnimationsCapped: false,
    domArticleCount: 1,
    domArticleCountCapped: false,
    paintedArticleCount: 0,
    paintedArticleCountCapped: false,
    firstArticleAncestorFailureCategory: "ancestor_low_opacity",
  })
  assert.doesNotMatch(JSON.stringify(state.paintDiagnostics), /University news|seeded news story/u)
  assert.equal(isAuthenticatedNewsCaptureReady(state), false)

  wrapper.style.opacity = "1"
  wrapper.animations = [
    {
      playState: "running",
      effect: { getKeyframes: () => [{ opacity: "0" }, { opacity: "1" }] },
    },
  ]
  state = stateInPage("en")
  assert.equal(state.articlePaintReady, false)
  assert.equal(
    state.paintDiagnostics.firstArticleAncestorFailureCategory,
    "ancestor_opacity_animation"
  )
  assert.equal(state.paintDiagnostics.layoutActiveOpacityAnimations, 0)
  assert.equal(isAuthenticatedNewsCaptureReady(state), false)

  wrapper.animations = []
  layout.style.opacity = "0.7"
  state = stateInPage("en")
  assert.equal(state.layoutPaintReady, false)
  assert.equal(state.articlePaintReady, false)
  assert.equal(state.paintDiagnostics.layoutOpacityPermille, 700)
  assert.equal(state.paintDiagnostics.layoutFailureCategory, "low_opacity")
  assert.equal(state.paintDiagnostics.firstArticleAncestorFailureCategory, "ancestor_low_opacity")

  layout.style.opacity = "1"
  state = stateInPage("en")
  assert.equal(state.layoutPaintReady, true)
  assert.equal(state.articlePaintReady, true)
  assert.equal(state.visibleArticleCount, 1)
  assert.equal(state.paintDiagnostics.paintedArticleCount, 1)
  assert.equal(state.paintDiagnostics.firstArticleAncestorFailureCategory, "none")
  assert.equal(isAuthenticatedNewsCaptureReady(state), true)

  body.style.opacity = "0"
  state = stateInPage("en")
  assert.equal(state.paintDiagnostics.paintedArticleCount, 0)
  assert.equal(state.paintDiagnostics.firstArticleAncestorFailureCategory, "ancestor_low_opacity")
})

test("visual diagnostics expose only bounded closed classifications", () => {
  const diagnostics = summarizeAuthenticatedVisualDiagnostics({
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "warning",
        text: 'Each child in a list should have a unique "key" prop private-marker',
      },
      { type: "warning", text: "A resource was preloaded but not used private-marker" },
      { type: "error", text: "Minified React error #418 private-marker" },
      { type: "info", text: "https://private.invalid/path?token=private-marker" },
      { type: "unrecognized-type", text: "private-marker" },
    ],
    requestFailures: [
      {
        method: "GET",
        url: "http://localhost/fallbacks/default_avatar.png?token=private-marker",
        errorText: "net::ERR_ABORTED private-marker",
      },
      {
        method: "POST",
        url: "https://external.invalid/private/path?secret=private-marker",
        errorText: "net::ERR_CONNECTION_RESET private-marker",
      },
      { method: "GET", url: "not a url private-marker", errorText: "private-marker" },
    ],
    httpFailures: [{ status: 403 }, { status: 503 }],
  })

  assert.equal(diagnostics.schema, 1)
  assert.equal(diagnostics.capped, false)
  assert.equal(diagnostics.consoleTypeCounts.warning, 2)
  assert.equal(diagnostics.consoleTypeCounts.info, 1)
  assert.equal(diagnostics.consoleTypeCounts.other, 1)
  assert.equal(diagnostics.consoleClassCounts.react_key_warning, 1)
  assert.equal(diagnostics.consoleClassCounts.preload_notice, 1)
  assert.equal(diagnostics.consoleClassCounts.react_minified_error, 1)
  assert.equal(diagnostics.requestFailureCount, 3)
  assert.equal(diagnostics.requestOriginCounts.same_origin, 1)
  assert.equal(diagnostics.requestOriginCounts.external, 1)
  assert.equal(diagnostics.requestOriginCounts.invalid, 1)
  assert.equal(diagnostics.requestEndpointCounts.avatar_fallback, 1)
  assert.equal(diagnostics.requestReasonCounts.aborted, 1)
  assert.equal(diagnostics.requestReasonCounts.connection, 1)
  assert.equal(diagnostics.httpStatusClassCounts["4xx"], 1)
  assert.equal(diagnostics.httpStatusClassCounts["5xx"], 1)
  assert.doesNotMatch(
    JSON.stringify(diagnostics),
    /private-marker|private\.invalid|fallbacks\/default_avatar/u
  )

  const excessRows = Array.from({ length: 10_000 }, () => ({}))
  const capped = summarizeAuthenticatedVisualDiagnostics({
    consoleMessages: Array.from({ length: 10_000 }, () => ({ type: "info", text: "bounded" })),
    requestFailures: excessRows,
    httpFailures: excessRows,
  })
  assert.equal(capped.capped, true)
  assert.equal(capped.consoleTypeCounts.info, 9999)
  assert.equal(capped.requestFailureCount, 9999)
  assert.equal(capped.httpFailureCount, 9999)
  assert.doesNotMatch(JSON.stringify(capped), /bounded/u)
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
    unavailableNewsPaintDiagnostics,
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
  assert.deepEqual(timedOut.paintDiagnostics, unavailableNewsPaintDiagnostics())
  assert.equal(timedOut.paintDiagnostics.status, "unavailable")
  assert.ok(
    Object.values(timedOut.paintDiagnostics)
      .slice(2)
      .every((value) => value === null)
  )
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
    canCaptureAuthenticatedScreenshot({
      ...screenshotOptions,
      routePath: "/events",
      finalUrl: "http://localhost/events",
      dashboardCardsVisible: null,
      eventsReadinessRequired: true,
      eventsReady: false,
    }),
    false
  )
  assert.equal(
    canCaptureAuthenticatedScreenshot({
      ...screenshotOptions,
      routePath: "/events",
      finalUrl: "http://localhost/events",
      dashboardCardsVisible: null,
      eventsReadinessRequired: true,
      eventsReady: true,
    }),
    true
  )
  assert.equal(
    canCaptureAuthenticatedScreenshot({
      ...screenshotOptions,
      routePath: "/schedule",
      finalUrl: "http://localhost/schedule",
      dashboardCardsVisible: null,
      scheduleReadinessRequired: true,
      scheduleReady: false,
    }),
    false
  )
  assert.equal(
    canCaptureAuthenticatedScreenshot({
      ...screenshotOptions,
      routePath: "/schedule",
      finalUrl: "http://localhost/schedule",
      dashboardCardsVisible: null,
      scheduleReadinessRequired: true,
      scheduleReady: true,
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

test("classifySmokeRouteOutcome fails on unsuccessful main-document HTTP statuses", () => {
  for (const httpStatus of [200, 302, 399]) {
    assert.deepEqual(
      classifySmokeRouteOutcome({
        navigationError: null,
        httpStatus,
        strict: false,
        hydrationErrorCount: 0,
      }),
      { success: true, failed: false }
    )
  }

  for (const httpStatus of [404, 500]) {
    assert.deepEqual(
      classifySmokeRouteOutcome({
        navigationError: null,
        httpStatus,
        strict: false,
        hydrationErrorCount: 0,
      }),
      { success: false, failed: true }
    )
  }

  assert.deepEqual(
    classifySmokeRouteOutcome({
      navigationError: null,
      httpStatus: null,
      strict: false,
      hydrationErrorCount: 0,
    }),
    { success: true, failed: false }
  )
  assert.deepEqual(
    classifySmokeRouteOutcome({
      navigationError: new Error("navigation failed"),
      httpStatus: null,
      strict: false,
      hydrationErrorCount: 0,
    }),
    { success: false, failed: true }
  )
  assert.deepEqual(
    classifySmokeRouteOutcome({
      navigationError: null,
      httpStatus: 200,
      strict: true,
      hydrationErrorCount: 1,
    }),
    { success: true, failed: true }
  )
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
