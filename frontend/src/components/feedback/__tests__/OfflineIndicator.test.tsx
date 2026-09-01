import { render, screen, act } from "@testing-library/react"
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"

const reactEffects = vi.hoisted(() => ({ dependencies: [] as unknown[] }))

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>()
  return {
    ...actual,
    useEffect: (effect: Parameters<typeof actual.useEffect>[0], dependencies?: unknown[]) => {
      reactEffects.dependencies.push(dependencies)
      return actual.useEffect(effect, dependencies as Parameters<typeof actual.useEffect>[1])
    },
  }
})

const translation = vi.hoisted(() => ({
  useTranslation: vi.fn(() => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: translation.useTranslation,
}))

import { OfflineIndicator } from "@/components/feedback/OfflineIndicator"
import { TIMEOUTS } from "@/config/timeouts"

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, writable: true, value })
}

afterEach(() => {
  vi.useRealTimers()
  setOnline(true)
})

beforeEach(() => {
  translation.useTranslation.mockClear()
  reactEffects.dependencies.length = 0
})

describe("OfflineIndicator", () => {
  it("renders nothing while online", () => {
    setOnline(true)
    render(<OfflineIndicator />)
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(translation.useTranslation).toHaveBeenCalledWith("system")
  })

  it("shows the offline toast when navigator starts offline", async () => {
    setOnline(false)
    render(<OfflineIndicator />)
    const toast = await screen.findByRole("status")
    expect(toast).toHaveTextContent("You're offline")
    expect(toast).toHaveClass(
      "fixed",
      "bottom-24",
      "left-1/2",
      "z-toast",
      "bg-(--warning-bg)",
      "border-(--warning-text)/(--opacity-dim)",
      "text-(--warning-text)"
    )
  })

  it("reacts to offline → online events and auto-hides the back-online toast", () => {
    vi.useFakeTimers()
    setOnline(true)
    render(<OfflineIndicator />)
    expect(screen.queryByRole("status")).not.toBeInTheDocument()

    setOnline(false)
    act(() => {
      window.dispatchEvent(new Event("offline"))
    })
    const offlineToast = screen.getByRole("status")
    expect(offlineToast).toHaveTextContent("You're offline")
    expect(offlineToast).toHaveClass(
      "bg-(--warning-bg)",
      "border-(--warning-text)/(--opacity-dim)",
      "text-(--warning-text)"
    )

    setOnline(true)
    act(() => {
      window.dispatchEvent(new Event("online"))
    })
    const onlineToast = screen.getByRole("status")
    expect(onlineToast).toHaveTextContent("Back online")
    expect(onlineToast).toHaveClass(
      "bg-(--success-bg)",
      "border-(--success-text)/(--opacity-dim)",
      "text-(--success-text)"
    )

    act(() => {
      vi.advanceTimersByTime(TIMEOUTS.OFFLINE_INDICATOR + 100)
    })
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("keeps an offline toast visible until the connection is restored", () => {
    vi.useFakeTimers()
    setOnline(false)
    render(<OfflineIndicator />)

    screen.getByText("You're offline")
    act(() => {
      vi.advanceTimersByTime(TIMEOUTS.OFFLINE_INDICATOR + 100)
    })
    expect(screen.getByText("You're offline")).toBeInTheDocument()
  })

  it("cancels a pending online hide timer when the connection drops again", () => {
    vi.useFakeTimers()
    setOnline(true)
    render(<OfflineIndicator />)

    act(() => {
      window.dispatchEvent(new Event("online"))
    })
    screen.getByText("Back online")

    setOnline(false)
    act(() => {
      window.dispatchEvent(new Event("offline"))
    })
    screen.getByText("You're offline")

    act(() => {
      vi.advanceTimersByTime(TIMEOUTS.OFFLINE_INDICATOR + 100)
    })
    expect(screen.getByText("You're offline")).toBeInTheDocument()
  })

  it("removes browser event listeners on unmount", () => {
    setOnline(true)
    const removeEventListener = vi.spyOn(window, "removeEventListener")
    const { unmount } = render(<OfflineIndicator />)
    unmount()

    expect(removeEventListener).toHaveBeenCalledWith("online", expect.any(Function))
    expect(removeEventListener).toHaveBeenCalledWith("offline", expect.any(Function))
    removeEventListener.mockRestore()
  })

  it("registers the online and offline events with their canonical names", () => {
    const addEventListener = vi.spyOn(window, "addEventListener")
    render(<OfflineIndicator />)

    expect(addEventListener).toHaveBeenCalledWith("online", expect.any(Function))
    expect(addEventListener).toHaveBeenCalledWith("offline", expect.any(Function))
    addEventListener.mockRestore()
  })

  it("keeps browser event subscriptions mount-scoped", () => {
    const { rerender } = render(<OfflineIndicator />)
    rerender(<OfflineIndicator />)

    expect(reactEffects.dependencies).toContainEqual([])
  })
})
