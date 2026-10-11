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
const visibilityFixtureUrl = new URL("./story-visibility-fixtures.ts", import.meta.url)

test("live Stories acceptance proves heap plateau and hidden-tab pause after viewer cycles", async () => {
  const [spec, config, seed, dashboardStories, visibilityFixture] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(seedUrl, "utf8"),
    readFile(dashboardStoriesUrl, "utf8"),
    readFile(visibilityFixtureUrl, "utf8"),
  ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /actionTimeout:\s*15_000/u)
  assert.match(config, /navigationTimeout:\s*45_000/u)
  assert.match(config, /ignoreHTTPSErrors:\s*true/u)
  assert.match(config, /locale:\s*["']ru-RU["']/u)
  assert.match(
    config,
    /name:\s*["']desktop["'],\s*use:\s*\{\s*\.\.\.devices\[["']Desktop Chrome["']\],\s*viewport:\s*\{\s*width:\s*1440,\s*height:\s*900\s*\}\s*\}/u
  )
  assert.match(
    config,
    /name:\s*["']mobile["'],\s*use:\s*\{\s*\.\.\.devices\[["']Pixel 7["']\],\s*viewport:\s*\{\s*width:\s*390,\s*height:\s*844\s*\}\s*\}/u
  )
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
    /storyVisibilityTest\(\s*["']a seeded story viewer reaches a memory plateau after 20 open-close cycles["']/u
  )
  assert.match(spec, /const WARM_UP_CYCLES = 1/u)
  assert.match(spec, /const MEASURED_CYCLES = 20/u)
  assert.ok(spec.includes('const STORY_MEMORY_DIAGNOSTIC_PREFIX = "STORY_MEMORY_DIAG "'))
  assert.ok(spec.includes('phase: "cycle0-after-settle-before-assertion"'))
  assert.match(spec, /DOMDebugger\.getEventListeners[\s\S]*?pierce:\s*false/u)
  assert.match(spec, /Runtime\.releaseObject[\s\S]*?Runtime\.releaseObjectGroup/u)
  const measuredLoop = spec.indexOf("for (let cycle = 0; cycle < MEASURED_CYCLES; cycle += 1)")
  const diagnosticCall = spec.indexOf("emitStoryMemoryDiagnosticRecord(", measuredLoop)
  const strictCounterAssertion = spec.indexOf(
    "expect(snapshot.domCounters).toEqual(warmSnapshot.domCounters)"
  )
  assert.match(spec, /if \(cycle === 0\) \{[\s\S]*?emitStoryMemoryDiagnosticRecord\(/u)
  assert.ok(diagnosticCall >= 0 && diagnosticCall < strictCounterAssertion)
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(
    spec,
    /await page\.goto\(new URL\(["']\/dashboard["'],\s*ownedSessionOrigin\(\)\)\.toString\(\)\)/u
  )
  assert.match(
    spec,
    /await page\.addInitScript\([\s\S]*?SERVICE_WORKER_BOOTSTRAP_EVENT[\s\S]*?await loginAs\(page,[\s\S]*?await page\.goto\(new URL\(["']\/dashboard["'],[\s\S]*?await page\.waitForFunction\([\s\S]*?__ueServiceWorkerBootstrapStatus[\s\S]*?expect\(serviceWorkerBootstrapStatus\)\.toBe\(["']ready["']\)[\s\S]*?const trigger =/u
  )
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
  assert.match(spec, /openStoryBackgroundTab\(page\)/u)
  assert.match(spec, /backgroundPage\.waitForTimeout\(1_000\)/u)
  assert.match(spec, /await backgroundPage\.bringToFront\(\)/u)
  assert.match(spec, /document\.visibilityState/u)
  assert.match(spec, /toBe\(["']hidden["']\)/u)
  assert.match(spec, /backgroundPage\.waitForTimeout\(/u)
  assert.match(spec, /toBe\(hiddenProgress\)/u)
  assert.match(spec, /page\.bringToFront\(\)/u)
  assert.match(spec, /toBe\(["']visible["']\)/u)
  assert.match(spec, /storyWriteRequests[\s\S]*?pathname\.startsWith\(["']\/api\/v1\/stories["']/u)
  assert.match(spec, /expect\(storyWriteRequests\)\.toEqual\(\[\]\)/u)
  assert.match(spec, /await backgroundPage\.close\(\)/u)
  assert.match(visibilityFixture, /connectOverCDP[\s\S]*?noDefaults:\s*true/u)
  assert.match(visibilityFixture, /noDefaults:\s*true,\s*isLocal:\s*true,\s*timeout:\s*3_000/u)
  assert.match(
    visibilityFixture,
    /const contexts = attached\.contexts\(\)\s*if \(contexts\.length !== 1\)/u
  )
  assert.match(visibilityFixture, /if \(context\.pages\(\)\.length !== 0\)/u)
  assert.match(
    visibilityFixture,
    /url:\s*["']about:blank["'],\s*newWindow:\s*true,\s*background:\s*false/u
  )
  assert.match(
    visibilityFixture,
    /browserCdp\.send\(["']Target\.createTarget["'][\s\S]*?newWindow:\s*true,[\s\S]*?background:\s*false/u
  )
  assert.match(
    visibilityFixture,
    /state\.browserCdp\.send\(["']Target\.createTarget["'][\s\S]*?newWindow:\s*false,[\s\S]*?background:\s*true/u
  )
  assert.match(
    visibilityFixture,
    /newWindow:\s*false,\s*\/\/ Create an actual background tab[\s\S]*?background:\s*true/u
  )
  assert.match(
    visibilityFixture,
    /context\.pages\(\)\.length !== 1 \|\| context\.pages\(\)\[0\] !== page/u
  )
  assert.match(visibilityFixture, /state\.context\.pages\(\)\.length !== 2/u)
  assert.match(
    visibilityFixture,
    /Emulation\.setFocusEmulationEnabled[\s\S]*?\{ enabled: false \}/u
  )
  assert.match(
    visibilityFixture,
    /attached\.close\(\)[\s\S]*?attached\.isConnected\(\)[\s\S]*?storyBrowser\.isConnected\(\)/u
  )
  assert.match(visibilityFixture, /owner\.close\(\)[\s\S]*?owner\.isConnected\(\)/u)
  assert.match(
    visibilityFixture,
    /const unsupportedOptions = \[[\s\S]*?"bypassCSP"[\s\S]*?"storageState"[\s\S]*?"javaScriptEnabled"/u
  )
  assert.match(
    visibilityFixture,
    /use\.serviceWorkers !== undefined && use\.serviceWorkers !== "allow"/u
  )
  assert.match(
    visibilityFixture,
    /use\.acceptDownloads !== undefined && use\.acceptDownloads !== true/u
  )
  assert.match(visibilityFixture, /use\.colorScheme \?\? "light"/u)
  assert.match(visibilityFixture, /use\.reducedMotion \?\? "no-preference"/u)
  assert.match(visibilityFixture, /use\.forcedColors \?\? "none"/u)
  assert.match(visibilityFixture, /use\.contrast \?\? "no-preference"/u)
  assert.match(visibilityFixture, /use\.media \?\? ""/u)
  assert.match(
    visibilityFixture,
    /Emulation\.setTouchEmulationEnabled[\s\S]*?\{\s*enabled: use\.hasTouch as boolean,?\s*\}/u
  )
  assert.match(visibilityFixture, /liveTest\.extend<\{ storyBrowser: Browser; page: Page \}>/u)
  assert.match(visibilityFixture, /storyBrowser:\s*async\s*\(/u)
  assert.doesNotMatch(visibilityFixture, /storyBrowser:\s*\[\s*async/u)
  assert.doesNotMatch(visibilityFixture, /^\s+browser:\s*\[/mu)
  assert.match(visibilityFixture, /channel:\s*["']chromium["']/u)
  assert.match(visibilityFixture, /headless:\s*true/u)
  assert.match(visibilityFixture, /Browser\.getWindowForTarget/u)
  assert.match(visibilityFixture, /mainWindowId !== backgroundWindowId/u)
  assert.match(visibilityFixture, /testInfo\.project\.use/u)
  assert.match(
    visibilityFixture,
    /use\.screen === undefined \? viewport : requiredSize\(use\.screen,\s*["']screen["']\)/u
  )
  assert.match(
    visibilityFixture,
    /Emulation\.setDeviceMetricsOverride[\s\S]*?deviceScaleFactor,[\s\S]*?mobile,[\s\S]*?screenWidth: screen\.width,[\s\S]*?screenHeight: screen\.height/u
  )
  assert.match(visibilityFixture, /Emulation\.setTouchEmulationEnabled[\s\S]*?use\.hasTouch/u)
  assert.match(
    visibilityFixture,
    /Emulation\.setUserAgentOverride[\s\S]*?userAgent,[\s\S]*?acceptLanguage: locale,[\s\S]*?userAgentMetadata/u
  )
  assert.match(visibilityFixture, /Emulation\.setLocaleOverride[\s\S]*?locale/u)
  assert.match(visibilityFixture, /page\.setDefaultTimeout\(actionTimeout\)/u)
  assert.match(visibilityFixture, /page\.setDefaultNavigationTimeout\(navigationTimeout\)/u)
  assert.doesNotMatch(visibilityFixture, /document\.visibilityState\s*=|dispatchEvent\(/u)
  assert.match(spec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(spec, /await expect\(dialog\)\.toHaveCount\(0\)/u)
  assert.match(spec, /await expect\(trigger\)\.toBeFocused\(\)/u)
  assert.match(spec, /expect\(snapshot\.domCounters\)\.toEqual\(warmSnapshot\.domCounters\)/u)
  assert.match(spec, /for \(let cycle = 0; cycle < MEASURED_CYCLES; cycle \+= 1\)/u)
  assert.doesNotMatch(spec, /randomUUID|freshPassword|request\.(?:post|put|patch|delete)|\.fill\(/u)

  assert.match(
    visibilityFixture,
    /export type StorySetupDiagnosticStage =([\s\S]*?\| "browser-launch"[\s\S]*?\| "cleanup")/u
  )
  assert.match(visibilityFixture, /const record = \{ schema: 1, project, stage, exceptionKind \}/u)
  assert.match(visibilityFixture, /if \(project !== "desktop" && project !== "mobile"\) return/u)
  assert.ok(
    visibilityFixture.includes(
      "process.stdout.write(`STORY_SETUP_DIAG ${JSON.stringify(record)}\\n`)"
    )
  )
  assert.match(
    visibilityFixture,
    /const testFailed = testInfo\.status !== testInfo\.expectedStatus/u
  )
  assert.match(visibilityFixture, /if \(fixtureFailed \|\| testFailed \|\| cleanupFailed\)/u)
  assert.match(
    visibilityFixture,
    /state\?\.setupFailureStage[\s\S]*?emitStorySetupDiagnostic\([\s\S]*?throwFixtureOutcome\(/u
  )
  assert.match(
    spec,
    /let bodyFailed = false[\s\S]*?catch \(error\) \{\s*recordStorySetupFailure\(page, error\)[\s\S]*?bodyFailed = true[\s\S]*?bodyError = error[\s\S]*?await cdp\.detach\(\)[\s\S]*?if \(bodyFailed\) throw bodyError/u
  )
  assert.match(
    spec,
    /recordStorySetupCleanupFailure\(page\)\s*cleanupFailed = true\s*cleanupError = error[\s\S]*?if \(cleanupFailed\) throw cleanupError/u
  )
  assert.doesNotMatch(spec, /finally \{\s*markStorySetupStage\(page, ["']cleanup["']\)/u)
  assert.doesNotMatch(visibilityFixture, /error\.stack|JSON\.stringify\(error|error\.message/u)
  for (const marker of [
    'markStorySetupStage(page, "bootstrap-listener")',
    'markStorySetupStage(page, "login")',
    'markStorySetupStage(page, "dashboard")',
    'markStorySetupStage(page, "bootstrap")',
    'markStorySetupStage(page, "story-trigger")',
    'markStorySetupStage(page, "baseline")',
    'markStorySetupStage(page, "warm-up")',
    'cycle === 0 ? "cycle0" : "measured-cycle"',
    'markStorySetupStage(page, "acceptance")',
  ]) {
    assert.ok(spec.includes(marker), `missing Story setup diagnostic stage marker: ${marker}`)
  }
})
