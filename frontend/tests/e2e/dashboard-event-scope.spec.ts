import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

const VIEWPORTS = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
] as const

for (const viewport of VIEWPORTS) {
  test(`dashboard event scope buttons have 44px targets at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport)
    await page.emulateMedia({ reducedMotion: "reduce" })
    await useMockApi(page, { authenticated: true })
    await page.goto("/dashboard", { waitUntil: "domcontentloaded" })
    await page.waitForFunction(() => window.__APP_HYDRATED === true)

    const events = page.locator(".vt-dash-events")
    const today = events.getByRole("button", { name: /^(Today|Сегодня)$/u })
    const week = events.getByRole("button", { name: /^(This week|Эта неделя)$/u })

    await expect(today).toHaveAttribute("aria-pressed", "true")
    await expect(week).toHaveAttribute("aria-pressed", "false")
    for (const [label, button] of [
      ["Today", today],
      ["This week", week],
    ] as const) {
      await button.click({ trial: true })
      const box = await button.boundingBox()
      if (!box) throw new Error(`${label} does not have a bounding box`)
      expect.soft(box.width, `${label}: width in CSS pixels`).toBeGreaterThanOrEqual(44)
      expect.soft(box.height, `${label}: height in CSS pixels`).toBeGreaterThanOrEqual(44)
    }

    await week.click()
    await expect(week).toHaveAttribute("aria-pressed", "true")
    await expect(today).toHaveAttribute("aria-pressed", "false")
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
}
