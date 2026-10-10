import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const CAMPUS_CENTER = [37.81478, 55.7144] as const

const deterministicStyle = {
  version: 8,
  sources: {
    openmaptiles: {
      type: "vector",
      tiles: ["https://tiles.openfreemap.org/data/v3/{z}/{x}/{y}.pbf"],
      minzoom: 0,
      maxzoom: 14,
    },
    "gesture-fixture": {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: {},
            geometry: {
              type: "LineString",
              coordinates: [
                [CAMPUS_CENTER[0] - 0.003, CAMPUS_CENTER[1]],
                [CAMPUS_CENTER[0] + 0.003, CAMPUS_CENTER[1]],
              ],
            },
          },
        ],
      },
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#f4f6f8" } },
    {
      id: "gesture-fixture-line",
      type: "line",
      source: "gesture-fixture",
      paint: { "line-color": "#e11d48", "line-width": 6 },
    },
  ],
}

type WheelObservation = { defaultPrevented: boolean; targetInsideMap: boolean } | null
type WindowWithWheelObservation = Window & { __mapWheelObservation?: WheelObservation }

async function openMapPage(
  page: Page,
  viewport: { width: number; height: number },
  mobileTouch = false
) {
  await page.setViewportSize(viewport)
  const touchSession = mobileTouch ? await page.context().newCDPSession(page) : null
  if (touchSession) {
    await touchSession.send("Emulation.setDeviceMetricsOverride", {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: 1,
      mobile: true,
    })
    await touchSession.send("Emulation.setTouchEmulationEnabled", {
      enabled: true,
      maxTouchPoints: 2,
    })
  }
  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.route("https://tiles.openfreemap.org/styles/bright", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(deterministicStyle),
    })
  )
  await page.route("https://tiles.openfreemap.org/data/v3/**", async (route) =>
    route.fulfill({ status: 200, contentType: "application/x-protobuf", body: Buffer.alloc(0) })
  )

  await gotoWithTransientRetry(page, "/map?z=17&lat=55.7144&lng=37.81478&p=0&b=0", {
    waitUntil: "commit",
    timeout: 30_000,
  })

  const placeholder = page.getByTestId("map-activation-placeholder")
  await expect(placeholder).toBeVisible({ timeout: 30_000 })
  return { placeholder, touchSession }
}

test("MapLibre captures wheel zoom without scrolling the page or shifting its viewport", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "the gesture test requires Chromium WebGL")
  await useMockApi(page)
  const { placeholder } = await openMapPage(page, { width: 1280, height: 900 })

  const initialScrollY = await page.evaluate(() => Math.round(window.scrollY))
  await page.mouse.move(12, 12)
  await page.mouse.wheel(0, 500)
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: "wheel input outside the map must remain available to the page",
    })
    .toBeGreaterThan(initialScrollY)

  await placeholder.scrollIntoViewIfNeeded()
  const mapViewport = page.locator(".map-viewport")
  const beforeActivation = await mapViewport.boundingBox()
  expect(beforeActivation).not.toBeNull()
  const documentTopBefore =
    beforeActivation!.y + (await page.evaluate(() => Math.round(window.scrollY)))

  await placeholder.click()
  const canvas = page.locator(".maplibregl-canvas")
  await expect(canvas).toBeVisible({ timeout: 30_000 })

  const afterActivation = await mapViewport.boundingBox()
  expect(afterActivation).not.toBeNull()
  const documentTopAfter =
    afterActivation!.y + (await page.evaluate(() => Math.round(window.scrollY)))
  expect(Math.abs(documentTopAfter - documentTopBefore)).toBeLessThanOrEqual(1)
  expect(Math.abs(afterActivation!.height - beforeActivation!.height)).toBeLessThanOrEqual(1)

  const canvasBounds = await canvas.boundingBox()
  expect(canvasBounds).not.toBeNull()
  const scrollBeforeMapWheel = await page.evaluate(() => Math.round(window.scrollY))
  await page.evaluate(() => {
    const observedWindow = window as WindowWithWheelObservation
    observedWindow.__mapWheelObservation = null
    document.addEventListener(
      "wheel",
      (event) => {
        const target = event.target
        observedWindow.__mapWheelObservation = {
          defaultPrevented: event.defaultPrevented,
          targetInsideMap: target instanceof Element && target.closest(".maplibregl-map") !== null,
        }
      },
      { once: true, passive: true }
    )
  })

  await page.mouse.move(
    canvasBounds!.x + canvasBounds!.width / 2,
    canvasBounds!.y + canvasBounds!.height / 2
  )
  await page.mouse.wheel(0, 500)
  await expect
    .poll(() => page.evaluate(() => (window as WindowWithWheelObservation).__mapWheelObservation))
    .toEqual({ defaultPrevented: true, targetInsideMap: true })
  expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(scrollBeforeMapWheel)
  await expect
    .poll(() => new URL(page.url()).searchParams.get("z"), {
      message: "a wheel gesture over the real map must update its camera viewport",
    })
    .not.toBe("17")
})

test("MapLibre captures a mobile two-finger pinch without page zoom or scroll", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "the touch gesture test requires Chromium CDP")
  await useMockApi(page)
  const { placeholder, touchSession } = await openMapPage(page, { width: 390, height: 844 }, true)
  expect(touchSession).not.toBeNull()

  try {
    await placeholder.scrollIntoViewIfNeeded()
    await placeholder.click()
    const canvas = page.locator(".maplibregl-canvas")
    await expect(canvas).toBeVisible({ timeout: 30_000 })
    const canvasBounds = await canvas.boundingBox()
    expect(canvasBounds).not.toBeNull()

    const scrollBeforePinch = await page.evaluate(() => Math.round(window.scrollY))
    const pageScaleBeforePinch = await page.evaluate(() => window.visualViewport?.scale ?? 1)
    const zoomBeforePinch = new URL(page.url()).searchParams.get("z")
    const centerX = canvasBounds!.x + canvasBounds!.width / 2
    const centerY = canvasBounds!.y + canvasBounds!.height / 2

    await touchSession!.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [
        { id: 0, x: centerX - 24, y: centerY, force: 1 },
        { id: 1, x: centerX + 24, y: centerY, force: 1 },
      ],
    })
    await page.waitForTimeout(60)
    await touchSession!.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        { id: 0, x: centerX - 52, y: centerY, force: 1 },
        { id: 1, x: centerX + 52, y: centerY, force: 1 },
      ],
    })
    await page.waitForTimeout(60)
    await touchSession!.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        { id: 0, x: centerX - 72, y: centerY, force: 1 },
        { id: 1, x: centerX + 72, y: centerY, force: 1 },
      ],
    })
    await touchSession!.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })

    await expect
      .poll(() => new URL(page.url()).searchParams.get("z"), {
        message: "a real two-finger gesture must change the MapLibre camera zoom",
      })
      .not.toBe(zoomBeforePinch)
    expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(scrollBeforePinch)
    expect(await page.evaluate(() => window.visualViewport?.scale ?? 1)).toBeCloseTo(
      pageScaleBeforePinch,
      2
    )
  } finally {
    await touchSession!.send("Emulation.setTouchEmulationEnabled", { enabled: false })
    await touchSession!.detach()
  }
})
