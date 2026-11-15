import { expect, loginAs, test } from "./fixtures"
import {
  expectEmptySearchResults,
  expectHighlightedSearchResults,
  expectRelevantSearchResults,
  installSearchReadinessProbe,
} from "../e2e/utils/searchFullText"

test("SearchDialog traps Tab and restores the original focus", async ({ page }) => {
  await page.addInitScript(() => {
    const state = window as Window & { __ueDeferredOverlaysReady?: boolean }
    state.__ueDeferredOverlaysReady = false
    window.addEventListener(
      "ue:deferred-global-overlays-ready",
      () => {
        state.__ueDeferredOverlaysReady = true
      },
      { once: true }
    )
  })
  await loginAs(page, "student")
  await page.goto("/dashboard")
  await page.evaluate(() => localStorage.removeItem("ue:recent-searches"))

  const originalFocus = page.locator("#navbar-logo-link")
  await expect(originalFocus).toBeVisible()
  await originalFocus.focus()
  await expect(originalFocus).toBeFocused()
  await page.waitForFunction(() => {
    const state = window as Window & { __ueDeferredOverlaysReady?: boolean }
    return state.__ueDeferredOverlaysReady === true
  })

  await page.keyboard.press("Control+k")
  const dialog = page.getByRole("dialog")
  const input = dialog.getByRole("textbox", { name: /Поиск по приложению|Search the application/u })
  await expect(dialog).toBeVisible()
  await expect(input).toBeFocused()
  await expect(dialog.getByRole("button")).toHaveCount(0)

  // One character reveals the clear button without enabling a search request.
  await page.keyboard.type("x")
  const clear = dialog.getByRole("button", { name: /Очистить поиск|Clear search/u })
  await expect(input).toBeFocused()
  await expect(clear).toBeVisible()
  await expect(dialog.getByRole("button")).toHaveCount(1)

  await page.keyboard.press("Tab")
  await expect(clear).toBeFocused()
  await page.keyboard.press("Tab")
  await expect(input).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(clear).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(input).toBeFocused()

  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await expect(originalFocus).toBeFocused()
})

test("compact navbar preserves native profile keyboard access", async ({ page }) => {
  // Expanded NavbarPill is full-width, not capped by the compact pill max-width.
  // Exercise the original name-focus contract where the 18rem container fits.
  await page.setViewportSize({ width: 1920, height: 900 })
  await loginAs(page, "student")
  // Match SSR and client preferences only in this test's fresh browser context.
  // Russian navigation labels exercise the constrained-width fallback below.
  await page
    .context()
    .addCookies([{ name: "ue:language", value: "ru", url: new URL(page.url()).origin }])
  await page.addInitScript(() => window.localStorage.setItem("ue:language", "ru"))
  await page.goto("/news")
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.locator("html")).toHaveAttribute("lang", "ru")
  await expect(page.getByRole("main")).toBeVisible()
  await page.evaluate(() => document.fonts.ready)

  const navbar = page.locator("nav.vt-navbar")
  const name = navbar.locator(".navbar-user-name button")
  const avatar = name.locator("xpath=../preceding-sibling::button[1]")
  const settings = navbar.locator("#navbar-settings-btn")
  const profileActions = navbar.locator('[class~="@container/profile-actions"]')
  const readProfileActionsWidthRem = () =>
    profileActions.evaluate(
      (element) =>
        element.getBoundingClientRect().width /
        Number.parseFloat(getComputedStyle(document.documentElement).fontSize)
    )
  const readKeyboardState = () =>
    navbar.evaluate((element) => {
      const name = element.querySelector<HTMLButtonElement>(".navbar-user-name button")
      const avatar = name?.parentElement?.previousElementSibling
      const settings = element.querySelector("#navbar-settings-btn")
      const active = document.activeElement

      return {
        scrollY: window.scrollY,
        disabled: name?.disabled === true,
        hidden: name?.getAttribute("aria-hidden") === "true",
        focus:
          active === avatar
            ? "avatar"
            : active === name
              ? "name"
              : active === settings
                ? "settings"
                : active === document.body
                  ? "body"
                  : "other",
      }
    })
  await expect(navbar).toBeVisible()
  await expect(name).toHaveCount(1)
  await expect(avatar).toHaveCount(1)
  await expect(settings).toHaveCount(1)
  const scrollRange = await page.evaluate(
    () => document.documentElement.scrollHeight - window.innerHeight
  )
  expect(scrollRange).toBeGreaterThan(180)

  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(readProfileActionsWidthRem).toBeGreaterThanOrEqual(18)
  await expect(name).toBeVisible()
  await expect(name).toBeEnabled()
  await avatar.focus()
  await page.keyboard.press("Tab")
  await expect(name).toBeFocused()

  // Do not blur or redirect focus: native disabling must release the hidden name.
  await page.evaluate(() => window.scrollTo(0, 180))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(180)
  await expect(name).toBeDisabled()
  await expect(name).toHaveAttribute("aria-hidden", "true")
  await expect(name).not.toBeFocused()

  await avatar.focus()
  const afterAvatar = await readKeyboardState()
  expect.soft(afterAvatar.scrollY).toBeGreaterThan(24)
  expect.soft(afterAvatar.disabled).toBe(true)
  expect.soft(afterAvatar.hidden).toBe(true)
  expect.soft(afterAvatar.focus).toBe("avatar")

  await page.keyboard.press("Tab")
  await expect(settings).toBeFocused()
  // Native focus navigation may scroll the sticky navbar back into expanded mode.
  // Re-establish compact mode without changing the settings button's focus.
  await page.evaluate(() => window.scrollTo(0, 180))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(180)
  await expect(name).toBeDisabled()
  await expect(name).toHaveAttribute("aria-hidden", "true")
  await expect(settings).toBeFocused()

  await page.keyboard.press("Shift+Tab")
  await expect(avatar).toBeFocused()

  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(readProfileActionsWidthRem).toBeGreaterThanOrEqual(18)
  await expect(name).toBeVisible()
  await expect(name).toBeEnabled()
  await expect(name).toHaveAttribute("aria-hidden", "false")
  await avatar.focus()
  await page.keyboard.press("Tab")
  await expect(name).toBeFocused()
  await page.keyboard.press("Enter")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/profile")
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.locator("html")).toHaveAttribute("lang", "ru")
  await expect(page.getByRole("main")).toBeVisible()

  // This is the available-width fallback, not scroll-driven compact mode:
  // the enabled name is CSS-hidden while its complete identity still describes
  // the avatar. Neither expected branch may pass just because a control is absent.
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto("/news")
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.locator("html")).toHaveAttribute("lang", "ru")
  await expect(page.getByRole("main")).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(readProfileActionsWidthRem).toBeLessThan(18)
  await expect(name).toHaveCount(1)
  await expect(name.locator("..")).toHaveCSS("display", "none")
  await expect(name).toBeHidden()
  await expect(name).toBeEnabled()
  await expect(name).toHaveAttribute("aria-hidden", "false")
  await expect(name).toHaveText("Тест Студентов")
  await expect(avatar).toBeVisible()
  await expect(avatar).toBeEnabled()
  await expect(avatar).toHaveAccessibleName("Открыть профиль")
  await expect(avatar).toHaveAccessibleDescription("Открыть профиль: Тест Студентов")
  await expect(settings).toBeVisible()
  await expect(settings).toBeEnabled()
  await avatar.focus()
  await page.keyboard.press("Tab")
  await expect(settings).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(avatar).toBeFocused()
  await page.keyboard.press("Enter")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/profile")
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.locator("html")).toHaveAttribute("lang", "ru")
  await expect(page.getByRole("main")).toBeVisible()
})

test.describe("controlled full-text search", () => {
  test.use({ serviceWorkers: "block" })

  test("full-text search requires the controlled relevant results", async ({ page }) => {
    await installSearchReadinessProbe(page)
    await loginAs(page, "student")
    await page.goto("/dashboard")
    await expectRelevantSearchResults(page)
  })

  test("full-text search requires visible matched-term highlights", async ({ page }) => {
    await installSearchReadinessProbe(page)
    await loginAs(page, "student")
    await page.goto("/dashboard")
    await expectHighlightedSearchResults(page)
  })

  test("full-text search requires the controlled empty state", async ({ page }) => {
    await installSearchReadinessProbe(page)
    await loginAs(page, "student")
    await page.goto("/dashboard")
    await expectEmptySearchResults(page)
  })
})
