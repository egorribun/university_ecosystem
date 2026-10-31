import { expect, test } from "@playwright/test"

const scenarios = [
  { theme: "light", system: "light" },
  { theme: "light", system: "dark" },
  { theme: "dark", system: "light" },
  { theme: "dark", system: "dark" },
] as const
const themeClass = { light: /\blight\b/u, dark: /\bdark\b/u }

for (const { theme, system } of scenarios) {
  test(`AUD-304: explicit ${theme} theme with ${system} system colors`, async ({
    page,
    baseURL,
  }, testInfo) => {
    if (!baseURL) throw new Error("The theme test requires a configured baseURL")

    const pageErrors: string[] = []
    const consoleErrors: string[] = []
    page.on("pageerror", (error) => pageErrors.push(error.message))
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text())
    })
    await page.emulateMedia({ colorScheme: system, reducedMotion: "reduce" })
    await page.context().addCookies([{ name: "ue-mode", value: theme, url: baseURL }])
    await page.addInitScript((value) => localStorage.setItem("ue-mode", value), theme)
    await page.goto("/reset-password")

    expect(new URL(page.url()).pathname).toBe("/reset-password")
    const toggle = page.locator("#reset-password-toggle")
    await expect(toggle).toBeVisible()
    await expect(page.locator("html")).toHaveClass(themeClass[theme])
    await expect(page.locator("body")).toHaveClass(themeClass[theme])
    await expect(page.locator("html")).not.toHaveClass(
      themeClass[theme === "dark" ? "light" : "dark"]
    )
    expect(await page.evaluate(() => localStorage.getItem("ue-mode"))).toBe(theme)
    expect(await page.evaluate(() => matchMedia("(prefers-color-scheme: dark)").matches)).toBe(
      system === "dark"
    )
    await expect(toggle).toHaveClass(/dark:hover:bg-white/u)

    const hoverCapable = await page.evaluate(() => matchMedia("(hover: hover)").matches)
    if (hoverCapable) await toggle.hover()
    const sample = await toggle.evaluate((element) => {
      const color = getComputedStyle(element).backgroundColor
      const canvas = document.createElement("canvas")
      canvas.width = 1
      canvas.height = 1
      const context = canvas.getContext("2d", { willReadFrequently: true })
      if (!context || !CSS.supports("color", color)) throw new Error(`Unsupported color: ${color}`)
      context.fillStyle = color
      context.fillRect(0, 0, 1, 1)
      return {
        color,
        hovered: element.matches(":hover"),
        rgba: Array.from(context.getImageData(0, 0, 1, 1).data),
        stylesheets: Array.from(document.styleSheets, (sheet) => sheet.href).filter(Boolean),
      }
    })
    const [red, green, blue, alpha] = sample.rgba
    if (hoverCapable) {
      expect(sample.hovered).toBe(true)
      expect(alpha).toBeGreaterThan(0)
      for (const channel of [red, green, blue]) {
        if (theme === "dark") expect(channel).toBeGreaterThanOrEqual(220)
        else expect(channel).toBeLessThanOrEqual(35)
      }
    } else {
      // Tailwind intentionally places hover utilities under (hover: hover).
      expect(alpha).toBe(0)
    }

    await testInfo.attach("computed-style.json", {
      body: Buffer.from(JSON.stringify({ theme, system, hoverCapable, ...sample }, null, 2)),
      contentType: "application/json",
    })
    await testInfo.attach("hover.png", {
      body: await page.screenshot(),
      contentType: "image/png",
    })

    const input = page.locator("#reset-password-input")
    await expect(input).toHaveAttribute("type", "password")
    await toggle.click()
    await expect(input).toHaveAttribute("type", "text")
    await expect(toggle).toHaveAttribute("aria-pressed", "true")
    await testInfo.attach("browser-health.json", {
      body: Buffer.from(JSON.stringify({ title: await page.title(), pageErrors, consoleErrors })),
      contentType: "application/json",
    })
    expect(pageErrors).toEqual([])
  })
}
