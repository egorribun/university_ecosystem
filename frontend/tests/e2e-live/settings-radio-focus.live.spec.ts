import type { Page } from "@playwright/test"
import { expect, loginAs, ROLES, test } from "./fixtures"

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
    const dashboard = document.querySelector(".dashboard-theme")
    const scope = dashboard ?? document.body
    scope.append(host)
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
      const dark = colorScheme === "dark"
      const mix = (color: string, percentage: number) =>
        `color-mix(in srgb, ${color} ${percentage}%, transparent)`
      const shadow = (geometry: string, color: string, percentage: number) =>
        `${geometry} ${mix(color, percentage)}`
      const gradient = (direction: string, stops: string[]) =>
        `linear-gradient(${direction}, ${stops.join(", ")})`
      const radial = (color: string, percentage: number, fade: number) =>
        `radial-gradient(120% 180% at -10% -20%, ${mix(color, percentage)}, transparent ${fade}%)`
      const navLight = [
        radial("var(--color-blue-400)", 50, 58),
        gradient("112deg", [
          "var(--bg-surface) 0%",
          "color-mix(in srgb, var(--bg-surface) 96%, var(--color-black) 4%) 100%",
        ]),
      ].join(", ")
      const navDark = [
        radial("var(--color-sky-400)", 20, 58),
        gradient("112deg", ["var(--color-slate-950) 0%", "var(--color-slate-900) 100%"]),
      ].join(", ")
      const footerLight = [
        radial("var(--color-blue-400)", 15, 60),
        gradient("112deg", ["var(--primary-main) 0%", "var(--primary-hover) 100%"]),
      ].join(", ")
      const cases = [
        {
          name: "bg-surface-tint",
          property: "background-color",
          expected: mix("var(--primary-main)", 5),
        },
        {
          name: "error-bg",
          property: "background-color",
          expected: mix("var(--error-text)", 10),
        },
        {
          name: "shadow-matte-card",
          property: "box-shadow",
          expected: [
            shadow("0 4px 20px", dark ? "black" : "var(--color-slate-400)", dark ? 20 : 10),
            shadow("0 1px 3px", "black", dark ? 10 : 5),
          ].join(", "),
        },
        {
          name: "shadow-matte-card-hover",
          property: "box-shadow",
          expected: [
            shadow("0 8px 30px", dark ? "black" : "var(--color-slate-400)", dark ? 30 : 20),
            shadow("0 2px 6px", "black", dark ? 20 : 10),
          ].join(", "),
        },
        {
          name: "raw-shadow-sm",
          property: "box-shadow",
          expected: [shadow("0 1px 3px", "black", 10), shadow("0 1px 2px", "black", 5)].join(", "),
        },
        {
          name: "raw-shadow-inner-premium",
          property: "box-shadow",
          expected: shadow("inset 0 1px 0", "white", 10),
        },
        {
          name: "glass-bg-low",
          property: "background-color",
          expected: mix("white", 10),
        },
        {
          name: "glass-sheen",
          property: "background-image",
          expected: gradient("135deg", [
            `${mix("white", 20)} 0%`,
            `${mix("white", 5)} 50%`,
            "transparent 100%",
          ]),
        },
        {
          name: "grad-news-hero",
          property: "background-image",
          expected: gradient("180deg", [
            "transparent 30%",
            `${mix("var(--color-slate-900)", 70)} 95%`,
          ]),
        },
        {
          name: "msg-header-bg",
          property: "background-color",
          expected: mix(dark ? "var(--color-slate-900)" : "white", 90),
        },
        {
          name: "glass-border",
          property: "background-color",
          expected: mix(dark ? "var(--color-white)" : "white", dark ? 10 : 20),
        },
        {
          name: "glass-tint3",
          property: "background-color",
          expected: mix(dark ? "var(--color-black)" : "white", dark ? 30 : 5),
        },
        {
          name: "glass-bg-high",
          property: "background-color",
          expected: mix("white", 20),
        },
        { name: "grad-nav-light", property: "background-image", expected: navLight },
        { name: "grad-nav-dark", property: "background-image", expected: navDark },
        { name: "bg-footer-light", property: "background-image", expected: footerLight },
        { name: "bg-footer-dark", property: "background-image", expected: navDark },
      ]
      return {
        cohort: cases.map(({ name, property, expected }) => ({
          name,
          property,
          actual: read(property, `var(--${name})`),
          expected: read(property, expected),
        })),
        dashboardOrb: dashboard ? read("background-color", "var(--dash-hero-orb)") : null,
        dashboardOrbExpected: dashboard
          ? read("background-color", mix("var(--color-sky-400)", dark ? 18 : 15))
          : null,
        panel: read("background-color", "var(--bg-panel)"),
        panelExpected: read(
          "background-color",
          `color-mix(in srgb, ${panelBase} 70%, transparent)`
        ),
        glass: read("box-shadow", "var(--raw-shadow-glass)"),
        glassExpected: read("box-shadow", "0 35px 80px color-mix(in srgb, black 20%, transparent)"),
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
      for (const probe of tokens.cohort) {
        const label = `${scheme} ${probe.name} percentage`
        expect(probe.expected, label).not.toBe("")
        if (probe.property === "background-color") {
          expect(probe.expected, label).not.toBe("rgba(0, 0, 0, 0)")
        } else {
          expect(probe.expected, label).not.toBe("none")
        }
        expect.soft(probe.actual, label).toBe(probe.expected)
      }
    }

    // Dashboard CSS is lazy-loaded. Observe its real route scope rather than
    // adding a theme class or stylesheet to the Settings document.
    await page.goto("/dashboard")
    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page.locator(".dashboard-theme")).toBeVisible()
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" })
      await expect(page.locator("html")).toHaveAttribute("data-color-scheme", scheme)
      await expect(page.locator("body")).toHaveAttribute("data-color-scheme", scheme)
      const tokens = await readSemanticTokens(page, scheme)
      const label = `${scheme} dash-hero-orb percentage`
      expect(tokens.opacity, label).toBe("0.2")
      expect(tokens.dashboardOrbExpected, label).not.toBeNull()
      expect(tokens.dashboardOrbExpected, label).not.toBe("")
      expect(tokens.dashboardOrbExpected, label).not.toBe("rgba(0, 0, 0, 0)")
      expect.soft(tokens.dashboardOrb, label).toBe(tokens.dashboardOrbExpected)
    }
  } finally {
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  }
})

test("Settings Snackbar content receives a real pointer click on Profile", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  // Install before navigation, but let authentication and rendering run normally.
  await page.clock.install()

  try {
    await loginAs(page, "student")
    await page.goto("/profile")
    await page.waitForFunction(() => window.__APP_HYDRATED === true)
    await expect(page).toHaveURL(/\/profile$/u)

    const email = page.getByRole("button", {
      name: ROLES.student.email,
      exact: true,
    })
    await expect(email).toHaveCount(1)
    await expect(email).toBeVisible()
    await expect(email).toBeEnabled()
    // Scroll and finish normal actionability checks before pausing app timers.
    await email.click({ trial: true })

    const feedback = page.getByTestId("profile-save-feedback")
    const alert = feedback.getByRole("alert")
    await expect(alert).toHaveCount(0)

    const pauseTime = await page.evaluate(() => Date.now() + 1000)
    await page.clock.pauseAt(pauseTime)
    const pausedNow = await page.evaluate(() => Date.now())

    // This production handler only opens local feedback; it does not copy or navigate.
    await email.click({ timeout: 3000 })
    await expect(page).toHaveURL(/\/profile$/u)
    await expect(alert).toHaveCount(1)
    await expect(alert).toBeVisible()

    const close = alert.getByRole("button", { name: "×", exact: true })
    await expect(close).toHaveCount(1)
    await expect(close).toBeVisible()
    await expect(close).toBeEnabled()

    const hit = await close.evaluate((button) => {
      const rect = button.getBoundingClientRect()
      const x = rect.left + rect.width / 2
      const y = rect.top + rect.height / 2
      const target = document.elementFromPoint(x, y)
      return {
        positiveArea: rect.width > 0 && rect.height > 0,
        centerInsideViewport: x >= 0 && x < window.innerWidth && y >= 0 && y < window.innerHeight,
        ownsCenter: target !== null && button.contains(target),
        pointerEvents: getComputedStyle(button).pointerEvents,
      }
    })

    expect(hit, "the visible close button must own its actual browser hit target").toMatchObject({
      positiveArea: true,
      centerInsideViewport: true,
      ownsCenter: true,
    })

    await close.click({ timeout: 3000 })
    await expect(alert).toHaveCount(0)
    expect(await page.evaluate(() => Date.now())).toBe(pausedNow)
  } finally {
    // Resume even on the intended RED, before owned-session fixture cleanup.
    await page.clock.resume()
  }
})
