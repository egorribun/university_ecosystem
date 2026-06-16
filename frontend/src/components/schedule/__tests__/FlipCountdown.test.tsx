import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && "mins" in opts && "secs" in opts ? `${key}:${opts.mins}:${opts.secs}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { FlipCountdown } from "@/components/schedule/FlipCountdown"

describe("FlipCountdown", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Pin "now" to a deterministic wall-clock so secondsLeft is computable.
    // 09:59:55 → 35995s since midnight; target 600 min (10:00) = 36000s → 5s left.
    vi.setSystemTime(new Date(2026, 5, 16, 9, 59, 55))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("renders the timer region with MM:SS flip digits and aria-label", () => {
    render(<FlipCountdown targetMinutes={600} />)
    const timer = screen.getByRole("timer")
    expect(timer).toBeInTheDocument()
    expect(timer).toHaveAttribute("aria-live", "polite")
    // ariaLabel key receives interpolated mins/secs (5s left → 0 min 5 sec)
    expect(timer).toHaveAttribute("aria-label", "schedule:countdown.ariaLabel:0:5")
    // 4 flip digit groups (MM:SS) — each FlipDigit emits an aria-label "<value> <label>"
    expect(screen.getByLabelText("0 schedule:countdown.tensOfMinutes")).toBeInTheDocument()
    expect(screen.getByLabelText("0 schedule:countdown.unitMinutes")).toBeInTheDocument()
    // tens-of-seconds digit = "0", units-of-seconds digit = "5"
    expect(screen.getByLabelText("0 schedule:countdown.tensOfSeconds")).toBeInTheDocument()
    expect(screen.getByLabelText("5 schedule:countdown.unitSeconds")).toBeInTheDocument()
    expect(screen.getByText(":")).toBeInTheDocument()
  })

  it("marks the timer urgent within the last 5 minutes", () => {
    // 5s left ≤ 300 → urgent branch
    render(<FlipCountdown targetMinutes={600} />)
    expect(screen.getByRole("timer")).toHaveAttribute("data-urgent", "true")
  })

  it("is not urgent when more than 5 minutes remain", () => {
    // target 700 min (11:40) vs 09:59:55 → 6005s left (> 300) → no urgent flag
    render(<FlipCountdown targetMinutes={700} />)
    expect(screen.getByRole("timer")).not.toHaveAttribute("data-urgent")
  })

  it("ticks down each second and flips a digit on change", () => {
    render(<FlipCountdown targetMinutes={600} />)
    // starts at 5s → units digit "5"
    expect(screen.getByLabelText("5 schedule:countdown.unitSeconds")).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    // now 4s → units digit "4", flip flap shows previous "5"
    expect(screen.getByLabelText("4 schedule:countdown.unitSeconds")).toBeInTheDocument()
  })

  it("fires onComplete when the countdown reaches zero", () => {
    const onComplete = vi.fn()
    // 1s left so a single tick hits zero deterministically.
    vi.setSystemTime(new Date(2026, 5, 16, 9, 59, 59))
    render(<FlipCountdown targetMinutes={600} onComplete={onComplete} />)
    expect(onComplete).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("timer")).toHaveAttribute(
      "aria-label",
      "schedule:countdown.ariaLabel:0:0"
    )
    // 0s is no longer urgent (isUrgent requires secondsLeft > 0)
    expect(screen.getByRole("timer")).not.toHaveAttribute("data-urgent")
  })

  it("pauses ticking while the tab is hidden", () => {
    render(<FlipCountdown targetMinutes={600} />)
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" })
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    // Still 5s left — interval body early-returns when hidden
    expect(screen.getByLabelText("5 schedule:countdown.unitSeconds")).toBeInTheDocument()
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" })
  })

  it("applies a custom className to the timer container", () => {
    render(<FlipCountdown targetMinutes={600} className="my-custom-countdown" />)
    expect(screen.getByRole("timer")).toHaveClass("my-custom-countdown")
  })
})
