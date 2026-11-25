import { expect, test, type Page, type TestInfo } from "@playwright/test"

const DRAWER_PHASES = [
  "fixture",
  "media",
  "mock-api",
  "route",
  "main",
  "overflow",
  "motion-preference",
  "probe-install",
  "trigger",
  "dialog",
  "focus",
  "reduced-motion",
  "hit-point",
  "native-input",
  "drawer-close",
  "final-state",
  "probe-stop",
  "probe-stopped",
  "input-assertions",
  "frame-summary",
  "evidence",
  "complete",
] as const
type DrawerPhase = (typeof DRAWER_PHASES)[number]
type DrawerPhasePoint = { phase: DrawerPhase; iteration: 0 | 1 | 2 | null }
export type DrawerPhaseTracker = {
  mark: (phase: DrawerPhase, iteration?: number) => void
  fail: () => void
  setCase: (input: "touch" | "mouse", motion: "no-preference" | "reduce") => void
  snapshot: () => {
    schema: 1
    browser: "chromium" | "firefox" | "webkit" | "unknown"
    input: "touch" | "mouse" | "unknown"
    motion: "no-preference" | "reduce" | "unknown"
    phase: DrawerPhase
    iteration: 0 | 1 | 2 | null
    firstFailurePhase: DrawerPhase | null
    firstFailureIteration: 0 | 1 | 2 | null
  }
}

/** Keep the failure stage bounded without recording an error, URL, or page content. */
export function createDrawerPhaseTracker(browserName?: unknown): DrawerPhaseTracker {
  const browser =
    browserName === "chromium" || browserName === "firefox" || browserName === "webkit"
      ? browserName
      : "unknown"
  let input: "touch" | "mouse" | "unknown" = "unknown"
  let motion: "no-preference" | "reduce" | "unknown" = "unknown"
  let current: DrawerPhasePoint = { phase: "fixture", iteration: null }
  let firstFailure: DrawerPhasePoint | null = null
  return {
    mark: (phase, iteration) => {
      if (!DRAWER_PHASES.includes(phase)) return
      current = {
        phase,
        iteration: iteration === 0 || iteration === 1 || iteration === 2 ? iteration : null,
      }
    },
    fail: () => {
      firstFailure ??= { ...current }
    },
    setCase: (nextInput, nextMotion) => {
      input = nextInput === "touch" || nextInput === "mouse" ? nextInput : "unknown"
      motion = nextMotion === "no-preference" || nextMotion === "reduce" ? nextMotion : "unknown"
    },
    snapshot: () => ({
      schema: 1,
      browser,
      input,
      motion,
      phase: current.phase,
      iteration: current.iteration,
      firstFailurePhase: firstFailure?.phase ?? null,
      firstFailureIteration: firstFailure?.iteration ?? null,
    }),
  }
}

/** Report only failed or interrupted tests, even if the probe never started. */
export async function attachDrawerPhaseOnFailure(
  info: Pick<TestInfo, "status" | "attach">,
  tracker: DrawerPhaseTracker
): Promise<void> {
  if (info.status !== "failed" && info.status !== "timedOut" && info.status !== "interrupted")
    return
  try {
    await info.attach("drawer-input-failure", {
      body: JSON.stringify({ kind: "test-phase", ...tracker.snapshot(), status: info.status }),
      contentType: "application/json",
    })
  } catch {
    // Failure-only evidence must not replace the test's failure.
  }
}

type DrawerFrame = { timestamp: number; left: number | null; opening: number | null }
type DrawerItem = "news" | "events"
type HitTarget = "trigger" | DrawerItem | "drawer" | "backdrop" | "root" | "body" | "other" | "none"
type Box = { x: number | null; y: number | null; width: number | null; height: number | null }
type ElementMetrics = {
  rect: Box | null
  pointerEvents: "auto" | "none" | "other" | "absent"
  visibility: "visible" | "hidden" | "other" | "absent"
  inert: boolean
}
type TransitionPhase = {
  selector: "active" | "inactive" | "unsupported"
  activeObject: "present" | "absent" | "unsupported"
}
type PointerSnapshot = {
  phase: "ready" | "pointermove" | "pointerdown"
  timestamp: number | null
  expected: DrawerItem
  x: number | null
  y: number | null
  target: HitTarget
  hits: HitTarget[]
  link: ElementMetrics
  drawer: ElementMetrics
  focus: { target: HitTarget; rect: Box | null }
  viewport: {
    innerWidth: number | null
    innerHeight: number | null
    clientWidth: number | null
    devicePixelRatio: number | null
    visualWidth: number | null
    visualHeight: number | null
    visualOffsetLeft: number | null
    visualOffsetTop: number | null
    visualScale: number | null
  }
  transition: TransitionPhase & { pseudoAnimations: number | null }
  boot: { hydrated: boolean; phase: "active" | "exiting" | "hidden" | "other" | "absent" }
  triggerExpanded: boolean | null
  scrollLocked: boolean
}
type DrawerDiagnostic = {
  snapshots: PointerSnapshot[]
  firstMiss: PointerSnapshot | null
  snapshotOverflow: boolean
  transitionTimeline: {
    kind: "start" | "phase"
    timestamp: number | null
    phase: TransitionPhase
  }[]
  transitionOverflow: boolean
}
type DrawerInput = {
  kind: "pointerdown" | "pointerup" | "click"
  target: "trigger" | "news" | "events" | "other"
  timestamp: number
  x: number
  y: number
  other?: {
    root: boolean
    insideDrawer: boolean
    hitLink: boolean
    viewTransitionAnimations: number
  }
}
type DrawerProbe = {
  arm: (item: DrawerItem, x: number, y: number) => void
  stop: () => {
    frames: DrawerFrame[]
    inputs: DrawerInput[]
    overflow: boolean
    diagnostic: DrawerDiagnostic
  }
}
type DrawerProbeWindow = Window & { __drawerRapidProbe?: DrawerProbe }

/** Summarize real browser frame timestamps without inventing an FPS budget. */
export function summarizeDrawerFrames(frames: DrawerFrame[]) {
  if (frames.length < 2) throw new Error("drawer frame probe did not observe two frames")
  const intervals: number[] = []
  const drawerIntervals: number[] = []
  const positions: number[] = []
  const openings = new Set<number>()
  for (const [index, frame] of frames.entries()) {
    if (!Number.isFinite(frame.timestamp)) throw new Error("invalid drawer frame timestamp")
    if (frame.left !== null) {
      if (
        !Number.isFinite(frame.left) ||
        !Number.isSafeInteger(frame.opening) ||
        frame.opening! < 1
      )
        throw new Error("invalid drawer frame position or opening")
      positions.push(frame.left)
      openings.add(frame.opening!)
    } else if (frame.opening !== null) {
      throw new Error("invalid drawer frame position or opening")
    }
    if (index > 0) {
      const previous = frames[index - 1]!
      const delta = frame.timestamp - previous.timestamp
      if (!Number.isFinite(delta) || delta <= 0) throw new Error("drawer frames are not ordered")
      intervals.push(delta)
      if (frame.opening !== null && frame.opening === previous.opening) drawerIntervals.push(delta)
    }
  }
  if (positions.length < 2) throw new Error("drawer was not observed in two frames")
  if (drawerIntervals.length < 1) throw new Error("no consecutive frames observed one opening")
  intervals.sort((a, b) => a - b)
  drawerIntervals.sort((a, b) => a - b)
  return {
    frameCount: frames.length,
    drawerFrameCount: positions.length,
    observedOpenings: openings.size,
    medianMs: intervals[Math.floor((intervals.length - 1) * 0.5)]!,
    p95Ms: intervals[Math.ceil(intervals.length * 0.95) - 1]!,
    maxMs: intervals[intervals.length - 1]!,
    drawerP95Ms: drawerIntervals[Math.ceil(drawerIntervals.length * 0.95) - 1]!,
    drawerMaxMs: drawerIntervals[drawerIntervals.length - 1]!,
    travelPx: Math.max(...positions) - Math.min(...positions),
  }
}

/** Install a bounded browser probe; the native transition result is never observed or altered. */
export function installDrawerProbe(): void {
  const probeWindow = window as DrawerProbeWindow
  if (probeWindow.__drawerRapidProbe) throw new Error("drawer frame probe is already running")
  const frames: DrawerFrame[] = []
  const inputs: DrawerInput[] = []
  const diagnostic: DrawerDiagnostic = {
    snapshots: [],
    firstMiss: null,
    snapshotOverflow: false,
    transitionTimeline: [],
    transitionOverflow: false,
  }
  let overflow = false
  let frameId = 0
  let previousDrawer: HTMLElement | null = null
  let opening = 0
  let expected: DrawerItem | null = null
  let previousPhase = ""

  const bounded = (value: number | undefined): number | null =>
    value !== undefined && Number.isFinite(value) && Math.abs(value) <= 1_000_000 ? value : null
  const box = (element: Element | null): Box | null => {
    if (!element) return null
    const rect = element.getBoundingClientRect()
    return {
      x: bounded(rect.x),
      y: bounded(rect.y),
      width: bounded(rect.width),
      height: bounded(rect.height),
    }
  }
  const classify = (element: Element | null): HitTarget => {
    if (!element) return "none"
    if (element.closest('button[aria-controls="mobile-drawer"]')) return "trigger"
    if (element.closest("#mobile-nav-link-news")) return "news"
    if (element.closest("#mobile-nav-link-events")) return "events"
    if (element.closest("#mobile-drawer")) return "drawer"
    if (element.closest('[data-testid="mobile-menu-backdrop"]')) return "backdrop"
    if (element === document.documentElement) return "root"
    if (element === document.body) return "body"
    return "other"
  }
  const metrics = (element: Element | null): ElementMetrics => {
    if (!element) return { rect: null, pointerEvents: "absent", visibility: "absent", inert: false }
    const style = window.getComputedStyle(element)
    return {
      rect: box(element),
      pointerEvents:
        style.pointerEvents === "auto" || style.pointerEvents === "none"
          ? style.pointerEvents
          : "other",
      visibility:
        style.visibility === "visible" || style.visibility === "hidden"
          ? style.visibility
          : "other",
      inert: element.closest("[inert]") !== null,
    }
  }
  const transitionPhase = (): TransitionPhase => {
    let selector: TransitionPhase["selector"] = "unsupported"
    try {
      if (window.CSS?.supports?.("selector(:active-view-transition)")) {
        selector = document.documentElement.matches(":active-view-transition")
          ? "active"
          : "inactive"
      }
    } catch {
      selector = "unsupported"
    }
    const transitionDocument = document as Document & { activeViewTransition?: unknown }
    let activeObject: TransitionPhase["activeObject"] = "unsupported"
    try {
      if ("activeViewTransition" in transitionDocument) {
        activeObject = transitionDocument.activeViewTransition ? "present" : "absent"
      }
    } catch {
      activeObject = "unsupported"
    }
    return { selector, activeObject }
  }
  const addTransition = (kind: "start" | "phase", timestamp: number, phase: TransitionPhase) => {
    if (diagnostic.transitionTimeline.length < 48) {
      diagnostic.transitionTimeline.push({ kind, timestamp: bounded(timestamp), phase })
    } else {
      diagnostic.transitionOverflow = true
    }
  }
  const recordPhase = (timestamp: number) => {
    const phase = transitionPhase()
    const key = `${phase.selector}/${phase.activeObject}`
    if (key !== previousPhase) {
      previousPhase = key
      addTransition("phase", timestamp, phase)
    }
    return phase
  }

  // Preserve the native arguments, receiver, return value, and promise handling.
  const originalTransition = document.startViewTransition
  let observedTransition: typeof document.startViewTransition | undefined
  if (typeof originalTransition === "function") {
    const observe: typeof document.startViewTransition = function (
      this: Document,
      ...args: Parameters<Document["startViewTransition"]>
    ) {
      const result = Reflect.apply(originalTransition, this, args) as ViewTransition
      try {
        addTransition("start", window.performance.now(), transitionPhase())
      } catch {
        diagnostic.transitionOverflow = true
      }
      return result
    }
    try {
      document.startViewTransition = observe
      observedTransition = observe
    } catch {
      // A non-writable browser implementation remains usable; phase sampling still works.
    }
  }

  const snapshot = (
    phase: PointerSnapshot["phase"],
    timestamp: number,
    item: DrawerItem,
    x: number,
    y: number,
    target: Element | null
  ): PointerSnapshot => {
    const link = document.getElementById(`mobile-nav-link-${item}`)
    const drawer = document.getElementById("mobile-drawer")
    const focus = document.activeElement
    const visual = window.visualViewport
    const loader = document.querySelector<HTMLElement>("[data-brand-boot-loader]")
    const loaderPhase = loader?.getAttribute("data-state")
    const bootPhase = !loader
      ? "absent"
      : loaderPhase === "active" || loaderPhase === "exiting" || loaderPhase === "hidden"
        ? loaderPhase
        : "other"
    const expanded = document
      .querySelector('button[aria-controls="mobile-drawer"]')
      ?.getAttribute("aria-expanded")
    let pseudoAnimations: number | null = null
    try {
      pseudoAnimations = Math.min(
        100,
        document.getAnimations().filter((animation) => {
          const effect = animation.effect
          return (
            effect instanceof KeyframeEffect &&
            (effect.pseudoElement ?? "").startsWith("::view-transition")
          )
        }).length
      )
    } catch {
      // The selector and native-object state still provide passive evidence.
    }
    const hits = document.elementsFromPoint(x, y).slice(0, 6).map(classify)
    return {
      phase,
      timestamp: bounded(timestamp),
      expected: item,
      x: bounded(x),
      y: bounded(y),
      target: classify(target),
      hits,
      link: metrics(link),
      drawer: metrics(drawer),
      focus: { target: classify(focus), rect: box(focus) },
      viewport: {
        innerWidth: bounded(window.innerWidth),
        innerHeight: bounded(window.innerHeight),
        clientWidth: bounded(document.documentElement.clientWidth),
        devicePixelRatio: bounded(window.devicePixelRatio),
        visualWidth: bounded(visual?.width),
        visualHeight: bounded(visual?.height),
        visualOffsetLeft: bounded(visual?.offsetLeft),
        visualOffsetTop: bounded(visual?.offsetTop),
        visualScale: bounded(visual?.scale),
      },
      transition: { ...recordPhase(timestamp), pseudoAnimations },
      boot: { hydrated: window.__APP_HYDRATED === true, phase: bootPhase },
      triggerExpanded: expanded === "true" ? true : expanded === "false" ? false : null,
      scrollLocked: document.body.style.overflow === "hidden",
    }
  }
  const addSnapshot = (entry: PointerSnapshot) => {
    if (diagnostic.snapshots.length < 24) diagnostic.snapshots.push(entry)
    else diagnostic.snapshotOverflow = true
  }
  const onInput = (event: MouseEvent) => {
    if (!event.isTrusted || !(event.target instanceof Element)) return
    if (
      expected &&
      !diagnostic.firstMiss &&
      (event.type === "pointermove" || event.type === "pointerdown")
    ) {
      const entry = snapshot(
        event.type,
        event.timeStamp,
        expected,
        event.clientX,
        event.clientY,
        event.target
      )
      addSnapshot(entry)
      if (event.type === "pointerdown") {
        if (entry.target !== expected) diagnostic.firstMiss = entry
        expected = null
      }
    }
    if (event.type === "pointermove") return
    let target: DrawerInput["target"] = "other"
    if (event.target.closest('button[aria-controls="mobile-drawer"]')) target = "trigger"
    else if (event.target.closest("#mobile-nav-link-news")) target = "news"
    else if (event.target.closest("#mobile-nav-link-events")) target = "events"
    if (inputs.length < 100)
      inputs.push({
        kind: event.type as DrawerInput["kind"],
        target,
        timestamp: event.timeStamp,
        x: event.clientX,
        y: event.clientY,
        ...(target === "other"
          ? {
              other: {
                root: event.target === document.documentElement,
                insideDrawer: Boolean(event.target.closest("#mobile-drawer")),
                hitLink: Boolean(
                  document
                    .elementFromPoint(event.clientX, event.clientY)
                    ?.closest("#mobile-nav-link-news, #mobile-nav-link-events")
                ),
                viewTransitionAnimations: document.getAnimations().filter((animation) => {
                  const effect = animation.effect
                  return (
                    effect instanceof KeyframeEffect &&
                    (effect.pseudoElement ?? "").startsWith("::view-transition")
                  )
                }).length,
              },
            }
          : {}),
      })
  }
  const sample = (timestamp: number) => {
    recordPhase(timestamp)
    const drawer = document.querySelector<HTMLElement>('#mobile-drawer[role="dialog"]')
    if (drawer && drawer !== previousDrawer) opening += 1
    previousDrawer = drawer
    if (frames.length < 1200) {
      frames.push({
        timestamp,
        left: drawer?.getBoundingClientRect().left ?? null,
        opening: drawer ? opening : null,
      })
    } else {
      overflow = true
    }
    frameId = window.requestAnimationFrame(sample)
  }
  document.addEventListener("pointermove", onInput, true)
  document.addEventListener("pointerdown", onInput, true)
  document.addEventListener("pointerup", onInput, true)
  document.addEventListener("click", onInput, true)
  frameId = window.requestAnimationFrame(sample)
  probeWindow.__drawerRapidProbe = {
    arm: (item, x, y) => {
      expected = item
      if (!diagnostic.firstMiss) {
        addSnapshot(
          snapshot("ready", window.performance.now(), item, x, y, document.elementFromPoint(x, y))
        )
      }
    },
    stop: () => {
      window.cancelAnimationFrame(frameId)
      document.removeEventListener("pointermove", onInput, true)
      document.removeEventListener("pointerdown", onInput, true)
      document.removeEventListener("pointerup", onInput, true)
      document.removeEventListener("click", onInput, true)
      if (observedTransition && document.startViewTransition === observedTransition) {
        document.startViewTransition = originalTransition
      }
      delete probeWindow.__drawerRapidProbe
      return { frames, inputs, overflow, diagnostic }
    },
  }
}

async function startDrawerProbe(page: Page): Promise<void> {
  await page.evaluate(installDrawerProbe)
}

async function stopDrawerProbe(page: Page) {
  return page.evaluate(() => {
    const probe = (window as DrawerProbeWindow).__drawerRapidProbe
    if (!probe) throw new Error("drawer frame probe is missing")
    return probe.stop()
  })
}

/** Find a real hit point as soon as the opening drawer exposes the requested item. */
async function drawerItemHitPoint(page: Page, item: "news" | "events") {
  const handle = await page.waitForFunction((name) => {
    const link = document.getElementById(`mobile-nav-link-${name}`)
    if (!link || !link.closest('#mobile-drawer[role="dialog"]')) return null
    const rect = link.getBoundingClientRect()
    if (
      rect.width < 44 ||
      rect.height < 44 ||
      rect.left < 0 ||
      rect.right > document.documentElement.clientWidth ||
      rect.top < 0 ||
      rect.bottom > innerHeight
    )
      return null
    const x = rect.left + rect.width / 4
    const y = (rect.top + rect.bottom) / 2
    const hit = document.elementFromPoint(x, y)
    if (!hit || !link.contains(hit)) return null
    const probe = (window as DrawerProbeWindow).__drawerRapidProbe
    if (!probe) throw new Error("drawer frame probe is missing")
    probe.arm(name, x, y)
    return { x, y }
  }, item)
  const point = await handle.jsonValue()
  await handle.dispose()
  if (!point) throw new Error("drawer item has no available hit point")
  return point
}

/** Exercise distinct drawer items without waiting for an intermediate route to settle. */
export async function verifyRapidDrawerNavigation(
  page: Page,
  hasTouch: boolean,
  phase?: DrawerPhaseTracker
): Promise<void> {
  const trigger = page.locator('button[aria-controls="mobile-drawer"]')
  const drawer = page.locator('#mobile-drawer[role="dialog"]')
  const bottomNavigation = page.locator('nav:has(a[data-tab-key="/dashboard"])')
  phase?.mark("overflow")
  const originalOverflow = await page.evaluate(() => document.body.style.overflow)
  phase?.mark("motion-preference")
  const reduced = await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)
  phase?.mark("probe-install")
  await startDrawerProbe(page)
  let result: Awaited<ReturnType<typeof stopDrawerProbe>>
  let failure: unknown
  try {
    for (const [index, item] of (["news", "events", "news"] as const).entries()) {
      phase?.mark("trigger", index)
      if (hasTouch) await trigger.tap()
      else await trigger.click()
      phase?.mark("dialog", index)
      await expect(drawer).toHaveAttribute("aria-modal", "true")
      if (index === 0) {
        phase?.mark("focus", index)
        await expect(drawer.getByRole("button").first()).toBeFocused()
        if (reduced) {
          phase?.mark("reduced-motion", index)
          await page.evaluate(
            () =>
              new Promise<void>((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
              )
          )
          const drawerTranslation = await drawer.evaluate((element) => {
            const transform = getComputedStyle(element).transform
            return transform === "none" ? 0 : new DOMMatrixReadOnly(transform).m41
          })
          expect(drawerTranslation).toBeCloseTo(0, 0)
          await expect(bottomNavigation.locator("[data-nav-indicator]")).toHaveCSS(
            "transition-duration",
            "0s"
          )
        }
      }
      phase?.mark("hit-point", index)
      const point = await drawerItemHitPoint(page, item)
      phase?.mark("native-input", index)
      if (hasTouch) await page.touchscreen.tap(point.x, point.y)
      else await page.mouse.click(point.x, point.y)
      phase?.mark("drawer-close", index)
      await expect(drawer).toBeHidden()
    }
    phase?.mark("final-state")
    await expect.poll(() => new URL(page.url()).pathname).toBe("/news")
    await expect(bottomNavigation.locator('a[aria-current="page"]')).toHaveCount(1)
    await expect(bottomNavigation.locator('a[data-tab-key="/news"]')).toHaveAttribute(
      "aria-current",
      "page"
    )
    await expect(
      page.getByRole("main").getByRole("heading", {
        name: /^(?:Новости университета|University news)[ 0-9]*$/u,
      })
    ).toBeVisible()
    await expect(trigger).toHaveAttribute("aria-expanded", "false")
    await expect
      .poll(() => page.evaluate(() => document.body.style.overflow))
      .toBe(originalOverflow)
  } catch (error) {
    phase?.fail()
    failure = error
  } finally {
    phase?.mark("probe-stop")
    result = await stopDrawerProbe(page)
    phase?.mark("probe-stopped")
  }

  if (failure !== undefined || result.diagnostic.firstMiss !== null) {
    try {
      await test.info().attach("drawer-input-failure", {
        body: JSON.stringify({
          inputs: result.inputs,
          frames: result.frames.length,
          diagnostic: result.diagnostic,
        }),
        contentType: "application/json",
      })
    } catch {
      // A diagnostic failure must not replace the navigation assertion.
    }
  }
  if (failure !== undefined) throw failure
  phase?.mark("input-assertions")
  expect(result.overflow, "bounded frame capture must not truncate the interaction").toBe(false)
  const clicks = result.inputs.filter(({ kind }) => kind === "click")
  expect(
    clicks.map(({ target }) => target),
    "each native activation must reach its intended control"
  ).toEqual(["trigger", "news", "trigger", "events", "trigger", "news"])
  const selectionGapsMs = [
    clicks[3]!.timestamp - clicks[1]!.timestamp,
    clicks[5]!.timestamp - clicks[3]!.timestamp,
  ]
  expect(selectionGapsMs.every((gap) => Number.isFinite(gap) && gap > 0)).toBe(true)
  phase?.mark("frame-summary")
  const evidence = summarizeDrawerFrames(result.frames)
  if (!reduced)
    expect(evidence.travelPx, "drawer must visibly move between frames").toBeGreaterThan(1)
  const width = page.viewportSize()?.width ?? 0
  phase?.mark("evidence")
  await test.info().attach(`drawer-frame-timing-${width}-${reduced ? "reduced" : "normal"}`, {
    body: JSON.stringify({
      width,
      reduced,
      input: hasTouch ? "touch" : "mouse",
      selectionGapsMs,
      ...evidence,
    }),
    contentType: "application/json",
  })
  phase?.mark("complete")
}
