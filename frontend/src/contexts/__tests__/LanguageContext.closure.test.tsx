import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { i18n as I18nInstance } from "i18next"

import i18n, { createI18nInstance } from "@/i18n/config"
import {
  LanguageProvider,
  getLocaleForLanguage,
  resolveInitialLanguage,
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
  vi.unstubAllGlobals()
  window.localStorage.clear()
  delete window.__UE_SELECTED_LANG__
  void i18n.changeLanguage("ru")
  document.cookie = "ue:language=; Max-Age=0; Path=/"
  Object.defineProperty(window.navigator, "language", {
    configurable: true,
    value: "en-US",
  })
})

describe("LanguageContext browser branches", () => {
  it("prefers a supported stored language and mirrors changes to DOM and cookie", async () => {
    window.localStorage.setItem("ue:language", "en")
    render(<Probe />, { wrapper })

    expect(screen.getByRole("button")).toHaveTextContent("en:en,ru")
    fireEvent.click(screen.getByRole("button"))
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru"))
    await waitFor(() => expect(document.documentElement).toHaveAttribute("lang", "ru"))
    expect(document.documentElement).toHaveAttribute("dir", "ltr")
    expect(document.body).toHaveAttribute("dir", "ltr")
    expect(document.cookie).toContain("ue:language=ru")
  })

  it("keeps DOM synchronization safe when document.body is unavailable", () => {
    const { result } = renderHook(() => useLanguage(), { wrapper })
    const bodyDescriptor = Object.getOwnPropertyDescriptor(document, "body")

    try {
      Object.defineProperty(document, "body", {
        configurable: true,
        value: null,
      })

      act(() => {
        result.current.setLanguage("en")
      })

      expect(document.documentElement).toHaveAttribute("lang", "en")
      expect(document.documentElement).toHaveAttribute("dir", "ltr")
      expect(document.cookie).toContain("ue:language=en")
    } finally {
      if (bodyDescriptor) {
        Object.defineProperty(document, "body", bodyDescriptor)
      } else {
        Reflect.deleteProperty(document, "body")
      }
    }
  })

  it("prefers the server-selected bootstrap language when it is supported", () => {
    window.__UE_SELECTED_LANG__ = "en"

    render(<Probe />, { wrapper })

    expect(screen.getByRole("button")).toHaveTextContent("en:en,ru")
  })

  it("falls back on the server when the i18n instance language is unsupported", () => {
    vi.stubGlobal("window", undefined)

    expect(resolveInitialLanguage({ language: "de" } as I18nInstance)).toBe("ru")
  })

  it("uses the supported i18n instance language during server rendering", () => {
    vi.stubGlobal("window", undefined)

    expect(resolveInitialLanguage({ language: "en" } as I18nInstance)).toBe("en")
  })

  it("falls back when a server i18n instance exposes a non-string language", () => {
    vi.stubGlobal("window", undefined)

    expect(resolveInitialLanguage({ language: 42 } as unknown as I18nInstance)).toBe("ru")
    expect(resolveInitialLanguage({ language: { code: "en" } } as unknown as I18nInstance)).toBe(
      "ru"
    )
  })

  it("marks the mirrored language cookie Secure on HTTPS", async () => {
    const cookieSetter = vi.spyOn(document, "cookie", "set")
    vi.stubGlobal("location", { protocol: "https:" })

    render(<Probe />, { wrapper })

    await waitFor(() =>
      expect(cookieSetter).toHaveBeenCalledWith(expect.stringContaining("; Secure"))
    )
  })

  it("writes the exact non-secure cookie contract on HTTP", async () => {
    const cookieSetter = vi.spyOn(document, "cookie", "set")
    vi.stubGlobal("location", { protocol: "http:" })

    render(<Probe />, { wrapper })

    await waitFor(() =>
      expect(cookieSetter).toHaveBeenCalledWith(
        "ue:language=ru; Path=/; Max-Age=31536000; SameSite=Lax"
      )
    )
    expect(cookieSetter.mock.calls.at(-1)?.[0]).not.toContain("Secure")
  })

  it("keeps the cookie path safe when location is unavailable", async () => {
    const cookieSetter = vi.spyOn(document, "cookie", "set")
    vi.stubGlobal("location", undefined)

    render(<Probe />, { wrapper })

    await waitFor(() => expect(cookieSetter).toHaveBeenCalled())
    expect(cookieSetter.mock.calls.at(-1)?.[0]).toContain("ue:language=ru")
    expect(cookieSetter.mock.calls.at(-1)?.[0]).not.toContain("Secure")
  })

  it("ignores browser locale so the client fallback matches SSR", () => {
    window.localStorage.setItem("ue:language", "de")
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "ru-RU",
    })
    render(<Probe />, { wrapper })
    expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru")
  })

  it("uses Russian when the browser exposes an empty language", () => {
    window.localStorage.setItem("ue:language", "de")
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "",
    })

    render(<Probe />, { wrapper })

    expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru")
  })

  it("falls back to the browser language when localStorage reads are denied", () => {
    Object.defineProperty(window.navigator, "language", {
      configurable: true,
      value: "ru-RU",
    })
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("storage denied", "SecurityError")
    })

    render(<Probe />, { wrapper })

    expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru")
  })

  it("keeps language changes working when localStorage writes fail", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("storage full", "QuotaExceededError")
    })

    render(<Probe />, { wrapper })
    fireEvent.click(screen.getByRole("button"))

    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("ru:en,ru"))
    expect(document.documentElement).toHaveAttribute("lang", "ru")
    expect(document.cookie).toContain("ue:language=ru")
    expect(setItem).toHaveBeenCalled()
  })

  it("updates state through setLanguage and exposes the guard/error contract", async () => {
    const { result } = renderHook(() => useLanguage(), { wrapper })
    expect(result.current.language).toBe("ru")
    const initialSetter = result.current.setLanguage

    act(() => {
      result.current.setLanguage("ru")
    })
    expect(result.current.language).toBe("ru")
    expect(result.current.setLanguage).toBe(initialSetter)
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
    expect(result.current.language).toBe("ru")
  })

  it("applies supported languageChanged events and detaches the listener", async () => {
    const first = createI18nInstance("ru")
    const second = createI18nInstance("ru")
    const firstOn = vi.spyOn(first, "on")
    const firstOff = vi.spyOn(first, "off")
    const secondOn = vi.spyOn(second, "on")
    const secondOff = vi.spyOn(second, "off")
    let current = first
    globalThis.__ssrI18nGetter__ = () => current

    const view = render(<Probe />, { wrapper })
    expect(firstOn).toHaveBeenCalledWith("languageChanged", expect.any(Function))

    current = second
    view.rerender(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>
    )
    expect(firstOff).toHaveBeenCalledWith("languageChanged", expect.any(Function))
    expect(secondOn).toHaveBeenCalledWith("languageChanged", expect.any(Function))

    act(() => {
      second.emit("languageChanged", "en")
    })
    await waitFor(() => expect(screen.getByRole("button")).toHaveTextContent("en:en,ru"))

    view.unmount()
    expect(secondOff).toHaveBeenCalledWith("languageChanged", expect.any(Function))
  })
})
