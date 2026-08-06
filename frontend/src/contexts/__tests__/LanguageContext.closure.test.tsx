import { act, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import {
  LanguageProvider,
  getLocaleForLanguage,
  useLanguage,
  type SupportedLanguage,
} from "@/contexts/LanguageContext"

const wrapper = ({ children }: PropsWithChildren) => <LanguageProvider>{children}</LanguageProvider>

const Probe = () => {
  const { language, available, setLanguage } = useLanguage()
  return (
    <button type="button" onClick={() => setLanguage("ru")}>
      {language}:{available.join(",")}
    </button>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
  document.cookie = "ue:language=; Max-Age=0; Path=/"
  Object.defineProperty(window.navigator, "language", {
    configurable: true,
    value: "en-US",
  })
})

describe("LanguageContext browser branches", () => {
  it("prefers a supported stored language and mirrors it to DOM and cookie", async () => {
    window.localStorage.setItem("ue:language", "ru")
    render(<Probe />, { wrapper })

    expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru")
    await waitFor(() => expect(document.documentElement).toHaveAttribute("lang", "ru"))
    expect(document.documentElement).toHaveAttribute("dir", "ltr")
    expect(document.body).toHaveAttribute("dir", "ltr")
    expect(document.cookie).toContain("ue:language=ru")
  })

  it("falls back to the browser language and then to English", () => {
    window.localStorage.setItem("ue:language", "de")
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "ru-RU",
    })
    const first = render(<Probe />, { wrapper })
    expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru")
    first.unmount()

    window.localStorage.setItem("ue:language", "de")
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "de-DE",
    })
    render(<Probe />, { wrapper })
    expect(screen.getByRole("button")).toHaveTextContent("en:en,ru")
  })

  it("updates state through setLanguage and exposes the guard/error contract", async () => {
    const { result } = renderHook(() => useLanguage(), { wrapper })
    expect(result.current.language).toBe("en")

    act(() => {
      result.current.setLanguage("ru")
    })
    expect(result.current.language).toBe("ru")
    await waitFor(() => expect(window.localStorage.getItem("ue:language")).toBe("ru"))

    expect(() => renderHook(() => useLanguage())).toThrow(
      "useLanguage must be used within a LanguageProvider"
    )
  })

  it("returns formatter locales and a safe fallback for unknown input", () => {
    expect(getLocaleForLanguage("ru")).toBe("ru-RU")
    expect(getLocaleForLanguage("en")).toBe("en-US")
    expect(getLocaleForLanguage("xx" as SupportedLanguage)).toBe("en-US")
  })

  it("ignores unsupported languageChanged events", () => {
    const { result } = renderHook(() => useLanguage(), { wrapper })
    act(() => {
      i18n.emit("languageChanged", "de")
    })
    expect(result.current.language).toBe("en")
  })
})
