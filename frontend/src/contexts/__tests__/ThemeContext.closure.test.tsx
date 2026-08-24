import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ThemeProvider, useTheme } from "../ThemeContext"

function Consumer() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <div>
      <output data-testid="theme">{theme}</output>
      <output data-testid="resolved">{resolvedTheme}</output>
      <button type="button" onClick={() => setTheme("dark")}>
        dark
      </button>
      <button type="button" onClick={() => setTheme("light")}>
        light
      </button>
      <button type="button" onClick={() => setTheme("system")}>
        system
      </button>
    </div>
  )
}

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
)

const createMediaQuery = (initialMatches: boolean) => {
  let matches = initialMatches
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const mediaQuery = {
    get matches() {
      return matches
    },
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    }),
    removeEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    }),
    dispatchChange(nextMatches: boolean) {
      matches = nextMatches
      const event = new Event("change") as MediaQueryListEvent
      for (const listener of listeners) listener(event)
    },
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
  }
  return mediaQuery as unknown as MediaQueryList & { dispatchChange: (matches: boolean) => void }
}

beforeEach(() => {
  localStorage.clear()
  document.cookie = "ue-mode=; Max-Age=0; Path=/"
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("ThemeContext closure", () => {
  it("hydrates a stored dark theme, applies it, and persists subsequent changes", async () => {
    localStorage.setItem("ue-mode", "dark")
    const matchMedia = vi.spyOn(window, "matchMedia")

    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    )

    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("dark"))
    expect(screen.getByTestId("theme")).toHaveTextContent("dark")
    expect(document.documentElement).toHaveClass("dark")
    expect(document.body).toHaveClass("dark")
    expect(matchMedia).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "light" }))
    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("light"))
    expect(localStorage.getItem("ue-mode")).toBe("light")
    expect(document.cookie).toContain("ue-mode=light")
  })

  it("reacts to system color-scheme changes and removes the media listener", async () => {
    localStorage.setItem("ue-mode", "system")
    const mediaQuery = createMediaQuery(true)
    vi.spyOn(window, "matchMedia").mockReturnValue(mediaQuery)
    const { unmount } = render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    )

    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("dark"))
    mediaQuery.dispatchChange(false)
    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("light"))
    expect(mediaQuery.addEventListener).toHaveBeenCalledWith("change", expect.any(Function))

    unmount()
    expect(mediaQuery.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function))
  })

  it("falls back to light without matchMedia and survives storage quota failures", async () => {
    localStorage.setItem("ue-mode", "system")
    vi.spyOn(window, "matchMedia").mockReturnValue(undefined as unknown as MediaQueryList)
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota")
    })

    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    )
    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("light"))
    fireEvent.click(screen.getByRole("button", { name: "dark" }))
    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("dark"))
    expect(setItem).toHaveBeenCalled()
  })

  it("uses the system default for invalid stored values and guards useTheme outside a provider", () => {
    localStorage.setItem("ue-mode", "invalid")
    expect(() => renderHook(() => useTheme())).toThrow(
      "useTheme must be used within a ThemeProvider"
    )
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.theme).toBe("system")
  })

  it("falls back safely when storage reads or cookie decoding fail", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    vi.spyOn(window, "matchMedia").mockReturnValue(undefined as unknown as MediaQueryList)
    vi.spyOn(document, "cookie", "get").mockReturnValue("ue-mode=%E0%A4%A")

    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    )

    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("light"))
    expect(screen.getByTestId("theme")).toHaveTextContent("system")
  })

  it("adds the Secure cookie attribute when the page uses HTTPS", async () => {
    const cookieSetter = vi.spyOn(document, "cookie", "set")
    vi.stubGlobal("location", { protocol: "https:" })
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    )

    await waitFor(() => expect(screen.getByTestId("resolved")).toHaveTextContent("light"))
    fireEvent.click(screen.getByRole("button", { name: "dark" }))
    await waitFor(() =>
      expect(cookieSetter).toHaveBeenLastCalledWith(
        "ue-mode=dark; Path=/; Max-Age=31536000; SameSite=Lax; Secure"
      )
    )
  })
})
