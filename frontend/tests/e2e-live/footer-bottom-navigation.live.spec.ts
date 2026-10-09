import { expect, loginAs, test } from "./fixtures"
import type { Page } from "@playwright/test"

const NAVIGATION_PATHS = ["/dashboard", "/news", "/events", "/schedule", "/profile"] as const
const SHORT_ACTIVITY_EMPTY_STATE = '.activity-theme section[aria-live="polite"]'
const SEEDED_LONG_ARTICLE =
  /ГУУ вошёл в топ-20 лучших университетов страны|GUU ranks among the country's top 20 universities/u

test.use({ trace: "off", screenshot: "off", video: "off" })

async function verifyFooterDoesNotOverlapBottomNavigation(page: Page): Promise<void> {
  const footer = page.getByRole("contentinfo")
  const bottomNavigation = page.locator('nav:has(a[data-tab-key="/dashboard"])')
  await expect(footer).toBeVisible()
  await expect(bottomNavigation).toBeVisible()

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollHeight - window.innerHeight - window.scrollY
      )
    )
    .toBeLessThanOrEqual(1)

  const geometry = await page.evaluate(() => {
    const footerElement = document.querySelector<HTMLElement>('footer[role="contentinfo"]')
    const navElement = document.querySelector<HTMLElement>('nav:has(a[data-tab-key="/dashboard"])')
    if (!footerElement || !navElement) throw new Error("production footer or mobile nav is missing")
    const footerRect = footerElement.getBoundingClientRect()
    const navRect = navElement.getBoundingClientRect()
    return {
      footerBottom: footerRect.bottom,
      navTop: navRect.top,
      navBottom: navRect.bottom,
      viewportHeight: window.innerHeight,
    }
  })

  expect(geometry.navBottom).toBeCloseTo(geometry.viewportHeight, 0)
  expect(
    geometry.footerBottom,
    "footer should clear the fixed bottom navigation"
  ).toBeLessThanOrEqual(geometry.navTop + 1)
}

test("bottom navigation fits phone widths, keeps 44px targets, and yields at tablet width", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAs(page, "student")
  await page.goto("/dashboard")
  await expect(page.getByRole("main")).toBeVisible()

  const bottomNavigation = page.locator('nav:has(a[data-tab-key="/dashboard"])')
  for (const width of [390, 360]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(bottomNavigation).toBeVisible()
    const navigationRect = await bottomNavigation.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
    })
    expect(navigationRect.left, `${width}px nav left edge`).toBeCloseTo(0, 0)
    expect(navigationRect.right, `${width}px nav right edge`).toBeCloseTo(width, 0)
    expect(navigationRect.top, `${width}px nav height`).toBeLessThanOrEqual(844 - 64)
    expect(navigationRect.bottom, `${width}px nav bottom edge`).toBeCloseTo(844, 0)

    for (const path of NAVIGATION_PATHS) {
      const link = bottomNavigation.locator(`a[data-tab-key="${path}"]`)
      await expect(link).toBeVisible()
      const target = await link.evaluate((element) => {
        const rect = element.getBoundingClientRect()
        return { width: rect.width, height: rect.height }
      })
      expect(target.width, `${width}px ${path} target width`).toBeGreaterThanOrEqual(44)
      expect(target.height, `${width}px ${path} target height`).toBeGreaterThanOrEqual(44)
    }
  }

  const keyboardNewsLink = bottomNavigation.locator('a[data-tab-key="/news"]')
  await keyboardNewsLink.focus()
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/news\/?$/u)
  await expect(bottomNavigation.locator('a[data-tab-key="/news"]')).toHaveAttribute(
    "aria-current",
    "page"
  )

  await page.setViewportSize({ width: 1024, height: 900 })
  await expect(bottomNavigation).toBeHidden()
  await expect(page.locator('button[aria-controls="mobile-drawer"]')).toHaveCount(0)
  const navbar = page.locator("nav.vt-navbar")
  await expect(navbar).toBeVisible()
  await expect(navbar.locator(".navbar-desktop-nav")).toBeVisible()
  const shell = await navbar.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return {
      left: rect.left,
      right: rect.right,
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }
  })
  expect(shell.left).toBeGreaterThanOrEqual(0)
  expect(shell.right).toBeLessThanOrEqual(1024)
  expect(shell.scrollWidth).toBeLessThanOrEqual(shell.clientWidth + 1)
})

test("footer clears the bottom navigation on short and long production pages", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAs(page, "student")

  await page.goto("/activity")
  await expect(page.locator(".activity-theme")).toBeVisible()
  // The demo seed intentionally has no attendance, grade, or participation
  // records, so this route exercises the real short-content empty state.
  await expect(page.locator(SHORT_ACTIVITY_EMPTY_STATE)).toBeVisible()
  const shortContentHeight = await page
    .locator(".activity-theme")
    .evaluate((element) => element.getBoundingClientRect().height)
  expect(shortContentHeight, "activity empty state should remain a short page").toBeLessThan(844)

  const shortPageFooterTop = await page
    .getByRole("contentinfo")
    .evaluate((element) => element.getBoundingClientRect().top)
  expect(shortPageFooterTop).toBeGreaterThan(844)
  await verifyFooterDoesNotOverlapBottomNavigation(page)

  await page.goto("/news")
  const articleLink = page.getByRole("link", { name: SEEDED_LONG_ARTICLE })
  await expect(articleLink).toBeVisible()
  await articleLink.click()
  await expect(page).toHaveURL(/\/news\/[^/]+$/u)
  await expect(page.getByRole("heading", { name: SEEDED_LONG_ARTICLE })).toBeVisible()
  await expect
    .poll(() =>
      page.evaluate(
        () => (document.querySelector("main")?.scrollHeight ?? 0) > window.innerHeight * 1.5
      )
    )
    .toBe(true)
  await verifyFooterDoesNotOverlapBottomNavigation(page)
})
