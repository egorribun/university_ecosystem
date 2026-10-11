import {
  SERVICE_WORKER_BOOTSTRAP_EVENT,
  type ServiceWorkerBootstrapEventDetail,
} from "../../src/app/pwaEvents"
import { expect, loginAs, ownedSessionOrigin } from "./fixtures"
import type { CDPSession, Page } from "@playwright/test"
import {
  markStorySetupStage,
  openStoryBackgroundTab,
  recordStorySetupCleanupFailure,
  recordStorySetupFailure,
  storyVisibilityTest,
} from "./story-visibility-fixtures"

const SEEDED_STORY_TITLE = /(?:Сессия: советы по подготовке|Exam season: preparation tips)/u
const WARM_UP_CYCLES = 1
const MEASURED_CYCLES = 20
const HEAP_PLATEAU_TOLERANCE_BYTES = 512 * 1024

type DOMCounters = {
  documents: number
  nodes: number
  jsEventListeners: number
}

type MemorySnapshot = {
  domCounters: DOMCounters
  jsHeapUsedBytes: number
}

type StoryBootstrapStatus = ServiceWorkerBootstrapEventDetail["status"] | null
type StoryBootstrapProbeWindow = Window & {
  __ueServiceWorkerBootstrapStatus?: StoryBootstrapStatus
}

const STORY_MEMORY_DIAGNOSTIC_SCHEMA = 1
const STORY_MEMORY_DIAGNOSTIC_PREFIX = "STORY_MEMORY_DIAG "
const STORY_MEMORY_LISTENER_EVENTS = [
  "visibilitychange",
  "focus",
  "blur",
  "focusin",
  "focusout",
  "keydown",
  "keyup",
  "click",
  "mousedown",
  "mouseup",
  "pointerdown",
  "pointerup",
  "touchstart",
  "touchend",
  "online",
  "offline",
  "resize",
  "scroll",
] as const

type StoryMemoryDiagnosticProject = "desktop" | "mobile"
type StoryMemoryListenerEvent = (typeof STORY_MEMORY_LISTENER_EVENTS)[number]
type StoryMemoryListenerBucket = "other" | StoryMemoryListenerEvent
type StoryMemoryListenerMetric = "total" | StoryMemoryListenerBucket
type StoryMemoryListenerCounts = Record<StoryMemoryListenerMetric, number>
type StoryMemoryDiagnosticListenerCounts = Record<StoryMemoryListenerMetric, number | null>
type StoryMemoryListenerBuckets = {
  window: StoryMemoryListenerCounts
  document: StoryMemoryListenerCounts
  documentTree: StoryMemoryListenerCounts
}
type StoryMemoryDiagnosticListeners = {
  window: StoryMemoryDiagnosticListenerCounts
  document: StoryMemoryDiagnosticListenerCounts
  documentTree: StoryMemoryDiagnosticListenerCounts
}
type StoryMemoryDiagnosticDOM = {
  documents: number | null
  nodes: number | null
  jsEventListeners: number | null
}
type StoryMemoryDiagnosticRecord = {
  schema: 1
  project: StoryMemoryDiagnosticProject
  phase: "cycle0-after-settle-before-assertion"
  diagnosticStatus: "available" | "unavailable"
  warmDOM: StoryMemoryDiagnosticDOM
  cycle0DOM: StoryMemoryDiagnosticDOM
  warmListeners: StoryMemoryDiagnosticListeners
  cycle0Listeners: StoryMemoryDiagnosticListeners
}
type StoryMemoryRemoteObject = { objectId?: string }
type StoryMemoryEventListener = {
  type: string
  handler?: StoryMemoryRemoteObject
  originalHandler?: StoryMemoryRemoteObject
}

function newStoryMemoryListenerCounts<Value extends number | null>(
  value: Value
): Record<StoryMemoryListenerMetric, Value> {
  return {
    total: value,
    other: value,
    visibilitychange: value,
    focus: value,
    blur: value,
    focusin: value,
    focusout: value,
    keydown: value,
    keyup: value,
    click: value,
    mousedown: value,
    mouseup: value,
    pointerdown: value,
    pointerup: value,
    touchstart: value,
    touchend: value,
    online: value,
    offline: value,
    resize: value,
    scroll: value,
  }
}

async function readStoryMemoryListenerCounts(
  cdp: CDPSession,
  targetName: "window" | "document" | "documentTree",
  expression: "window" | "document" | "document.documentElement",
  depth: 0 | -1
): Promise<StoryMemoryListenerCounts> {
  const objectGroup = "story-memory-" + targetName
  const remoteObjectIds = new Set<string>()
  let counts: StoryMemoryListenerCounts | null = null
  let readFailed = false
  let releaseFailed = false
  try {
    const evaluation = (await cdp.send("Runtime.evaluate", {
      expression,
      objectGroup,
      returnByValue: false,
      generatePreview: false,
    })) as { result?: StoryMemoryRemoteObject }
    const objectId = evaluation.result?.objectId
    if (typeof objectId !== "string") {
      throw new Error("Story listener target unavailable")
    }
    remoteObjectIds.add(objectId)

    const response = (await cdp.send("DOMDebugger.getEventListeners", {
      objectId,
      depth,
      pierce: false,
    })) as { listeners?: StoryMemoryEventListener[] }
    if (!Array.isArray(response.listeners)) {
      throw new Error("Story listener list unavailable")
    }
    for (const listener of response.listeners) {
      for (const remote of [listener.handler, listener.originalHandler]) {
        if (typeof remote?.objectId === "string") {
          remoteObjectIds.add(remote.objectId)
        }
      }
    }

    const listenerCounts: StoryMemoryListenerCounts = newStoryMemoryListenerCounts<number>(0)
    const knownEvents = new Set<string>(STORY_MEMORY_LISTENER_EVENTS)
    for (const listener of response.listeners) {
      const metric: StoryMemoryListenerBucket = knownEvents.has(listener.type)
        ? (listener.type as StoryMemoryListenerEvent)
        : "other"
      listenerCounts.total += 1
      listenerCounts[metric] += 1
    }
    counts = listenerCounts
  } catch {
    readFailed = true
  } finally {
    for (const objectId of remoteObjectIds) {
      try {
        await cdp.send("Runtime.releaseObject", { objectId })
      } catch {
        releaseFailed = true
      }
    }
    try {
      await cdp.send("Runtime.releaseObjectGroup", { objectGroup })
    } catch {
      releaseFailed = true
    }
  }
  if (readFailed || releaseFailed || counts === null) {
    throw new Error("Story listener diagnostic unavailable")
  }
  return counts
}

async function captureStoryMemoryListeners(
  cdp: CDPSession
): Promise<StoryMemoryListenerBuckets | null> {
  try {
    const window = await readStoryMemoryListenerCounts(cdp, "window", "window", 0)
    const document = await readStoryMemoryListenerCounts(cdp, "document", "document", 0)
    const documentTree = await readStoryMemoryListenerCounts(
      cdp,
      "documentTree",
      "document.documentElement",
      -1
    )
    return { window, document, documentTree }
  } catch {
    return null
  }
}

function safeStoryMemoryDOM(counters: DOMCounters): StoryMemoryDiagnosticDOM | null {
  const values = [counters.documents, counters.nodes, counters.jsEventListeners]
  if (!values.every((value) => Number.isSafeInteger(value) && value >= 0)) {
    return null
  }
  return {
    documents: counters.documents,
    nodes: counters.nodes,
    jsEventListeners: counters.jsEventListeners,
  }
}

function safeStoryMemoryListeners(buckets: StoryMemoryListenerBuckets): boolean {
  return Object.values(buckets).every((counts) =>
    Object.values(counts).every((value) => Number.isSafeInteger(value) && value >= 0)
  )
}

function unavailableStoryMemoryListeners(): StoryMemoryDiagnosticListeners {
  return {
    window: newStoryMemoryListenerCounts(null),
    document: newStoryMemoryListenerCounts(null),
    documentTree: newStoryMemoryListenerCounts(null),
  }
}

function emitStoryMemoryDiagnosticRecord(
  projectName: string,
  warmSnapshot: MemorySnapshot,
  cycle0Snapshot: MemorySnapshot,
  warmListeners: StoryMemoryListenerBuckets | null,
  cycle0Listeners: StoryMemoryListenerBuckets | null
): void {
  const project = projectName === "desktop" || projectName === "mobile" ? projectName : undefined
  if (!project) return

  const warmDOM = safeStoryMemoryDOM(warmSnapshot.domCounters)
  const cycle0DOM = safeStoryMemoryDOM(cycle0Snapshot.domCounters)
  let record: StoryMemoryDiagnosticRecord
  if (
    warmDOM !== null &&
    cycle0DOM !== null &&
    warmListeners !== null &&
    cycle0Listeners !== null &&
    safeStoryMemoryListeners(warmListeners) &&
    safeStoryMemoryListeners(cycle0Listeners)
  ) {
    record = {
      schema: STORY_MEMORY_DIAGNOSTIC_SCHEMA,
      project,
      phase: "cycle0-after-settle-before-assertion",
      diagnosticStatus: "available",
      warmDOM,
      cycle0DOM,
      warmListeners,
      cycle0Listeners,
    }
  } else {
    record = {
      schema: STORY_MEMORY_DIAGNOSTIC_SCHEMA,
      project,
      phase: "cycle0-after-settle-before-assertion",
      diagnosticStatus: "unavailable",
      warmDOM: { documents: null, nodes: null, jsEventListeners: null },
      cycle0DOM: { documents: null, nodes: null, jsEventListeners: null },
      warmListeners: unavailableStoryMemoryListeners(),
      cycle0Listeners: unavailableStoryMemoryListeners(),
    }
  }
  try {
    process.stdout.write(`${STORY_MEMORY_DIAGNOSTIC_PREFIX}${JSON.stringify(record)}\n`)
  } catch {
    // Diagnostics must not change the acceptance outcome.
  }
}

async function settleViewerCleanup(page: Page, cdp: CDPSession): Promise<MemorySnapshot> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()))
      })
  )
  await cdp.send("HeapProfiler.collectGarbage")
  const [domCounters, heapUsage] = await Promise.all([
    cdp.send("Memory.getDOMCounters") as Promise<DOMCounters>,
    cdp.send("Runtime.getHeapUsage") as Promise<{ usedSize: number }>,
  ])
  return { domCounters, jsHeapUsedBytes: heapUsage.usedSize }
}

storyVisibilityTest(
  "a seeded story viewer reaches a memory plateau after 20 open-close cycles",
  async ({ page }, testInfo) => {
    try {
      markStorySetupStage(page, "bootstrap-listener")
      await page.addInitScript((eventName: string) => {
        const observedWindow = window as StoryBootstrapProbeWindow
        observedWindow.__ueServiceWorkerBootstrapStatus = null
        window.addEventListener(
          eventName,
          (event) => {
            observedWindow.__ueServiceWorkerBootstrapStatus = (
              event as CustomEvent<ServiceWorkerBootstrapEventDetail>
            ).detail.status
          },
          { once: true }
        )
      }, SERVICE_WORKER_BOOTSTRAP_EVENT)
      markStorySetupStage(page, "login")
      await loginAs(page, "student")
      markStorySetupStage(page, "dashboard")
      await page.goto(new URL("/dashboard", ownedSessionOrigin()).toString())
      markStorySetupStage(page, "bootstrap")
      await page.waitForFunction(() => {
        const status = (window as StoryBootstrapProbeWindow).__ueServiceWorkerBootstrapStatus
        return status !== null && status !== undefined
      })
      const serviceWorkerBootstrapStatus = await page.evaluate(
        () => (window as StoryBootstrapProbeWindow).__ueServiceWorkerBootstrapStatus
      )
      expect(serviceWorkerBootstrapStatus).toBe("ready")

      markStorySetupStage(page, "story-trigger")
      const trigger = page.getByRole("button", { name: SEEDED_STORY_TITLE })
      const dialog = page.getByRole("dialog")
      await expect(trigger).toBeVisible()
      const storyWriteRequests: string[] = []
      page.on("request", (request) => {
        const requestUrl = new URL(request.url())
        if (
          requestUrl.pathname.startsWith("/api/v1/stories") &&
          !["GET", "HEAD"].includes(request.method())
        ) {
          storyWriteRequests.push(`${request.method()} ${requestUrl.pathname}`)
        }
      })
      markStorySetupStage(page, "baseline")
      const initialBodyOverflow = await page.locator("body").evaluate((body) => body.style.overflow)
      const cdp = await page.context().newCDPSession(page)

      const openAndClose = async (verifyHiddenPause = false): Promise<MemorySnapshot> => {
        await trigger.click()
        await expect(dialog).toBeVisible()
        await expect(dialog).toHaveCount(1)
        await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)

        const activeProgress = dialog.locator('[role="progressbar"][aria-live="polite"]')
        const readProgress = async () => Number(await activeProgress.getAttribute("aria-valuenow"))
        await expect.poll(readProgress).toBeGreaterThan(0)

        if (verifyHiddenPause) {
          const backgroundPage = await openStoryBackgroundTab(page)
          try {
            await backgroundPage.goto("about:blank")
            await backgroundPage.bringToFront()
            await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
            const hiddenProgress = await readProgress()
            await backgroundPage.waitForTimeout(1_000)
            expect(await readProgress()).toBe(hiddenProgress)

            await page.bringToFront()
            await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible")
            await expect.poll(readProgress).toBeGreaterThan(hiddenProgress)
          } finally {
            await backgroundPage.close()
            await page.bringToFront()
          }
        }

        await page.keyboard.press("Escape")
        await expect(dialog).toHaveCount(0)
        await expect(trigger).toBeFocused()
        await expect
          .poll(() => page.locator("body").evaluate((body) => body.style.overflow))
          .toBe(initialBodyOverflow)

        return settleViewerCleanup(page, cdp)
      }

      let bodyFailed = false
      let bodyError: unknown
      try {
        markStorySetupStage(page, "warm-up")
        for (let cycle = 0; cycle < WARM_UP_CYCLES; cycle += 1) {
          await openAndClose()
        }

        markStorySetupStage(page, "baseline")
        const warmSnapshot = await settleViewerCleanup(page, cdp)
        const warmListenerCounts = await captureStoryMemoryListeners(cdp)
        const measuredHeapSamples: number[] = []
        for (let cycle = 0; cycle < MEASURED_CYCLES; cycle += 1) {
          markStorySetupStage(page, cycle === 0 ? "cycle0" : "measured-cycle")
          const snapshot = await openAndClose(cycle === 0)
          if (cycle === 0) {
            const cycleListenerCounts =
              warmListenerCounts === null ? null : await captureStoryMemoryListeners(cdp)
            emitStoryMemoryDiagnosticRecord(
              testInfo.project.name,
              warmSnapshot,
              snapshot,
              warmListenerCounts,
              cycleListenerCounts
            )
          }
          markStorySetupStage(page, "acceptance")
          expect(snapshot.domCounters).toEqual(warmSnapshot.domCounters)
          measuredHeapSamples.push(snapshot.jsHeapUsedBytes)
        }
        markStorySetupStage(page, "acceptance")
        expect(storyWriteRequests).toEqual([])

        const earlyHeapMean =
          measuredHeapSamples.slice(0, 5).reduce((total, bytes) => total + bytes, 0) / 5
        const lateHeapMean =
          measuredHeapSamples.slice(-5).reduce((total, bytes) => total + bytes, 0) / 5
        expect(lateHeapMean).toBeLessThanOrEqual(earlyHeapMean + HEAP_PLATEAU_TOLERANCE_BYTES)
      } catch (error) {
        recordStorySetupFailure(page, error)
        bodyFailed = true
        bodyError = error
      }

      let cleanupFailed = false
      let cleanupError: unknown
      try {
        await cdp.detach()
      } catch (error) {
        recordStorySetupCleanupFailure(page)
        cleanupFailed = true
        cleanupError = error
      }
      if (bodyFailed) throw bodyError
      if (cleanupFailed) throw cleanupError
    } catch (error) {
      recordStorySetupFailure(page, error)
      throw error
    }
  }
)
