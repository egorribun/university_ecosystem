import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./story-viewer-keyboard.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const viewerUrl = new URL("../../src/components/stories/StoryViewer.tsx", import.meta.url)
const dashboardStoriesUrl = new URL(
  "../../src/components/stories/DashboardStories.tsx",
  import.meta.url
)
const focusTrapUrl = new URL("../../src/hooks/useFocusTrap.ts", import.meta.url)
const appShellUrl = new URL("../../src/contexts/AppShellContext.tsx", import.meta.url)
const visibilityFixtureUrl = new URL("./story-visibility-fixtures.ts", import.meta.url)

function assertControlledVisibilityProof(spec, dashboardStories) {
  const controlledStart = spec.search(
    /storyVisibilityTest\(\s*["']a seeded story preserves elapsed playback across a clock-controlled hidden tab["']/u
  )
  assert.ok(controlledStart >= 0, "live acceptance includes clock-controlled visibility coverage")
  const controlled = spec.slice(controlledStart)

  assert.match(controlled, /await page\.emulateMedia\(\{ reducedMotion: ["']no-preference["'] \}\)/u)
  assert.match(controlled, /await page\.clock\.install\(\)[\s\S]*?await loginAs\(page/u)
  assert.match(controlled, /await page\.clock\.pauseAt\([\s\S]*?await openAtKnownProgress\(\)/u)
  assert.match(controlled, /await page\.clock\.runFor\(VISIBLE_WARMUP_MS\)/u)
  assert.match(controlled, /toBeGreaterThan\(15\)[\s\S]*?toBeLessThan\(25\)/u)
  assert.match(controlled, /const backgroundPage = await openStoryBackgroundTab\(page\)/u)
  assert.match(controlled, /await backgroundPage\.bringToFront\(\)/u)
  assert.match(controlled, /document\.visibilityState\)[\s\S]*?toBe\(["']hidden["']\)/u)
  assert.match(controlled, /new MutationObserver\(/u)
  assert.match(controlled, /attributeFilter:\s*\[["']aria-valuenow["']\]/u)
  assert.match(controlled, /observer\.takeRecords\(\)/u)
  assert.match(
    controlled,
    /for \(let checkpoint = 0; checkpoint < 2; checkpoint \+= 1\)[\s\S]*?await page\.clock\.fastForward\(STORY_HIDDEN_DURATION_MS \/ 2\)[\s\S]*?expect\(await readProgress\(\)\)\.toBe\(pausedProgress\)[\s\S]*?observation\.read\(\)[\s\S]*?expect\(hiddenProgressChanges\)\.toBe\(0\)/u
  )
  assert.match(controlled, /observation\.disconnect\(\), progressObservation\)/u)
  assert.match(controlled, /await progressObservation\.dispose\(\)/u)
  assert.match(controlled, /await page\.bringToFront\(\)[\s\S]*?toBe\(["']visible["']\)/u)
  assert.match(controlled, /await page\.clock\.runFor\(VISIBLE_RESUME_MS\)/u)
  assert.match(controlled, /toBeGreaterThan\(pausedProgress \+ MIN_RESUMED_ADVANCE\)/u)
  assert.match(controlled, /toBeLessThan\(pausedProgress \+ MAX_RESUMED_ADVANCE\)/u)
  assert.match(controlled, /document\.addEventListener\(["']visibilitychange["'], blockHiddenVisibility, true\)/u)
  assert.match(controlled, /document\.visibilityState === ["']hidden["']\) event\.stopImmediatePropagation\(\)/u)
  assert.match(controlled, /await page\.clock\.fastForward\(1_000\)/u)
  assert.match(controlled, /toBeGreaterThan\(unpausedProgress \+ 10\)/u)
  assert.match(controlled, /document\.removeEventListener\(["']visibilitychange["'], blockHiddenVisibility, true\)/u)
  assert.match(controlled, /finally \{[\s\S]*?removeBlocker\(\), removeVisibilityBlocker\)/u)
  assert.match(controlled, /await removeVisibilityBlocker\.dispose\(\)/u)
  assert.match(controlled, /await page\.clock\.resume\(\)/u)

  const readNumber = (name, source) => {
    const match = source.match(new RegExp(`const ${name} = ([\\d_]+)`, "u"))
    assert.ok(match, `missing ${name}`)
    return Number(match[1].replaceAll("_", ""))
  }
  const autoAdvance = readNumber("STORY_AUTO_ADVANCE_MS", dashboardStories)
  const hiddenDuration = readNumber("STORY_HIDDEN_DURATION_MS", controlled)
  const warmup = readNumber("VISIBLE_WARMUP_MS", controlled)
  const resume = readNumber("VISIBLE_RESUME_MS", controlled)
  const minimumAdvance = readNumber("MIN_RESUMED_ADVANCE", controlled)
  const maximumAdvance = readNumber("MAX_RESUMED_ADVANCE", controlled)
  assert.ok(hiddenDuration > autoAdvance, "hidden interval exceeds a whole story")
  assert.ok((warmup / autoAdvance) * 100 > 15 && (warmup / autoAdvance) * 100 < 25)
  assert.ok((resume / autoAdvance) * 100 > minimumAdvance)
  assert.ok((resume / autoAdvance) * 100 < maximumAdvance)
  assert.ok(minimumAdvance > 0 && maximumAdvance < 15, "resume bounds reject reset progress")
  assert.ok((1_000 / autoAdvance) * 100 > 10, "negative control can exceed its threshold")
}

test("story viewer live acceptance checks seeded keyboard trap and focus cleanup", async () => {
  const [spec, config, seed, viewer, dashboardStories, focusTrap, appShell, visibilityFixture] =
    await Promise.all([
      readFile(specUrl, "utf8"),
      readFile(configUrl, "utf8"),
      readFile(seedUrl, "utf8"),
      readFile(viewerUrl, "utf8"),
      readFile(dashboardStoriesUrl, "utf8"),
      readFile(focusTrapUrl, "utf8"),
      readFile(appShellUrl, "utf8"),
      readFile(visibilityFixtureUrl, "utf8"),
    ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /actionTimeout:\s*15_000/u)
  assert.match(config, /navigationTimeout:\s*45_000/u)
  assert.match(seed, /"title":\s*"🎓 Сессия: советы по подготовке"/u)
  assert.match(seed, /"title":\s*"🎓 Exam season: preparation tips"/u)
  assert.match(seed, /async def seed_stories[\s\S]*?is_active=True,[\s\S]*?expires_at=far_future/u)

  assert.match(viewer, /role=["']dialog["']/u)
  assert.match(viewer, /useFocusTrap<.*>\(\s*\{\s*active:\s*activeStoryIndex !== null/u)
  assert.match(
    viewer,
    /setOverlayState\(STORY_VIEWER_OVERLAY_ID,\s*\{\s*blurred:\s*false,\s*scrollLocked:\s*true\s*\}\)/u
  )
  assert.match(dashboardStories, /event\.key === ["']Escape["']/u)
  assert.match(dashboardStories, /document\.visibilityState === ["']hidden["']/u)
  assert.match(
    dashboardStories,
    /document\.addEventListener\(["']visibilitychange["'],\s*handleVisibilityChange\)/u
  )
  assert.match(dashboardStories, /pausePlayback\(\)/u)
  assert.match(dashboardStories, /resumePlayback\(\)/u)
  assert.match(focusTrap, /returnFocusOnDeactivate:\s*returnFocus/u)
  assert.match(appShell, /document\.body\.style\.overflow = ["']hidden["']/u)
  assert.match(appShell, /document\.body\.style\.overflow = previousOverflowRef\.current/u)

  assert.match(
    spec,
    /a seeded story traps focus, closes with Escape, restores focus, and releases scroll lock/u
  )
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/dashboard["']\)/u)
  assert.match(spec, /page\.route\(["']https:\/\/picsum\.photos\/\*\*["']/u)
  assert.match(spec, /contentType:\s*["']image\/svg\+xml["']/u)
  assert.match(spec, /getByRole\(["']dialog["']\)/u)
  assert.match(spec, /toHaveAccessibleName\(SEEDED_STORY_TITLE\)/u)
  assert.match(spec, /toBeFocused\(\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(spec, /const tabbableControls = dialog\.locator\(/u)
  assert.match(spec, /const firstControl = tabbableControls\.first\(\)/u)
  assert.match(spec, /const lastControl = tabbableControls\.last\(\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Shift\+Tab["']\)/u)
  assert.match(spec, /await expect\(lastControl\)\.toBeFocused\(\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Tab["']\)/u)
  assert.match(spec, /await expect\(firstControl\)\.toBeFocused\(\)/u)
  assert.match(spec, /toBe\(["']hidden["']\)/u)
  assert.match(spec, /toBe\(initialBodyOverflow\)/u)

  const visibilityTestStart = spec.search(
    /storyVisibilityTest\(\s*["']a seeded story pauses while hidden and resumes at the preserved progress["']/u
  )
  assert.ok(
    visibilityTestStart >= 0,
    "live acceptance includes a seeded visibility pause/resume case"
  )
  const visibilityTest = spec.slice(visibilityTestStart)
  assert.match(visibilityTest, /const backgroundPage = await openStoryBackgroundTab\(page\)/u)
  assert.match(visibilityTest, /await backgroundPage\.bringToFront\(\)/u)
  assert.match(visibilityTest, /document\.visibilityState\)[\s\S]*?toBe\(["']hidden["']\)/u)
  assert.match(visibilityTest, /await page\.waitForTimeout\(STORY_HIDDEN_DURATION_MS\)/u)
  assert.match(visibilityTest, /await page\.bringToFront\(\)/u)
  assert.match(visibilityTest, /toBe\(["']visible["']\)/u)
  assert.match(visibilityTest, /toBeGreaterThan\(pausedProgress\)/u)
  assert.match(
    spec,
    /await page\.goto\(new URL\(["']\/dashboard["'],\s*ownedSessionOrigin\(\)\)\.toString\(\)\)/u
  )
  assert.match(visibilityFixture, /connectOverCDP[\s\S]*?noDefaults:\s*true/u)
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
  assert.match(visibilityFixture, /mainWindowId !== backgroundWindowId/u)
  assert.match(
    visibilityFixture,
    /Emulation\.setFocusEmulationEnabled[\s\S]*?\{ enabled: false \}/u
  )
  assert.match(visibilityFixture, /Browser\.getWindowForTarget/u)
  assert.match(visibilityFixture, /mainWindowId !== backgroundWindowId/u)
  assert.match(visibilityFixture, /page\.setDefaultTimeout\(actionTimeout\)/u)
  assert.match(visibilityFixture, /page\.setDefaultNavigationTimeout\(navigationTimeout\)/u)
  assert.doesNotMatch(visibilityFixture, /document\.visibilityState\s*=|dispatchEvent\(/u)
  const autoAdvanceMatch = dashboardStories.match(/const STORY_AUTO_ADVANCE_MS = (\d+)/u)
  const hiddenDurationMatch = visibilityTest.match(/const STORY_HIDDEN_DURATION_MS = ([\d_]+)/u)
  assert.ok(autoAdvanceMatch && hiddenDurationMatch, "pause coverage is bounded by story timing")
  assert.ok(
    Number(hiddenDurationMatch[1].replaceAll("_", "")) > Number(autoAdvanceMatch[1]),
    "the tab remains hidden longer than one story's auto-advance interval"
  )
  assertControlledVisibilityProof(spec, dashboardStories)
  assert.doesNotMatch(spec, /randomUUID|freshPassword|request\.(?:post|put|patch|delete)|\.fill\(/u)
})

test("clock-controlled visibility contract rejects removed pause and resume oracles", async () => {
  const [spec, dashboardStories] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(dashboardStoriesUrl, "utf8"),
  ])
  const controlledStart = spec.indexOf(
    '"a seeded story preserves elapsed playback across a clock-controlled hidden tab"'
  )
  assert.ok(controlledStart >= 0)
  const prefix = spec.slice(0, controlledStart)
  const controlled = spec.slice(controlledStart)
  const mutations = [
    [
      "hidden progress equality",
      "expect(await readProgress()).toBe(pausedProgress)",
      "expect(await readProgress()).toBeGreaterThanOrEqual(pausedProgress)",
    ],
    [
      "hidden clock advancement",
      "await page.clock.fastForward(STORY_HIDDEN_DURATION_MS / 2)",
      "await page.waitForTimeout(STORY_HIDDEN_DURATION_MS / 2)",
    ],
    [
      "hidden progress mutation observer",
      "expect(hiddenProgressChanges).toBe(0)",
      "expect(hiddenProgressChanges).toBeGreaterThanOrEqual(0)",
    ],
    [
      "resumed lower bound",
      "toBeGreaterThan(pausedProgress + MIN_RESUMED_ADVANCE)",
      "toBeGreaterThan(pausedProgress)",
    ],
    [
      "resumed upper bound",
      "toBeLessThan(pausedProgress + MAX_RESUMED_ADVANCE)",
      "toBeLessThan(100)",
    ],
    [
      "broken-pause negative control",
      "toBeGreaterThan(unpausedProgress + 10)",
      "toBeGreaterThan(unpausedProgress - 10)",
    ],
    [
      "negative-control listener cleanup",
      "await page.evaluate((removeBlocker) => removeBlocker(), removeVisibilityBlocker)",
      "await removeVisibilityBlocker.dispose()",
    ],
  ]
  for (const [label, before, after] of mutations) {
    assert.ok(controlled.includes(before), `${label} mutation must change the controlled case`)
    assert.throws(
      () => assertControlledVisibilityProof(prefix + controlled.replace(before, after), dashboardStories),
      { name: "AssertionError" },
      `${label} mutation must be rejected`
    )
  }
})
