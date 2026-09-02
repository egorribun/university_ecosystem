import { render, renderHook, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useEffect } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppShellProvider } from "@/contexts/AppShellContext"
import useScrollRestoration from "../useScrollRestoration"

const ScrollHarness = ({ path, mark }: { path: string; mark?: boolean }) => {
  const { markScrollFromBottom, scrollToTop } = useScrollRestoration(path)

  useEffect(() => {
    if (mark) {
      markScrollFromBottom()
    }
  }, [mark, markScrollFromBottom])

  return (
    <button type="button" onClick={() => scrollToTop("auto")}>
      Scroll Top
    </button>
  )
}

describe("useScrollRestoration", () => {
  let scrollRoot: HTMLDivElement

  beforeEach(() => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          media: query,
          matches: query.includes("prefers-reduced-motion"),
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList
    )

    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })

    scrollRoot = document.createElement("div")
    scrollRoot.setAttribute("data-scroll-root", "")
    scrollRoot.style.overflowY = "auto"
    Object.defineProperty(scrollRoot, "scrollHeight", { value: 600, configurable: true })
    Object.defineProperty(scrollRoot, "clientHeight", { value: 500, configurable: true })
    Object.defineProperty(scrollRoot, "scrollTop", {
      value: 120,
      writable: true,
      configurable: true,
    })
    scrollRoot.scrollTo = vi.fn((options?: ScrollToOptions | number, y?: number) => {
      if (typeof options === "number") {
        scrollRoot.scrollTop = options
        return
      }

      if (typeof options === "object" && options !== null) {
        const { top } = options
        scrollRoot.scrollTop = typeof top === "number" ? top : 0
        return
      }

      if (typeof y === "number") {
        scrollRoot.scrollTop = y
      }
    }) as typeof scrollRoot.scrollTo
    document.body.appendChild(scrollRoot)

    window.sessionStorage.clear()
  })

  afterEach(() => {
    document.body.removeChild(scrollRoot)
    vi.restoreAllMocks()
  })

  it("marks and restores scroll position around navigation", async () => {
    const user = userEvent.setup()

    const { rerender } = render(
      <AppShellProvider>
        <ScrollHarness path="/dashboard" />
      </AppShellProvider>
    )

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBeNull()

    rerender(
      <AppShellProvider>
        <ScrollHarness path="/dashboard" mark />
      </AppShellProvider>
    )

    expect(window.sessionStorage.getItem("__scrollTopNext")).toBe("1")

    rerender(
      <AppShellProvider>
        <ScrollHarness path="/news" />
      </AppShellProvider>
    )

    expect(scrollRoot.scrollTop).toBe(0)

    const button = screen.getByRole("button", { name: "Scroll Top" })
    scrollRoot.scrollTop = 200

    await user.click(button)

    expect(scrollRoot.scrollTop).toBe(0)
  })

  it("matches the dashboard root and canonicalizes trailing slashes", () => {
    const { result, rerender } = renderHook(
      ({ path }: { path: string }) => useScrollRestoration(path),
      {
        initialProps: { path: "/" },
        wrapper: ({ children }) => <AppShellProvider>{children}</AppShellProvider>,
      }
    )

    expect(result.current.isSamePath("/dashboard")).toBe(true)

    rerender({ path: "/dashboard/" })
    expect(result.current.isSamePath("/dashboard")).toBe(true)

    rerender({ path: "/news/" })
    expect(result.current.isSamePath("/news")).toBe(true)
    expect(result.current.isSamePath("/events")).toBe(false)
  })
})
