import type { Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

test.use({ trace: "off", screenshot: "off", video: "off" })

async function openThemeOptions(page: Page) {
  const accordion = page
    .locator("button:has(h3)")
    .filter({ hasText: /Тема|Theme/i })
    .first()
  await expect(accordion).toBeVisible()
  if ((await accordion.getAttribute("aria-expanded")) === "true") {
    await accordion.click()
  }
  await accordion.click()
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
  return accordion
}

test("Settings radio has a visible keyboard focus style", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/settings")
  await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()

  const accordion = await openThemeOptions(page)
  await expect(accordion).toBeFocused()

  const systemRadio = page.getByRole("radio", { name: /Система|System/i })
  await expect(systemRadio).toBeVisible()
  await expect(systemRadio).toBeChecked()
  const indicator = systemRadio
    .locator("xpath=ancestor::label")
    .locator('[class~="peer-focus-visible:shadow-focus"]')
  await expect(indicator).toHaveCount(1)
  await expect(indicator).toBeVisible()
  const boxShadow = () => indicator.evaluate((element) => getComputedStyle(element).boxShadow)
  const unfocusedShadow = await boxShadow()

  // Only focus changes: no radio selection or persisted setting is changed.
  await page.keyboard.press("Tab")
  await expect(systemRadio).toBeFocused()
  await expect
    .poll(() => systemRadio.evaluate((element) => element.matches(":focus-visible")))
    .toBe(true)
  await expect.poll(boxShadow).not.toBe(unfocusedShadow)
  const focusedShadow = await boxShadow()
  expect(focusedShadow).not.toBe(unfocusedShadow)
  expect(focusedShadow).not.toBe("none")

  await page.keyboard.press("Shift+Tab")
  await expect(accordion).toBeFocused()
  await expect.poll(boxShadow).toBe(unfocusedShadow)
  await expect(systemRadio).toBeChecked()
})

async function readSemanticTokens(page: Page, scheme: "light" | "dark") {
  return page.evaluate((colorScheme) => {
    const host = document.createElement("div")
    host.setAttribute("aria-hidden", "true")
    host.style.cssText =
      "position:fixed;left:-10000px;top:0;width:1px;height:1px;pointer-events:none"
    document.body.append(host)
    try {
      const read = (property: string, value: string) => {
        const probe = document.createElement("div")
        probe.style.setProperty(property, value)
        host.append(probe)
        try {
          return getComputedStyle(probe).getPropertyValue(property)
        } finally {
          probe.remove()
        }
      }
      const panelBase = colorScheme === "dark" ? "var(--color-slate-800)" : "white"
      return {
        panel: read("background-color", "var(--bg-panel)"),
        panelExpected: read(
          "background-color",
          `color-mix(in srgb, ${panelBase} 70%, transparent)`
        ),
        glass: read("box-shadow", "var(--raw-shadow-glass)"),
        glassExpected: read(
          "box-shadow",
          "0 35px 80px color-mix(in srgb, black 20%, transparent)"
        ),
        glow: read("box-shadow", "var(--shadow-glow-primary)"),
        glowExpected: read(
          "box-shadow",
          "0 0 12px color-mix(in srgb, var(--primary-main) 20%, transparent)"
        ),
        opacity: read("opacity", "var(--opacity-dim)"),
        focus: read("box-shadow", "var(--raw-shadow-focus)"),
        focusExpected: read(
          "box-shadow",
          "0 0 0 2px var(--bg-page), 0 0 0 4px var(--primary-main)"
        ),
      }
    } finally {
      host.remove()
    }
  }, scheme)
}

test("Semantic tokens preserve percentage alpha in both themes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/settings")
  await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()
  await openThemeOptions(page)
  const systemRadio = page.getByRole("radio", { name: /Система|System/i })
  await expect(systemRadio).toBeChecked()

  try {
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" })
      await expect(page.locator("html")).toHaveAttribute("data-color-scheme", scheme)
      await expect(page.locator("body")).toHaveAttribute("data-color-scheme", scheme)
      await expect(systemRadio).toBeChecked()
      const tokens = await readSemanticTokens(page, scheme)

      // Controls establish the real stylesheet, theme, and independent expected values.
      expect(tokens.opacity).toBe("0.2")
      expect(tokens.panelExpected).not.toBe("")
      expect(tokens.panelExpected).not.toBe("rgba(0, 0, 0, 0)")
      for (const shadow of [tokens.glassExpected, tokens.glowExpected, tokens.focusExpected]) {
        expect(shadow).not.toBe("")
        expect(shadow).not.toBe("none")
      }
      expect(tokens.focus).toBe(tokens.focusExpected)
      expect(tokens.focus).not.toBe("none")

      expect.soft(tokens.panel, `${scheme} panel percentage`).toBe(tokens.panelExpected)
      expect.soft(tokens.glass, `${scheme} glass percentage`).toBe(tokens.glassExpected)
      expect.soft(tokens.glow, `${scheme} glow percentage`).toBe(tokens.glowExpected)
    }
  } finally {
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  }
})
