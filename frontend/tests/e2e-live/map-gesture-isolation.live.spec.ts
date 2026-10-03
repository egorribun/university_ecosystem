import { expect, loginAs, test } from "./fixtures"
import type { Page } from "@playwright/test"

const CAMPUS_CENTER = { longitude: 37.81478, latitude: 55.7144 }
const CENTER_TOLERANCE_DEGREES = 0.0001
const MAP_URL = "/map?z=17&lat=55.7144&lng=37.81478&p=0&b=0"
const STABILITY_FRAME_COUNT = 6

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
                [CAMPUS_CENTER.longitude - 0.003, CAMPUS_CENTER.latitude],
                [CAMPUS_CENTER.longitude + 0.003, CAMPUS_CENTER.latitude],
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

type Camera = { zoom: number; latitude: number; longitude: number }
type PagePosition = {
  scrollX: number
  scrollY: number
  viewportOffsetLeft: number
  viewportOffsetTop: number
  viewportScale: number
}

async function readCamera(page: Page): Promise<Camera> {
  return page.evaluate(() => {
    const query = new URLSearchParams(window.location.search)
    return {
      zoom: Number(query.get("z")),
      latitude: Number(query.get("lat")),
      longitude: Number(query.get("lng")),
    }
  })
}

async function readPagePosition(page: Page): Promise<PagePosition> {
  return page.evaluate(() => {
    const visualViewport = window.visualViewport
    return {
      scrollX: Math.round(window.scrollX),
      scrollY: Math.round(window.scrollY),
      viewportOffsetLeft: Math.round(visualViewport?.offsetLeft ?? 0),
      viewportOffsetTop: Math.round(visualViewport?.offsetTop ?? 0),
      viewportScale: Number((visualViewport?.scale ?? 1).toFixed(2)),
    }
  })
}

async function expectPagePositionStableForFrames(
  page: Page,
  initialPosition: PagePosition,
  gesture: "wheel" | "pinch" | "pan"
) {
  const samples = await page.evaluate(async (sampleCount) => {
    const readPosition = () => {
      const visualViewport = window.visualViewport
      return {
        scrollX: Math.round(window.scrollX),
        scrollY: Math.round(window.scrollY),
        viewportOffsetLeft: Math.round(visualViewport?.offsetLeft ?? 0),
        viewportOffsetTop: Math.round(visualViewport?.offsetTop ?? 0),
        viewportScale: Number((visualViewport?.scale ?? 1).toFixed(2)),
      }
    }

    const positions = []
    for (let frameIndex = 0; frameIndex < sampleCount; frameIndex += 1) {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      positions.push(readPosition())
    }
    return positions
  }, STABILITY_FRAME_COUNT)

  expect(
    samples,
    `${gesture} must preserve page and visual viewport across settled frames`
  ).toEqual(Array.from({ length: STABILITY_FRAME_COUNT }, () => initialPosition))
}

function expectCenterNear(camera: Camera, expected: Pick<Camera, "latitude" | "longitude">) {
  expect(Math.abs(camera.latitude - expected.latitude)).toBeLessThanOrEqual(
    CENTER_TOLERANCE_DEGREES
  )
  expect(Math.abs(camera.longitude - expected.longitude)).toBeLessThanOrEqual(
    CENTER_TOLERANCE_DEGREES
  )
}

async function openLiveMap(page: Page, viewport: { width: number; height: number }, touch = false) {
  await page.setViewportSize(viewport)
  const touchSession = touch ? await page.context().newCDPSession(page) : null

  try {
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
    await page.route("https://tiles.openfreemap.org/styles/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(deterministicStyle),
      })
    )
    await page.route("https://tiles.openfreemap.org/data/v3/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/x-protobuf", body: Buffer.alloc(0) })
    )

    await loginAs(page, "student")
    await page.goto(MAP_URL, { waitUntil: "commit" })
    const placeholder = page.getByTestId("map-activation-placeholder")
    await expect(placeholder).toBeVisible({ timeout: 30_000 })
    await placeholder.scrollIntoViewIfNeeded()
    await placeholder.click()

    const canvas = page.locator(".maplibregl-canvas")
    await expect(canvas).toBeVisible({ timeout: 30_000 })
    await expect
      .poll(async () => {
        const camera = await readCamera(page)
        return Number.isFinite(camera.zoom) && Number.isFinite(camera.latitude)
      })
      .toBe(true)

    return { canvas, touchSession }
  } catch (error) {
    if (touchSession) {
      await touchSession.send("Emulation.setTouchEmulationEnabled", { enabled: false })
      await touchSession.detach()
    }
    throw error
  }
}

test("live map captures wheel zoom without page scroll or center drift", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "the map gesture requires Chromium WebGL")
  test.skip((page.viewportSize()?.width ?? 0) < 640, "wheel scenario runs in the desktop project")

  const { canvas } = await openLiveMap(page, { width: 1440, height: 900 })
  const before = await readCamera(page)
  expect(before.zoom).toBe(17)
  expectCenterNear(before, CAMPUS_CENTER)
  const pagePositionBefore = await readPagePosition(page)
  const canvasBounds = await canvas.boundingBox()
  expect(canvasBounds).not.toBeNull()

  await page.mouse.move(
    canvasBounds!.x + canvasBounds!.width / 2,
    canvasBounds!.y + canvasBounds!.height / 2
  )
  await page.mouse.wheel(0, 500)

  await expect
    .poll(async () => (await readCamera(page)).zoom, {
      message: "wheel input over the live map must change the map zoom",
    })
    .not.toBe(before.zoom)
  expect(await readPagePosition(page)).toEqual(pagePositionBefore)
  await expectPagePositionStableForFrames(page, pagePositionBefore, "wheel")
  expectCenterNear(await readCamera(page), before)
})

test("live map leaves page scrolling available outside the map", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "the map gesture requires Chromium WebGL")
  test.skip((page.viewportSize()?.width ?? 0) < 640, "wheel scenario runs in the desktop project")

  const { canvas } = await openLiveMap(page, { width: 1440, height: 900 })
  const canvasBounds = await canvas.boundingBox()
  expect(canvasBounds).not.toBeNull()
  const pointer = { x: 12, y: 12 }
  const pointInsideCanvas =
    pointer.x >= canvasBounds!.x &&
    pointer.x <= canvasBounds!.x + canvasBounds!.width &&
    pointer.y >= canvasBounds!.y &&
    pointer.y <= canvasBounds!.y + canvasBounds!.height
  expect(pointInsideCanvas, "the page-level wheel point is outside the map canvas").toBe(false)
  const pointInsideMap = await page.evaluate(({ x, y }) => {
    const target = document.elementFromPoint(x, y)
    return target instanceof Element && target.closest(".maplibregl-map") !== null
  }, pointer)
  expect(pointInsideMap, "the page-level wheel target is outside MapLibre").toBe(false)

  await page.evaluate(() => window.scrollTo(0, 0))
  const cameraBeforeWheel = await readCamera(page)
  const pagePositionBeforeWheel = await readPagePosition(page)
  expect(pagePositionBeforeWheel.scrollY).toBe(0)
  await page.mouse.move(pointer.x, pointer.y)
  await page.mouse.wheel(0, 500)

  await expect
    .poll(async () => (await readPagePosition(page)).scrollY, {
      message: "wheel input outside the map remains available to the document",
    })
    .toBeGreaterThan(pagePositionBeforeWheel.scrollY)
  const pagePositionAfterWheel = await readPagePosition(page)
  expect(pagePositionAfterWheel.scrollX).toBe(pagePositionBeforeWheel.scrollX)
  expect(pagePositionAfterWheel.viewportScale).toBe(pagePositionBeforeWheel.viewportScale)
  expect(await readCamera(page)).toEqual(cameraBeforeWheel)
  await expectPagePositionStableForFrames(page, pagePositionAfterWheel, "wheel")
})

test("live mobile map keeps pinch and one-finger pan inside the map", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "touch gestures require Chromium CDP")
  test.skip((page.viewportSize()?.width ?? 0) >= 640, "touch scenario runs in the mobile project")

  const { canvas, touchSession } = await openLiveMap(page, { width: 390, height: 844 }, true)
  expect(touchSession).not.toBeNull()

  try {
    const bounds = await canvas.boundingBox()
    expect(bounds).not.toBeNull()
    const centerX = bounds!.x + bounds!.width / 2
    const centerY = bounds!.y + bounds!.height / 2
    const initialCamera = await readCamera(page)
    expect(initialCamera.zoom).toBe(17)
    expectCenterNear(initialCamera, CAMPUS_CENTER)
    const pagePositionBeforePinch = await readPagePosition(page)

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
      .poll(async () => (await readCamera(page)).zoom, {
        message: "two-finger touch must zoom the live map",
      })
      .not.toBe(initialCamera.zoom)
    expect(await readPagePosition(page)).toEqual(pagePositionBeforePinch)
    await expectPagePositionStableForFrames(page, pagePositionBeforePinch, "pinch")
    expectCenterNear(await readCamera(page), initialCamera)

    const beforePan = await readCamera(page)
    const pagePositionBeforePan = await readPagePosition(page)
    await touchSession!.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ id: 0, x: centerX, y: centerY, force: 1 }],
    })
    await page.waitForTimeout(60)
    await touchSession!.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ id: 0, x: centerX, y: centerY + 70, force: 1 }],
    })
    await page.waitForTimeout(60)
    await touchSession!.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ id: 0, x: centerX, y: centerY + 145, force: 1 }],
    })
    await touchSession!.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })

    await expect
      .poll(async () => (await readCamera(page)).latitude, {
        message: "one-finger touch must pan the live map camera",
      })
      .not.toBe(beforePan.latitude)
    expect(await readPagePosition(page)).toEqual(pagePositionBeforePan)
    await expectPagePositionStableForFrames(page, pagePositionBeforePan, "pan")
  } finally {
    await touchSession!.send("Emulation.setTouchEmulationEnabled", { enabled: false })
    await touchSession!.detach()
  }
})
