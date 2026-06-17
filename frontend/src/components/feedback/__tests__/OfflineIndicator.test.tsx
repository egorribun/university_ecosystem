import { render, screen, act } from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
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

describe("OfflineIndicator", () => {
  it("renders nothing while online", () => {
    setOnline(true)
    render(<OfflineIndicator />)
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("shows the offline toast when navigator starts offline", () => {
    setOnline(false)
    render(<OfflineIndicator />)
    expect(screen.getByRole("status")).toBeInTheDocument()
    expect(screen.getByText("offlineIndicator.offline")).toBeInTheDocument()
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
    expect(screen.getByText("offlineIndicator.offline")).toBeInTheDocument()

    setOnline(true)
    act(() => {
      window.dispatchEvent(new Event("online"))
    })
    expect(screen.getByText("offlineIndicator.online")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(TIMEOUTS.OFFLINE_INDICATOR + 100)
    })
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
