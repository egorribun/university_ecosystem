import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./navbar-layout-stability.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const navbarUrl = new URL("../../src/components/navbar/Navbar.tsx", import.meta.url)
const navbarLogoUrl = new URL("../../src/components/navbar/NavbarLogo.tsx", import.meta.url)
const pillUrl = new URL("../../src/components/navbar/NavbarPill.tsx", import.meta.url)
const scrollBehaviorUrl = new URL("../../src/hooks/ui/useScrollBehavior.ts", import.meta.url)
const scrollConstantsUrl = new URL("../../src/constants/scroll.ts", import.meta.url)

const [spec, fixtures, config, navbar, navbarLogo, pill, scrollBehavior, scrollConstants] =
  await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(navbarUrl, "utf8"),
    readFile(navbarLogoUrl, "utf8"),
    readFile(pillUrl, "utf8"),
    readFile(scrollBehaviorUrl, "utf8"),
    readFile(scrollConstantsUrl, "utf8"),
  ])

test("live navbar stability measures real scroll-driven layout shifts", () => {
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/news["']\)/u)
  assert.match(spec, /PerformanceObserver/u)
  assert.match(spec, /layout-shift/u)
  assert.match(spec, /hadRecentInput/u)
  assert.match(spec, /NAVBAR_CLS_LIMIT\s*=\s*0\.1/u)
  assert.match(spec, /expect\(finalMetrics\.cls\)\.toBeLessThan\(NAVBAR_CLS_LIMIT\)/u)
  assert.match(spec, /vt-navbar/u)
  assert.match(spec, /getBoundingClientRect\(\)/u)
  assert.match(spec, /classList\.contains\(["']relative["']\)/u)
  assert.match(spec, /window\.scrollTo\(0,\s*180\)/u)
  assert.match(spec, /window\.scrollTo\(0,\s*0\)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeFromHAR|useMockApi/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)\(/u)
  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*loginPasswordForRole\(role\),\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
})

test("navbar CLS observation includes font and image stabilization", () => {
  const observerInstallation = spec.indexOf("await page.addInitScript")
  const newsNavigation = spec.indexOf('await page.goto("/news")')
  const fontReadiness = spec.indexOf("await document.fonts.ready")
  const imageDecode = spec.indexOf("image.decode()")

  assert.ok(observerInstallation >= 0, "install the observer before target-page navigation")
  assert.ok(observerInstallation < newsNavigation)
  assert.ok(newsNavigation < fontReadiness)
  assert.ok(fontReadiness < imageDecode)
  assert.match(
    spec,
    /observer\.observe\(\{\s*type:\s*["']layout-shift["'],\s*buffered:\s*true\s*\}\)/u
  )
  assert.match(spec, /expect\(decodedNavbarImages\)\.toBeGreaterThan\(0\)/u)
})

test("the measurement exercises the fixed navbar shell and production scroll threshold", () => {
  assert.match(navbar, /<nav[\s\S]{0,180}className=\{cn\([\s\S]{0,180}vt-navbar/u)
  assert.match(navbar, /h-\(--navbar-height\)/u)
  assert.match(navbar, /<NavbarPill[\s\S]{0,180}isCompact=\{showPill\}/u)
  assert.match(pill, /transition-\[transform,opacity\]/u)
  assert.match(navbarLogo, /<SmartImage[\s\S]*?loading="eager"/u)
  assert.match(scrollBehavior, /NAVBAR_SCROLL_ENTER_THRESHOLD/u)
  assert.match(scrollBehavior, /requestAnimationFrame\(commitScrollState\)/u)
  assert.match(scrollConstants, /NAVBAR_SCROLL_ENTER_THRESHOLD\s*=\s*72/u)
  assert.match(scrollConstants, /NAVBAR_SCROLL_EXIT_THRESHOLD\s*=\s*24/u)
})

test("the live run is Chromium-project discoverable with diagnostic artifacts disabled", () => {
  assert.match(spec, /test\.skip\(testInfo\.project\.name\s*!==\s*["']desktop["']/u)
  assert.match(
    spec,
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']\s*\}\)/u
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})

test("the desktop spacing diagnostic emits bounded geometry only on failing samples", async () => {
  const spec = await readFile(specUrl, "utf8")
  assert.match(spec, /const NAVBAR_GEOMETRY_DIAGNOSTIC_LIMIT = 6/u)
  assert.match(spec, /UE_LIVE_NAVBAR_GEOMETRY_V1 project=/u)
  assert.match(spec, /sample\.messengerLeft - sample\.referenceRight < 12/u)
  assert.match(spec, /sample\.nameRight > sample\.settingsLeft \+ 1/u)
  assert.match(spec, /sample\.settingsRight > sample\.contentRight \+ 1/u)
  assert.match(spec, /sample\.scrollWidth > sample\.clientWidth \+ 1/u)
})

// Bottom navigation and the drawer share the production navbar shell. Keep
// their rapid-input acceptance contract in this existing CI entrypoint.
test("mobile navigation preserves native rapid input, final content, and history assertions", async () => {
  const navigationSpec = await readFile(
    new URL("./footer-bottom-navigation.live.spec.ts", import.meta.url),
    "utf8"
  )
  assert.match(navigationSpec, /for \(const width of \[390, 360\]\)/u)
  assert.match(
    navigationSpec,
    /await verifyRapidMobileNavigation\(page, testInfo\.project\.use\.hasTouch === true\)/u
  )
  assert.equal((navigationSpec.match(/^test\(/gmu) ?? []).length, 2)
  const rapid = navigationSpec.slice(
    navigationSpec.indexOf("async function verifyRapidMobileNavigation")
  )
  assert.match(
    rapid,
    /const rapidPaths = \["\/events", "\/schedule", "\/profile", "\/news"\] as const/u
  )
  const burst = rapid.slice(
    rapid.indexOf("for (const point of points)"),
    rapid.indexOf('await expectCurrentRoute("/news")')
  )
  assert.match(burst, /await page\.touchscreen\.tap\(point\.x, point\.y\)/u)
  assert.match(burst, /await page\.mouse\.click\(point\.x, point\.y\)/u)
  assert.doesNotMatch(burst, /expect|waitFor|goto|evaluate|locator|boundingBox/u)
  assert.match(rapid, /a\[aria-current="page"\].*\.toHaveCount\(1\)/u)
  assert.match(rapid, /new URL\(page\.url\(\)\)\.pathname\)\.toBe\(path\)/u)
  assert.match(rapid, /path === "\/news" \? newsHeading : eventsTabs\)\.toBeVisible\(\)/u)
  assert.match(rapid, /path === "\/news" \? eventsTabs : newsHeading\)\.toHaveCount\(0\)/u)
  assert.match(rapid, /activation < 2/u)
  assert.match(rapid, /window\.history\.length\)\)\.toBe\(historyLength\)/u)
  assert.match(rapid, /await drawerEvents\.tap\(\)/u)
  assert.match(rapid, /await page\.goBack\(\)\s+await expectCurrentRoute\("\/news"\)/u)
  assert.match(rapid, /await page\.goForward\(\)\s+await expectCurrentRoute\("\/events"\)/u)
  assert.equal((rapid.match(/await expect\(drawer\)\.toHaveCount\(0\)/gu) ?? []).length, 3)
  assert.match(
    rapid,
    /consoleErrorCount, "rapid navigation must not emit console errors"\)\.toBe\(0\)/u
  )
  assert.doesNotMatch(
    rapid,
    /waitForTimeout|setTimeout|dispatchEvent\(|\.route\(|test\.skip|setDefaultTimeout|test\.setTimeout/u
  )
})

test("mobile drawer checks focused layout and stable physical targets without weakening them", () => {
  const start = spec.indexOf('test("mobile drawer traps keyboard focus')
  const end = spec.indexOf("test(", start + 5)
  const drawer = spec.slice(start, end < 0 ? undefined : end)
  const focusAndTrial = drawer.indexOf("await assertDrawerCloseReady(closeButton, width)")
  const physical = drawer.indexOf("const closeSize")
  assert.ok(start >= 0 && focusAndTrial >= 0 && focusAndTrial < physical)
  const helper = spec.slice(spec.indexOf("async function assertDrawerCloseReady("))
  const focus = helper.indexOf("await expect(closeButton).toBeFocused()")
  const layout = helper.indexOf("const layout")
  const trial = helper.indexOf("await closeButton.click({ trial: true })")
  assert.ok(focus >= 0 && focus < layout && layout < trial)
  assert.match(helper, /style\.boxSizing\s*===\s*["']content-box["']/u)
  for (const side of ["Left", "Right", "Top", "Bottom"]) {
    assert.match(helper, new RegExp(`style\\.padding${side}`, "u"))
    assert.match(helper, new RegExp(`style\\.border${side}Width`, "u"))
  }
  for (const dimension of ["width", "height"]) {
    assert.match(
      helper,
      new RegExp(`layout\\.${dimension}[^\\n]*\\.toBeGreaterThanOrEqual\\(44\\)`, "u")
    )
    assert.match(
      drawer,
      new RegExp(`closeSize\\.${dimension}[^\\n]*\\.toBeGreaterThanOrEqual\\(44\\)`, "u")
    )
  }
  assert.match(drawer, /page\.keyboard\.press\(["']Shift\+Tab["']\)/u)
  assert.match(drawer, /page\.keyboard\.press\(["']Tab["']\)/u)
  assert.match(drawer, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(drawer, /previousBodyOverflow/u)
  assert.doesNotMatch(drawer + helper, /waitForTimeout|setTimeout|Math\.round|toBeCloseTo/u)
})

test("drawer frame evidence measures real intervals and rejects invalid samples", async () => {
  const { summarizeDrawerFrames } = await import(
    new URL("./mobile-drawer-rapid.ts", import.meta.url)
  )
  const frames = [
    { timestamp: 100, left: null, opening: null },
    { timestamp: 116, left: 390, opening: 1 },
    { timestamp: 132, left: 240, opening: 1 },
    { timestamp: 182, left: 40, opening: 2 },
    { timestamp: 198, left: null, opening: null },
  ]
  assert.deepEqual(summarizeDrawerFrames(frames), {
    frameCount: 5,
    drawerFrameCount: 3,
    observedOpenings: 2,
    medianMs: 16,
    p95Ms: 50,
    maxMs: 50,
    drawerP95Ms: 16,
    drawerMaxMs: 16,
    travelPx: 350,
  })
  assert.throws(() => summarizeDrawerFrames([]), /two frames/u)
  assert.throws(
    () => summarizeDrawerFrames([frames[1], { timestamp: 116, left: 10, opening: 1 }]),
    /not ordered/u
  )
  assert.throws(
    () => summarizeDrawerFrames([frames[1], { timestamp: Number.NaN, left: 10, opening: 1 }]),
    /invalid drawer frame timestamp/u
  )
  assert.throws(
    () =>
      summarizeDrawerFrames([
        frames[1],
        { timestamp: 117, left: Number.POSITIVE_INFINITY, opening: 1 },
      ]),
    /invalid drawer frame position/u
  )
  assert.throws(
    () => summarizeDrawerFrames([frames[0], { timestamp: 116, left: null, opening: null }]),
    /not observed/u
  )
  assert.throws(
    () => summarizeDrawerFrames([frames[1], { timestamp: 117, left: 10, opening: 2 }]),
    /no consecutive frames/u
  )
})

test("drawer phase evidence is bounded, fail-only, and preserves the first failing stage", async () => {
  const { attachDrawerPhaseOnFailure, createDrawerPhaseTracker } = await import(
    new URL("./mobile-drawer-rapid.ts", import.meta.url)
  )
  const tracker = createDrawerPhaseTracker()
  assert.equal(createDrawerPhaseTracker("chromium").snapshot().browser, "chromium")
  assert.equal(createDrawerPhaseTracker("private-browser").snapshot().browser, "unknown")
  const attachments = []
  const info = {
    status: "passed",
    attach: async (name, attachment) => attachments.push({ name, ...attachment }),
  }
  await attachDrawerPhaseOnFailure(info, tracker)
  info.status = "skipped"
  await attachDrawerPhaseOnFailure(info, tracker)
  info.status = "private-status"
  await attachDrawerPhaseOnFailure(info, tracker)
  assert.equal(attachments.length, 0)

  info.status = "failed"
  await attachDrawerPhaseOnFailure(info, tracker)
  assert.deepEqual(JSON.parse(attachments[0].body), {
    kind: "test-phase",
    schema: 1,
    browser: "unknown",
    input: "unknown",
    motion: "unknown",
    phase: "fixture",
    iteration: null,
    firstFailurePhase: null,
    firstFailureIteration: null,
    status: "failed",
  })
  assert.equal(attachments[0].name, "drawer-input-failure")
  assert.equal(attachments[0].contentType, "application/json")

  tracker.setCase("mouse", "reduce")
  tracker.mark("native-input", 1)
  tracker.fail()
  tracker.mark("probe-stop")
  tracker.fail()
  info.status = "timedOut"
  await attachDrawerPhaseOnFailure(info, tracker)
  assert.deepEqual(JSON.parse(attachments[1].body), {
    kind: "test-phase",
    schema: 1,
    browser: "unknown",
    input: "mouse",
    motion: "reduce",
    phase: "probe-stop",
    iteration: null,
    firstFailurePhase: "native-input",
    firstFailureIteration: 1,
    status: "timedOut",
  })
  tracker.setCase("private-input", "private-motion")
  tracker.mark("private-phase", 9000)
  info.status = "interrupted"
  await attachDrawerPhaseOnFailure(info, tracker)
  const bounded = JSON.parse(attachments[2].body)
  assert.equal(bounded.input, "unknown")
  assert.equal(bounded.motion, "unknown")
  assert.equal(bounded.phase, "probe-stop")
  assert.doesNotMatch(attachments[2].body, /private/u)
  tracker.mark("trigger", 9000)
  assert.equal(tracker.snapshot().iteration, null)
  await assert.doesNotReject(() =>
    attachDrawerPhaseOnFailure(
      {
        status: "failed",
        attach: async () => {
          throw new Error("private-error")
        },
      },
      tracker
    )
  )
})

test("drawer probe preserves native transitions and captures the first bounded pointer miss", async () => {
  const { JSDOM } = await import("jsdom")
  const { installDrawerProbe } = await import(new URL("./mobile-drawer-rapid.ts", import.meta.url))
  const dom = new JSDOM(
    `<button aria-controls="mobile-drawer" aria-expanded="true"></button>
     <div data-brand-boot-loader data-state="exiting"></div>
     <div id="mobile-drawer" role="dialog"><button></button><a id="mobile-nav-link-news"></a></div>`
  )
  const browserWindow = dom.window
  const browserDocument = browserWindow.document
  const savedGlobals = new Map(
    ["window", "document", "Element"].map((name) => [
      name,
      Object.getOwnPropertyDescriptor(globalThis, name),
    ])
  )
  for (const [name, value] of [
    ["window", browserWindow],
    ["document", browserDocument],
    ["Element", browserWindow.Element],
  ]) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }

  try {
    const listeners = new Map()
    const addEventListener = browserDocument.addEventListener.bind(browserDocument)
    const removeEventListener = browserDocument.removeEventListener.bind(browserDocument)
    browserDocument.addEventListener = (name, listener, options) => {
      listeners.set(name, listener)
      return addEventListener(name, listener, options)
    }
    browserDocument.removeEventListener = (name, listener, options) => {
      if (listeners.get(name) === listener) listeners.delete(name)
      return removeEventListener(name, listener, options)
    }
    let cancelledFrame = null
    browserWindow.requestAnimationFrame = () => 7
    browserWindow.cancelAnimationFrame = (frame) => {
      cancelledFrame = frame
    }
    browserWindow.__APP_HYDRATED = true
    Object.defineProperty(browserWindow, "CSS", { value: { supports: () => true } })
    Object.defineProperty(browserWindow, "visualViewport", {
      value: { width: 390, height: 844, offsetLeft: 0, offsetTop: 0, scale: 1 },
    })
    Object.defineProperty(browserWindow, "devicePixelRatio", { value: 2.625 })
    Object.defineProperty(browserDocument.documentElement, "clientWidth", { value: 390 })
    browserDocument.body.style.overflow = "hidden"
    const link = browserDocument.getElementById("mobile-nav-link-news")
    const drawer = browserDocument.getElementById("mobile-drawer")
    link.getBoundingClientRect = () => ({ x: 90, y: 300, width: 200, height: 44 })
    drawer.getBoundingClientRect = () => ({ x: 55, y: 0, width: 320, height: 844 })
    drawer.querySelector("button").focus()
    let hit = link
    browserDocument.elementFromPoint = () => hit
    browserDocument.elementsFromPoint = () => [hit, browserDocument.documentElement]
    browserDocument.getAnimations = () => []
    let active = false
    const htmlMatches = browserDocument.documentElement.matches.bind(
      browserDocument.documentElement
    )
    browserDocument.documentElement.matches = (selector) =>
      selector === ":active-view-transition" ? active : htmlMatches(selector)
    const transition = Object.defineProperties(
      {},
      Object.fromEntries(
        ["ready", "updateCallbackDone", "finished"].map((key) => [
          key,
          { get: () => assert.fail(`probe inspected ${key}`) },
        ])
      )
    )
    let transitionGetterThrows = false
    Object.defineProperty(browserDocument, "activeViewTransition", {
      get: () => {
        if (transitionGetterThrows) throw new Error("diagnostic getter failed")
        return active ? transition : null
      },
    })
    let receiverWasDocument = false
    let nativeArguments
    const failureUpdate = () => {}
    const nativeFailure = new Error("native transition failed")
    const nativeTransition = function (...args) {
      receiverWasDocument = this === browserDocument
      nativeArguments = args
      if (args[0] === failureUpdate) throw nativeFailure
      active = true
      return transition
    }
    browserDocument.startViewTransition = nativeTransition

    installDrawerProbe()
    const probe = browserWindow.__drawerRapidProbe
    assert.throws(() => installDrawerProbe(), /already running/u)
    probe.arm("news", 140, 322)
    const update = () => {}
    assert.equal(browserDocument.startViewTransition(update), transition)
    assert.equal(receiverWasDocument, true)
    assert.deepEqual(nativeArguments, [update])
    assert.throws(
      () => browserDocument.startViewTransition(failureUpdate),
      (error) => error === nativeFailure
    )
    transitionGetterThrows = true
    assert.equal(browserDocument.startViewTransition(update), transition)
    transitionGetterThrows = false
    hit = browserDocument.documentElement
    for (const type of ["pointermove", "pointerdown"]) {
      listeners.get(type)({
        isTrusted: true,
        target: hit,
        type,
        timeStamp: type === "pointermove" ? 120 : 121,
        clientX: 140,
        clientY: 322,
      })
    }
    const result = probe.stop()
    assert.deepEqual(
      result.diagnostic.snapshots.map(({ phase }) => phase),
      ["ready", "pointermove", "pointerdown"]
    )
    assert.equal(result.diagnostic.snapshots[0].target, "news")
    assert.equal(result.diagnostic.firstMiss.target, "root")
    assert.equal(result.diagnostic.firstMiss.hits[0], "root")
    assert.deepEqual(result.diagnostic.firstMiss.link.rect, {
      x: 90,
      y: 300,
      width: 200,
      height: 44,
    })
    assert.deepEqual(result.diagnostic.firstMiss.drawer.rect, {
      x: 55,
      y: 0,
      width: 320,
      height: 844,
    })
    assert.equal(result.diagnostic.firstMiss.focus.target, "drawer")
    assert.equal(result.diagnostic.firstMiss.viewport.devicePixelRatio, 2.625)
    assert.equal(result.diagnostic.firstMiss.viewport.visualScale, 1)
    assert.deepEqual(result.diagnostic.firstMiss.boot, { hydrated: true, phase: "exiting" })
    assert.deepEqual(result.diagnostic.firstMiss.transition, {
      selector: "active",
      activeObject: "present",
      pseudoAnimations: 0,
    })
    assert.ok(result.diagnostic.transitionTimeline.some(({ kind }) => kind === "start"))
    assert.equal(browserDocument.startViewTransition, nativeTransition)
    assert.equal(browserWindow.__drawerRapidProbe, undefined)
    assert.equal(cancelledFrame, 7)
    assert.equal(listeners.has("pointerdown"), false)

    installDrawerProbe()
    const boundedProbe = browserWindow.__drawerRapidProbe
    hit = link
    boundedProbe.arm("news", 140, 322)
    for (let count = 0; count < 30; count += 1) {
      listeners.get("pointermove")({
        isTrusted: true,
        target: link,
        type: "pointermove",
        timeStamp: 200 + count,
        clientX: 140,
        clientY: 322,
      })
    }
    hit = browserDocument.documentElement
    listeners.get("pointerdown")({
      isTrusted: true,
      target: hit,
      type: "pointerdown",
      timeStamp: 300,
      clientX: 140,
      clientY: 322,
    })
    for (let count = 0; count < 60; count += 1) browserDocument.startViewTransition(update)
    const boundedResult = boundedProbe.stop()
    assert.equal(boundedResult.diagnostic.snapshots.length, 24)
    assert.equal(boundedResult.diagnostic.snapshotOverflow, true)
    assert.equal(boundedResult.diagnostic.firstMiss.target, "root")
    assert.equal(boundedResult.diagnostic.transitionTimeline.length, 48)
    assert.equal(boundedResult.diagnostic.transitionOverflow, true)
    assert.equal(browserDocument.startViewTransition, nativeTransition)
  } finally {
    browserWindow.close()
    for (const [name, descriptor] of savedGlobals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  }
})
