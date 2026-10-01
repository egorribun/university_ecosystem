import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./map-gesture-isolation.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const mapFeatureUrl = new URL("../../src/features/map/MapFeature.tsx", import.meta.url)
const mapLibreUrl = new URL("../../src/components/map/MapLibreMap.tsx", import.meta.url)
const mapSchemaUrl = new URL("../../src/features/map/schema.ts", import.meta.url)
const approvedPlanUrl = new URL(
  "../../../docs/superpowers/plans/MVP_APPROVED_PLAN.md",
  import.meta.url
)

test("live map gesture acceptance covers browser isolation and camera invariants", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("a live MapLibre gesture-isolation scenario must exist")
  }

  const [config, mapFeature, mapLibre, mapSchema, approvedPlan] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(mapFeatureUrl, "utf8"),
    readFile(mapLibreUrl, "utf8"),
    readFile(mapSchemaUrl, "utf8"),
    readFile(approvedPlanUrl, "utf8"),
  ])

  assert.match(approvedPlan, /Map: после wheel\/touch\/pinch внешний scroll не прыгает/u)
  assert.match(config, /trace:\s*["']off["']/u, "live gesture acceptance must not record traces")
  assert.match(
    config,
    /screenshot:\s*["']off["']/u,
    "live gesture acceptance must not save screenshots"
  )
  assert.match(config, /video:\s*["']off["']/u, "live gesture acceptance must not save video")
  assert.match(config, /name:\s*["']desktop["']/u, "the desktop project must discover this spec")
  assert.match(config, /name:\s*["']mobile["']/u, "the mobile project must discover this spec")
  assert.ok(
    /testDir:\s*["']\.\/tests\/e2e-live["']/u.test(config),
    "live specs use the live config"
  )
  assert.ok(
    /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u.test(config),
    "live spec is discoverable"
  )
  assert.ok(/loginAs\(page,\s*["']student["']\)/u.test(spec), "scenario uses the seeded student")
  assert.ok(/const MAP_URL = ["']\/map\?z=17&lat=55\.7144&lng=37\.81478&p=0&b=0["']/u.test(spec))
  assert.ok(/page\.goto\(MAP_URL/u.test(spec), "scenario opens the seeded map viewport")
  const routedPatterns = [...spec.matchAll(/page\.route\(\s*["']([^"']+)["']/gu)].map(
    ([, pattern]) => pattern
  )
  assert.deepEqual(
    routedPatterns,
    ["https://tiles.openfreemap.org/styles/**", "https://tiles.openfreemap.org/data/v3/**"],
    "only deterministic external map style/tile assets may be intercepted"
  )
  assert.doesNotMatch(
    spec,
    /useMockApi|routeWebSocket|page\.route\([^\n]*(?:\/api(?:\/|\*\*)|\/auth(?:\/|\*\*)|\/login(?:\/|\*\*))/iu,
    "application API and authentication must remain real"
  )
  assert.doesNotMatch(
    spec,
    /page\.(?:screenshot|video)|testInfo\.(?:attach|outputPath)|recordHar/u,
    "the scenario must not emit screenshots, video, HAR, or attached artifacts"
  )
  assert.ok(/map-activation-placeholder/u.test(spec), "scenario activates the real lazy map")
  assert.ok(/\.maplibregl-canvas/u.test(spec), "scenario sends gestures to the real map canvas")
  assert.ok(/page\.mouse\.wheel\(/u.test(spec), "desktop wheel gesture is covered")
  const outsideMapWheel = spec.slice(
    spec.indexOf('test("live map leaves page scrolling available outside the map'),
    spec.indexOf('test("live mobile map keeps pinch')
  )
  assert.match(
    outsideMapWheel,
    /window\.scrollTo\(0,\s*0\)/u,
    "outside-map wheel starts at the top so page scroll remains observable"
  )
  assert.match(
    outsideMapWheel,
    /const pointer = \{ x: 12, y: 12 \}[\s\S]*?document\.elementFromPoint\(x,\s*y\)[\s\S]*?target\.closest\(["']\.maplibregl-map["']\)/u,
    "the wheel pointer is proven to be outside the MapLibre interaction surface"
  )
  assert.match(outsideMapWheel, /page\.mouse\.move\(pointer\.x,\s*pointer\.y\)/u)
  assert.match(outsideMapWheel, /page\.mouse\.wheel\(0,\s*500\)/u)
  assert.match(
    outsideMapWheel,
    /toBeGreaterThan\(pagePositionBeforeWheel\.scrollY\)/u,
    "a real page-level wheel still scrolls the document"
  )
  assert.match(
    outsideMapWheel,
    /expect\(await readCamera\(page\)\)\.toEqual\(cameraBeforeWheel\)/u,
    "page-level wheel input does not change the map camera"
  )
  assert.ok(/Input\.dispatchTouchEvent/u.test(spec), "mobile touch gestures are covered")
  assert.ok(/Emulation\.setDeviceMetricsOverride/u.test(spec), "mobile metrics are emulated")
  assert.ok(/Emulation\.setTouchEmulationEnabled/u.test(spec), "touch input is enabled explicitly")
  assert.ok(/maxTouchPoints:\s*2/u.test(spec), "mobile browser emulates a two-touch device")
  assert.ok(/type:\s*["']touchStart["']/u.test(spec), "touch begins through Chromium input")
  assert.ok(/type:\s*["']touchMove["']/u.test(spec), "touch moves through Chromium input")
  assert.ok(/type:\s*["']touchEnd["']/u.test(spec), "touch ends through Chromium input")
  const pinchScenario = spec.slice(
    spec.indexOf("const pagePositionBeforePinch"),
    spec.indexOf("const beforePan")
  )
  const panScenario = spec.slice(spec.indexOf("const beforePan"), spec.indexOf("} finally"))
  assert.match(
    pinchScenario,
    /touchPoints:\s*\[\s*\{\s*id:\s*0,[\s\S]*?\},\s*\{\s*id:\s*1,/u,
    "pinch sends two independent touch points"
  )
  assert.match(
    panScenario,
    /touchPoints:\s*\[\s*\{\s*id:\s*0,[\s\S]*?\}\s*\]/u,
    "pan uses a single touch point"
  )
  assert.match(spec, /readPagePosition\(page\)/u, "the full browser viewport position is sampled")
  assert.ok(/window\.scrollX/u.test(spec), "horizontal page scroll is observed")
  assert.ok(/window\.scrollY/u.test(spec), "vertical page scroll is observed")
  assert.ok(
    /visualViewport\?\.offsetLeft/u.test(spec),
    "visual viewport horizontal offset is observed"
  )
  assert.ok(
    /visualViewport\?\.offsetTop/u.test(spec),
    "visual viewport vertical offset is observed"
  )
  assert.ok(/visualViewport\?\.scale/u.test(spec), "browser pinch zoom is isolated")
  assert.equal(
    (spec.match(/expect\(await readPagePosition\(page\)\)\.toEqual\(/gu) ?? []).length,
    3,
    "wheel, pinch, and pan each preserve page and visual viewport position"
  )
  assert.match(spec, /const STABILITY_FRAME_COUNT = 6/u)
  assert.match(spec, /async function expectPagePositionStableForFrames\(/u)
  assert.match(spec, /requestAnimationFrame/u)
  assert.match(
    spec,
    /expect\(\s*samples,[\s\S]*?settled frames[\s\S]*?\)\.toEqual\(Array\.from\(\{ length: STABILITY_FRAME_COUNT \}, \(\) => initialPosition\)\)/u
  )
  for (const [position, gesture] of [
    ["pagePositionBefore", "wheel"],
    ["pagePositionBeforePinch", "pinch"],
    ["pagePositionBeforePan", "pan"],
  ]) {
    assert.match(
      spec,
      new RegExp(
        `expectPagePositionStableForFrames\\(page,\\s*${position},\\s*["']${gesture}["']\\)`,
        "u"
      ),
      `${gesture} must keep the viewport unchanged across follow-up animation frames`
    )
  }
  assert.ok(/CENTER_TOLERANCE_DEGREES/u.test(spec))
  assert.ok(/toBeLessThanOrEqual\(\s*CENTER_TOLERANCE_DEGREES/u.test(spec))
  assert.ok(/expectCenterNear\(before, CAMPUS_CENTER\)/u.test(spec))
  assert.ok(/expectCenterNear\(await readCamera\(page\), before\)/u.test(spec))
  assert.ok(/expectCenterNear\(initialCamera, CAMPUS_CENTER\)/u.test(spec))
  assert.ok(/expectCenterNear\(await readCamera\(page\), initialCamera\)/u.test(spec))
  assert.ok(
    /readCamera\(page\)\)\.latitude[\s\S]*?\.not\.toBe\(beforePan\.latitude\)/u.test(spec),
    "one-finger pan must change the map center"
  )

  assert.match(mapFeature, /urlInitialViewport=\{latchedInitialViewport\}/u)
  assert.match(mapFeature, /onMapMoveEnd=\{handleMapMoveEnd\}/u)
  assert.match(mapFeature, /setUrlParams\(debouncedViewport\)/u)
  assert.match(mapLibre, /overscrollBehavior:\s*["']contain["']/u)
  assert.match(mapSchema, /lat:\s*Number\(state\.latitude\.toFixed\(5\)\)/u)
  assert.match(mapSchema, /lng:\s*Number\(state\.longitude\.toFixed\(5\)\)/u)
})
