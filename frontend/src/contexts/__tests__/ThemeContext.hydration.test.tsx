import { act, StrictMode } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { fireEvent, within } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

import { LanguageProvider } from "@/contexts/LanguageContext"
import i18n from "@/i18n/config"
import { AppearanceSection } from "@/pages/settings/sections/AppearanceSection"
import { ThemeProvider, useTheme } from "../ThemeContext"

let root: Root | undefined
let container: HTMLDivElement | undefined

function ThemeState() {
  const { theme, resolvedTheme } = useTheme()
  return <output aria-label="Current theme">{`${theme}/${resolvedTheme}`}</output>
}

function SettingsAppearance() {
  return (
    <StrictMode>
      <ThemeProvider>
        <LanguageProvider>
          <AppearanceSection setSnackbar={() => undefined} />
          <ThemeState />
        </LanguageProvider>
      </ThemeProvider>
    </StrictMode>
  )
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  localStorage.clear()
  localStorage.setItem("ue:language", "en")
  document.cookie = "ue-mode=; Max-Age=0; Path=/"
  document.cookie = "ue:language=; Max-Age=0; Path=/"
  document.documentElement.classList.remove("dark", "light")
  document.body.classList.remove("dark", "light")
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = undefined
  container?.remove()
  container = undefined
  vi.restoreAllMocks()
  document.documentElement.classList.remove("dark", "light")
  document.body.classList.remove("dark", "light")
})

it.each(["dark", "light", "system"] as const)(
  "hydrates real appearance controls without recovery before restoring stored %s",
  async (storedTheme) => {
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window")!
    let html: string
    Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
    try {
      html = renderToString(<SettingsAppearance />)
    } finally {
      Object.defineProperty(globalThis, "window", originalWindow)
    }
    expect(html).toContain("system/light")
    expect(html).toContain(
      i18n.t("settings:appearance.theme.systemHint", {
        value: i18n.t("settings:appearance.theme.hintOptions.light"),
      })
    )

    localStorage.setItem("ue-mode", storedTheme)
    const cookieSetter = vi.spyOn(document, "cookie", "set")
    const matchMedia = vi.spyOn(window, "matchMedia")
    // Preserve the returning user's pre-paint dark class until the stored
    // preference is restored, including when their system scheme is dark.
    const resolved = storedTheme === "light" ? "light" : "dark"
    document.documentElement.classList.add(resolved)
    document.body.classList.add(resolved)
    matchMedia.mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    const rootClassAdds = vi.spyOn(document.documentElement.classList, "add")
    const bodyClassAdds = vi.spyOn(document.body.classList, "add")
    const recoverableErrors: unknown[] = []
    container = document.createElement("div")
    container.innerHTML = html
    document.body.append(container)
    await act(async () => {
      root = hydrateRoot(container!, <SettingsAppearance />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
    })
    const ui = within(container)
    expect(recoverableErrors).toEqual([])
    expect(ui.getByLabelText("Current theme")).toHaveTextContent(`${storedTheme}/${resolved}`)
    expect(document.documentElement).toHaveClass(resolved)
    expect(document.body).toHaveClass(resolved)
    const opposite = resolved === "dark" ? "light" : "dark"
    expect(rootClassAdds).not.toHaveBeenCalledWith(opposite)
    expect(bodyClassAdds).not.toHaveBeenCalledWith(opposite)
    expect(localStorage.getItem("ue-mode")).toBe(storedTheme)
    const themeCookies = cookieSetter.mock.calls.filter(([cookie]) => cookie.startsWith("ue-mode="))
    expect(themeCookies.length).toBeGreaterThan(0)
    for (const [cookie] of themeCookies) {
      expect(cookie).toBe(`ue-mode=${storedTheme}; Path=/; Max-Age=31536000; SameSite=Lax`)
    }
    if (storedTheme !== "system") expect(matchMedia).not.toHaveBeenCalled()

    const themeTitle = ui.getByText(i18n.t("settings:appearance.theme.title"))
    fireEvent.click(themeTitle.closest("button")!)
    fireEvent.click(
      ui.getByRole("radio", { name: i18n.t("settings:appearance.theme.options.light") })
    )
    expect(localStorage.getItem("ue-mode")).toBe("light")
    expect(document.cookie).toContain("ue-mode=light")
    expect(document.documentElement).toHaveClass("light")
    expect(recoverableErrors).toEqual([])
  }
)
