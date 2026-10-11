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
  assert.doesNotMatch(spec, /randomUUID|freshPassword|request\.(?:post|put|patch|delete)|\.fill\(/u)
})
