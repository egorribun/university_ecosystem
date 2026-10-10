import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./story-viewer-reduced-motion.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const storyViewerUrl = new URL("../../src/components/stories/StoryViewer.tsx", import.meta.url)
const motionStylesUrl = new URL("../../src/styles/partials/_modern-css.css", import.meta.url)

test("live Stories acceptance verifies keyboard access and reduced motion in Chromium", async () => {
  const [spec, config, storyViewer, motionStyles] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(storyViewerUrl, "utf8"),
    readFile(motionStylesUrl, "utf8"),
  ])

  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(
    storyViewer,
    /prefersReducedMotion\s*=\s*useMediaQuery\(["']\(prefers-reduced-motion: reduce\)["']\)/u
  )
  assert.match(storyViewer, /animated=\{!prefersReducedMotion\}/u)
  assert.match(
    motionStyles,
    /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.css-scale-in[\s\S]*?transition-duration:\s*0\.01s\s*!important/u
  )

  assert.match(
    spec,
    /test\(["']StoryViewer stays keyboard-operable without meaningful motion under reduced motion["']/u
  )
  assert.match(spec, /page\.emulateMedia\(\{\s*reducedMotion:\s*["']reduce["']\s*\}\)/u)
  assert.match(spec, /matchMedia\(["']\(prefers-reduced-motion: reduce\)["']\)/u)
  assert.match(spec, /getComputedStyle\([\s\S]*?transitionDuration/u)
  assert.match(spec, /role="dialog"/u)
  assert.match(spec, /getByRole\(["']button["'],\s*\{\s*name:\s*["']Закрыть просмотр историй/u)
  assert.match(spec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(spec, /await expect\(trigger\)\.toBeFocused\(\)/u)
  assert.match(spec, /MAX_REDUCED_MOTION_DURATION_MS\s*=\s*10/u)
})
