import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./map-zoom-longtask.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const mapFeatureUrl = new URL("../../src/features/map/MapFeature.tsx", import.meta.url)
const mapLibreUrl = new URL("../../src/components/map/MapLibreMap.tsx", import.meta.url)
const gestureSpecUrl = new URL("./map-gesture-isolation.live.spec.ts", import.meta.url)
const planUrl = new URL("../../../docs/superpowers/plans/MVP_MASTER_PLAN.md", import.meta.url)

test("map zoom long-task acceptance observes the real MapLibre browser path", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live map zoom long-task scenario must exist")
  }

  const [config, mapFeature, mapLibre, gestureSpec, plan] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(mapFeatureUrl, "utf8"),
    readFile(mapLibreUrl, "utf8"),
    readFile(gestureSpecUrl, "utf8"),
    readFile(planUrl, "utf8"),
  ])

  assert.match(
    plan,
    /В v1\.1: полный lab protocol navbar CLS <0\.1, отсутствие map long tasks ≥50 ms/u
  )
  assert.match(mapFeature, /data-testid="map-activation-placeholder"/u)
  assert.match(mapFeature, /setMapReady\(true\)/u)
  assert.match(mapLibre, /https:\/\/tiles\.openfreemap\.org\/styles\/bright/u)
  assert.match(mapLibre, /if \(!map \|\| !map\.loaded\(\)\)/u)

  assert.match(spec, /live MapLibre zoom has no main-thread long task at or above 50 ms/u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /await page\.goto\(MAP_URL/u)
  assert.match(spec, /map-activation-placeholder/u)
  assert.match(spec, /waitForResponse\([\s\S]*?\/styles\//u)
  assert.match(spec, /waitForResponse\([\s\S]*?\/data\/v3\//u)
  assert.match(spec, /\.maplibregl-canvas/u)
  assert.match(spec, /waitForMapNetworkQuiescence/u)
  assert.match(spec, /requestAnimationFrame/u)
  assert.match(spec, /PerformanceObserver/u)
  assert.match(spec, /type:\s*["']longtask["']/u)
  assert.match(spec, /LONG_TASK_THRESHOLD_MS\s*=\s*50/u)
  assert.match(spec, /sample\.duration\s*>=\s*LONG_TASK_THRESHOLD_MS/u)
  assert.match(spec, /const ZOOM_STEPS\s*=\s*3/u)
  assert.match(spec, /getByRole\("button",\s*\{\s*name: \/Приблизить\|Zoom in\/u\s*\}\)/u)
  assert.match(spec, /await zoomIn\.click\(\)/u)
  assert.match(spec, /toEqual\(\s*\[\s*\]\s*\)/u)
  assert.match(spec, /browserName !== ["']chromium["']/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|useMockApi|waitForTimeout/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)/u)

  assert.match(gestureSpec, /page\.route\(["']https:\/\/tiles\.openfreemap\.org\/styles/u)
  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name: "desktop"/u)
  assert.match(config, /name: "mobile"/u)
})
