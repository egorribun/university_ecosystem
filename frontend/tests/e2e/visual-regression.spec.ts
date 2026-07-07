import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

/**
 * Visual regression tests — W24 pixel-perfect snapshots.
 *
 * Covers 5 key authenticated pages at two viewports:
 *   - Desktop 1280×720
 *   - Mobile  375×812  (iPhone-style)
 *
 * Strategy:
 *   - Inject axe-less AXE_SOURCE not needed here; we only call toHaveScreenshot.
 *   - Mocked API so no real backend required.
 *   - Chromium + Windows only (cross-browser font rendering diverges; mobile-
 *     webkit snapshot variance caused false-fails in Wave 115 baseline work).
 *   - Clock frozen to a fixed date so any date-dependent UI is deterministic.
 *   - `waitForLoadState('networkidle')` + 1500ms settle covers Framer Motion
 *     animations and React Query hydration (pattern from visual.spec.ts).
 */

// Read axe source path for future a11y integration — not used here but keeps
// the import path pattern consistent with a11y-cdn-axe.spec.ts.
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../../node_modules/axe-core/axe.min.js"
)
// Verify the path resolves at module load so spec fails fast if node_modules
// is not installed rather than hanging mid-test.
readFileSync(AXE_SOURCE_PATH, "utf-8").slice(0, 1) // existence check only

// Minimal mock-API import (login helper) — mirrors visual.spec.ts pattern.
import { useMockApi } from "./utils/mockApi"

const SNAPSHOT_OPTS = {
  maxDiffPixelRatio: 0.005, // 0.5% pixel threshold
  animations: "disabled" as const,
}

const SETTLE_MS = 1500

// ─── Desktop viewport ──────────────────────────────────────────────────────
test.describe("Visual regression — desktop (1280×720)", () => {
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "Snapshot baselines are Chromium-only (font rendering varies across engines)"
  )
  test.skip(process.platform !== "win32", "Snapshot baselines are checked-in for Windows only")

  test.use({ viewport: { width: 1280, height: 720 } })

  test.beforeEach(async ({ page }) => {
    // Freeze clock to a deterministic date so date-dependent widgets are stable.
    await page.clock.install({ time: new Date("2026-06-27T10:00:00Z") })
  })

  test("dashboard page matches desktop snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-desktop-dashboard.png", SNAPSHOT_OPTS)
  })

  test("events page matches desktop snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/events")
    await page.waitForURL(/\/events$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-desktop-events.png", SNAPSHOT_OPTS)
  })

  test("messenger page matches desktop snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/messenger")
    await page.waitForURL(/\/messenger$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-desktop-chat.png", SNAPSHOT_OPTS)
  })

  test("profile page matches desktop snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/profile")
    await page.waitForURL(/\/profile$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-desktop-profile.png", SNAPSHOT_OPTS)
  })

  test("schedule page matches desktop snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule")
    await page.waitForURL(/\/schedule$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-desktop-schedule.png", SNAPSHOT_OPTS)
  })
})

// ─── Mobile viewport ───────────────────────────────────────────────────────
test.describe("Visual regression — mobile (375×812)", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "Snapshot baselines are Chromium-only")
  test.skip(process.platform !== "win32", "Snapshot baselines are checked-in for Windows only")

  test.use({ viewport: { width: 375, height: 812 } })

  test.beforeEach(async ({ page }) => {
    await page.clock.install({ time: new Date("2026-06-27T10:00:00Z") })
  })

  test("dashboard page matches mobile snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-mobile-dashboard.png", SNAPSHOT_OPTS)
  })

  test("events page matches mobile snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/events")
    await page.waitForURL(/\/events$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-mobile-events.png", SNAPSHOT_OPTS)
  })

  test("messenger page matches mobile snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/messenger")
    await page.waitForURL(/\/messenger$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-mobile-chat.png", SNAPSHOT_OPTS)
  })

  test("profile page matches mobile snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/profile")
    await page.waitForURL(/\/profile$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-mobile-profile.png", SNAPSHOT_OPTS)
  })

  test("schedule page matches mobile snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule")
    await page.waitForURL(/\/schedule$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(SETTLE_MS)

    await expect(page).toHaveScreenshot("vr-mobile-schedule.png", SNAPSHOT_OPTS)
  })
})
