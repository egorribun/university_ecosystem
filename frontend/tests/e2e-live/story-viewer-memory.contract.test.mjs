import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./story-viewer-memory.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const dashboardStoriesUrl = new URL(
  "../../src/components/stories/DashboardStories.tsx",
  import.meta.url
)

test("live Stories acceptance proves heap plateau and hidden-tab pause after viewer cycles", async () => {
  const [spec, config, seed, dashboardStories] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(seedUrl, "utf8"),
    readFile(dashboardStoriesUrl, "utf8"),
  ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(seed, /"title":\s*"🎓 Сессия: советы по подготовке"/u)
  assert.match(seed, /"title":\s*"🎓 Exam season: preparation tips"/u)
  assert.match(seed, /async def seed_stories[\s\S]*?is_active=True,[\s\S]*?expires_at=far_future/u)

  assert.match(dashboardStories, /requestAnimationFrame\(step\)/u)
  assert.match(dashboardStories, /cancelAnimationFrame\(rafRef\.current\)/u)
  assert.match(dashboardStories, /window\.addEventListener\(["']keydown["'],\s*handleKey\)/u)
  assert.match(dashboardStories, /window\.removeEventListener\(["']keydown["'],\s*handleKey\)/u)
  assert.match(
    dashboardStories,
    /document\.addEventListener\(["']visibilitychange["'],\s*handleVisibilityChange\)/u
  )
  assert.match(
    dashboardStories,
    /document\.removeEventListener\(["']visibilitychange["'],\s*handleVisibilityChange\)/u
  )

  assert.match(
    spec,
    /test\(["']a seeded story viewer reaches a memory plateau after 20 open-close cycles["']/u
  )
  assert.match(spec, /const WARM_UP_CYCLES = 1/u)
  assert.match(spec, /const MEASURED_CYCLES = 20/u)
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/dashboard["']\)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket\(|\.fulfill\(/u)
  assert.match(spec, /newCDPSession\(page\)/u)
  assert.match(spec, /HeapProfiler\.collectGarbage/u)
  assert.match(spec, /Memory\.getDOMCounters/u)
  assert.match(spec, /Runtime\.getHeapUsage/u)
  assert.match(spec, /const HEAP_PLATEAU_TOLERANCE_BYTES = 512 \* 1024/u)
  assert.match(spec, /earlyHeapMean[\s\S]*?lateHeapMean/u)
  assert.match(spec, /lateHeapMean\)\.toBeLessThanOrEqual\([\s\S]*?HEAP_PLATEAU_TOLERANCE_BYTES/u)
  assert.match(spec, /jsEventListeners/u)
  assert.match(spec, /await expect\.poll\(readProgress\)\.toBeGreaterThan\(0\)/u)
  assert.match(spec, /await expect\(dialog\)\.toHaveCount\(1\)/u)
  assert.match(spec, /context\(\)\.newPage\(\)/u)
  assert.match(spec, /document\.visibilityState/u)
  assert.match(spec, /toBe\(["']hidden["']\)/u)
  assert.match(spec, /backgroundPage\.waitForTimeout\(/u)
  assert.match(spec, /toBe\(hiddenProgress\)/u)
  assert.match(spec, /page\.bringToFront\(\)/u)
  assert.match(spec, /toBe\(["']visible["']\)/u)
  assert.match(spec, /storyWriteRequests[\s\S]*?pathname\.startsWith\(["']\/api\/v1\/stories["']/u)
  assert.match(spec, /expect\(storyWriteRequests\)\.toEqual\(\[\]\)/u)
  assert.match(spec, /await backgroundPage\.close\(\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(spec, /await expect\(dialog\)\.toHaveCount\(0\)/u)
  assert.match(spec, /await expect\(trigger\)\.toBeFocused\(\)/u)
  assert.match(spec, /expect\(snapshot\.domCounters\)\.toEqual\(warmSnapshot\.domCounters\)/u)
  assert.match(spec, /for \(let cycle = 0; cycle < MEASURED_CYCLES; cycle \+= 1\)/u)
  assert.doesNotMatch(spec, /randomUUID|freshPassword|request\.(?:post|put|patch|delete)|\.fill\(/u)
})
