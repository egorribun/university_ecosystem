import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { LanguageProvider } from "@/contexts/LanguageContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import i18n from "@/i18n/config"
import { AppearanceSection } from "@/pages/settings/index"

const createMediaQuery = (matches: boolean): MediaQueryList =>
  ({
    matches,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
  }) as unknown as MediaQueryList

const renderSection = () =>
  render(
    <ThemeProvider>
      <LanguageProvider>
        <AppearanceSection setSnackbar={vi.fn()} />
      </LanguageProvider>
    </ThemeProvider>
  )

const openAccordion = (title: string) => {
  const heading = screen.getByText(title)
  fireEvent.click(heading.closest("button")!)
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  window.localStorage.clear()
  document.cookie = "ue:language=; Max-Age=0; Path=/"
  document.cookie = "ue-mode=; Max-Age=0; Path=/"
  vi.spyOn(window, "matchMedia").mockReturnValue(createMediaQuery(false))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("AppearanceSection preferences", () => {
  it("persists a language selected from the appearance controls", async () => {
    window.localStorage.setItem("ue-mode", "light")
    window.localStorage.setItem("ue:language", "en")
    renderSection()
    openAccordion(i18n.t("settings:appearance.language.title"))

    fireEvent.click(
      screen.getByRole("radio", {
        name: i18n.t("settings:appearance.language.options.ru"),
      })
    )

    await waitFor(() => expect(window.localStorage.getItem("ue:language")).toBe("ru"))
    expect(document.documentElement).toHaveAttribute("lang", "ru")
  })

  it("persists a theme selected from the appearance controls", async () => {
    window.localStorage.setItem("ue-mode", "system")
    renderSection()
    openAccordion(i18n.t("settings:appearance.theme.title"))

    fireEvent.click(
      screen.getByRole("radio", {
        name: i18n.t("settings:appearance.theme.options.dark"),
      })
    )

    await waitFor(() => expect(window.localStorage.getItem("ue-mode")).toBe("dark"))
    expect(document.documentElement.dataset.colorScheme).toBe("dark")
  })
})
