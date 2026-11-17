import { expect, loginAs, test } from "./fixtures"
import { reportMapZoomLongTasks } from "./map-zoom-longtask-diagnostic"
import { stopLongTaskMeasurement } from "./map-zoom-longtask-measurement"
import type {
  LongTaskSample,
  MeasuredLongTaskSample,
  WindowWithMapZoomObserver,
} from "./map-zoom-longtask-measurement"
import type { Page, Request } from "@playwright/test"

const MAP_URL = "/map?z=17&lat=55.7144&lng=37.81478&p=0&b=0"
const MAP_RESOURCE_HOST = "tiles.openfreemap.org"
const LONG_TASK_THRESHOLD_MS = 50
const ZOOM_STEPS = 3

// The public tile host is outside the stand's control, so its style and vector
// tiles are pinned to a local fixture. MapLibre itself still runs for real: it
// parses this style, requests the tile through the same URL template, and
// renders the canvas that the zoom control and long-task observer exercise.
const deterministicStyle = {
  version: 8,
  sources: {
    openmaptiles: {
      type: "vector",
      tiles: [`https://${MAP_RESOURCE_HOST}/data/v3/{z}/{x}/{y}.pbf`],
      minzoom: 0,
      maxzoom: 14,
    },
  },
  layers: [{ id: "background", type: "background", paint: { "background-color": "#f4f6f8" } }],
}

interface MapCamera {
  zoom: number
  latitude: number
  longitude: number
}

async function readCamera(page: Page, phase?: { step: number; phase: number }): Promise<MapCamera> {
  return page.evaluate((mark) => {
    const marks = (window as WindowWithMapZoomObserver).__mapZoomPhaseMarks
    const previous = marks?.at(-1)
    if (mark && marks && (previous?.step !== mark.step || previous.phase !== mark.phase)) {
      marks.push({ ...mark, at: performance.now() })
    }
    const query = new URLSearchParams(window.location.search)
    return {
      zoom: Number(query.get("z")),
      latitude: Number(query.get("lat")),
      longitude: Number(query.get("lng")),
    }
  }, phase)
}

function isMapResource(request: Request): boolean {
  return new URL(request.url()).hostname === MAP_RESOURCE_HOST
}

async function waitForMapNetworkQuiescence(
  page: Page,
  pendingRequests: Set<Request>,
  requestRevision: () => number,
  step?: number
): Promise<void> {
  let lastRevision = -1
  let stablePolls = 0

  await expect
    .poll(
      async () => {
        await page.evaluate(
          (measurementStep) =>
            new Promise<void>((resolve) => {
              const marks = (window as WindowWithMapZoomObserver).__mapZoomPhaseMarks
              const previous = marks?.at(-1)
              if (
                measurementStep &&
                marks &&
                (previous?.step !== measurementStep || previous.phase !== 3)
              ) {
                marks.push({ step: measurementStep, phase: 3, at: performance.now() })
              }
              requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
            }),
          step
        )

        const revision = requestRevision()
        if (pendingRequests.size === 0 && revision === lastRevision) {
          stablePolls += 1
        } else {
          stablePolls = 0
        }
        lastRevision = revision
        return stablePolls >= 2
      },
      { message: "real map resources and rendered camera settle before measurement" }
    )
    .toBe(true)
}

test("live MapLibre zoom has no main-thread long task at or above 50 ms", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "longtask performance entries require Chromium")

  const pendingMapRequests = new Set<Request>()
  let mapRequestRevision = 0
  page.on("request", (request) => {
    if (!isMapResource(request)) return
    pendingMapRequests.add(request)
    mapRequestRevision += 1
  })
  page.on("requestfinished", (request) => pendingMapRequests.delete(request))
  page.on("requestfailed", (request) => pendingMapRequests.delete(request))

  await page.route(`https://${MAP_RESOURCE_HOST}/styles/**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(deterministicStyle),
    })
  )
  await page.route(`https://${MAP_RESOURCE_HOST}/data/v3/**`, (route) =>
    route.fulfill({ status: 200, contentType: "application/x-protobuf", body: Buffer.alloc(0) })
  )

  await loginAs(page, "student")
  await page.goto(MAP_URL, { waitUntil: "commit" })

  const placeholder = page.getByTestId("map-activation-placeholder")
  await expect(placeholder).toBeVisible()
  await placeholder.scrollIntoViewIfNeeded()

  const styleResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      url.hostname === MAP_RESOURCE_HOST && url.pathname.startsWith("/styles/") && response.ok()
    )
  })
  const vectorTileResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      url.hostname === MAP_RESOURCE_HOST && url.pathname.startsWith("/data/v3/") && response.ok()
    )
  })

  await placeholder.click()
  const [styleResponse, vectorTileResponse] = await Promise.all([
    styleResponsePromise,
    vectorTileResponsePromise,
  ])
  expect(styleResponse.ok()).toBe(true)
  expect(vectorTileResponse.ok()).toBe(true)

  const canvas = page.locator(".maplibregl-canvas")
  await expect(canvas).toBeVisible()
  await expect
    .poll(() =>
      canvas.evaluate((element) => {
        const canvasElement = element as HTMLCanvasElement
        return canvasElement.width > 0 && canvasElement.height > 0
      })
    )
    .toBe(true)
  await expect.poll(async () => Number.isFinite((await readCamera(page)).zoom)).toBe(true)
  await waitForMapNetworkQuiescence(page, pendingMapRequests, () => mapRequestRevision)

  const zoomIn = page.getByRole("button", { name: /Приблизить|Zoom in/u })
  await expect(zoomIn).toBeVisible()
  const initialCamera = await readCamera(page)

  const measurementAvailable = await page.evaluate(() => {
    if (!PerformanceObserver.supportedEntryTypes.includes("longtask")) return false

    const measurementWindow = window as WindowWithMapZoomObserver
    const samples: LongTaskSample[] = []
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.entryType === "longtask") {
          samples.push({ startTime: entry.startTime, duration: entry.duration })
        }
      }
    })

    observer.observe({ type: "longtask", buffered: false })
    measurementWindow.__mapZoomLongTaskObserver = observer
    measurementWindow.__mapZoomLongTaskSamples = samples
    measurementWindow.__mapZoomPhaseMarks = []
    measurementWindow.__mapZoomMeasurementStartedAt = performance.now()
    return true
  })
  expect(measurementAvailable, "Chromium exposes longtask PerformanceObserver entries").toBe(true)

  const longTaskSamples: MeasuredLongTaskSample[] = []
  try {
    for (let step = 0; step < ZOOM_STEPS; step += 1) {
      const measurementStep = step + 1
      const previousZoom = (await readCamera(page, { step: measurementStep, phase: 1 })).zoom
      await zoomIn.click()
      await expect
        .poll(async () => (await readCamera(page, { step: measurementStep, phase: 2 })).zoom, {
          message: "the real zoom control updates the MapLibre camera",
        })
        .not.toBe(previousZoom)
      await waitForMapNetworkQuiescence(
        page,
        pendingMapRequests,
        () => mapRequestRevision,
        measurementStep
      )
    }
  } finally {
    longTaskSamples.push(...(await stopLongTaskMeasurement(page)))
  }

  expect((await readCamera(page)).zoom).toBeGreaterThan(initialCamera.zoom)
  const blockingTasks = longTaskSamples.filter(
    (sample) => sample.duration >= LONG_TASK_THRESHOLD_MS
  )
  if (blockingTasks.length > 0) {
    reportMapZoomLongTasks(
      test.info().project.name,
      test.info().retry,
      blockingTasks.map(({ step, phase, duration }) => ({ step, phase, duration }))
    )
  }
  expect(blockingTasks, "zoom must not create a main-thread long task of 50 ms or more").toEqual([])
})
