import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const translationMocks = vi.hoisted(() => ({
  useTranslation: vi.fn(() => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && "mins" in opts && "secs" in opts ? `${key}:${opts.mins}:${opts.secs}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: translationMocks.useTranslation,
}))

import {
  FlipCountdown,
  createFlipResetCleanup,
  getSecondsUntilTarget,
  invokeCountdownCompletion,
  isCountdownUrgent,
  padTwo,
  shouldCompleteCountdown,
  shouldFlipDigit,
  shouldRenderFlipFlaps,
  shouldTickCountdown,
} from "@/components/schedule/FlipCountdown"

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

  it("keeps pure countdown formatting and boundary contracts exact", () => {
    expect(padTwo(0)).toBe("00")
    expect(padTwo(9)).toBe("09")
    expect(padTwo(10)).toBe("10")
    expect(getSecondsUntilTarget(600, new Date(2026, 5, 16, 9, 59, 55))).toBe(5)
    expect(getSecondsUntilTarget(500, new Date(2026, 5, 16, 10, 0, 0))).toBe(0)
    expect(shouldFlipDigit("4", "5")).toBe(true)
    expect(shouldFlipDigit("5", "5")).toBe(false)
    expect(shouldTickCountdown("visible")).toBe(true)
    expect(shouldTickCountdown("hidden")).toBe(false)
    expect(shouldCompleteCountdown(0)).toBe(true)
    expect(shouldCompleteCountdown(1)).toBe(false)
    const completion = vi.fn()
    invokeCountdownCompletion(completion)
    invokeCountdownCompletion(undefined)
    expect(completion).toHaveBeenCalledTimes(1)
    expect(shouldRenderFlipFlaps(true)).toBe(true)
    expect(shouldRenderFlipFlaps(false)).toBe(false)
    expect(isCountdownUrgent(0)).toBe(false)
    expect(isCountdownUrgent(1)).toBe(true)
    expect(isCountdownUrgent(300)).toBe(true)
    expect(isCountdownUrgent(301)).toBe(false)
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
    expect(translationMocks.useTranslation).toHaveBeenCalledWith(["schedule"])
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
    const { container } = render(<FlipCountdown targetMinutes={600} />)
    // starts at 5s → units digit "5"
    expect(screen.getByLabelText("5 schedule:countdown.unitSeconds")).toBeInTheDocument()
    expect(container.querySelector(".sched-flip-digit")).toBeInTheDocument()
    expect(container.querySelector(".sched-flip-top-flap")).not.toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    // now 4s → units digit "4", flip flap shows previous "5"
    expect(screen.getByLabelText("4 schedule:countdown.unitSeconds")).toBeInTheDocument()
    expect(container.querySelector(".sched-flip-active")).toBeInTheDocument()
    expect(container.querySelector(".sched-flip-top-flap span")).toHaveTextContent("5")
    expect(container.querySelector(".sched-flip-bottom-flap span")).toHaveTextContent("4")
    act(() => {
      vi.advanceTimersByTime(499)
    })
    expect(container.querySelector(".sched-flip-active")).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(container.querySelector(".sched-flip-active")).not.toBeInTheDocument()
  })

  it("cancels a stale digit animation timer when the digit changes again", () => {
    const reset = vi.fn()
    const cancel = createFlipResetCleanup(reset, 500)
    cancel()
    act(() => vi.advanceTimersByTime(500))
    expect(reset).not.toHaveBeenCalled()

    createFlipResetCleanup(reset, 500)
    act(() => vi.advanceTimersByTime(499))
    expect(reset).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(reset).toHaveBeenCalledTimes(1)
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

  it("restarts its interval when the target lesson changes", () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval")
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval")
    const { rerender } = render(<FlipCountdown targetMinutes={600} />)
    const initialSetCalls = setIntervalSpy.mock.calls.length
    rerender(<FlipCountdown targetMinutes={700} />)
    expect(setIntervalSpy.mock.calls.length).toBe(initialSetCalls + 1)
    expect(clearIntervalSpy).toHaveBeenCalledTimes(1)
    setIntervalSpy.mockRestore()
    clearIntervalSpy.mockRestore()
  })

  it("uses the latest completion callback and tolerates an omitted callback", () => {
    const first = vi.fn()
    const latest = vi.fn()
    vi.setSystemTime(new Date(2026, 5, 16, 9, 59, 59))
    const { rerender } = render(<FlipCountdown targetMinutes={600} onComplete={first} />)
    rerender(<FlipCountdown targetMinutes={600} onComplete={latest} />)
    act(() => vi.advanceTimersByTime(1000))
    expect(first).not.toHaveBeenCalled()
    expect(latest).toHaveBeenCalledTimes(1)

    expect(() => {
      vi.setSystemTime(new Date(2026, 5, 16, 9, 59, 59))
      render(<FlipCountdown targetMinutes={600} />)
      act(() => vi.advanceTimersByTime(1000))
    }).not.toThrow()
  })

  it("clears its interval when unmounted", () => {
    const onComplete = vi.fn()
    vi.setSystemTime(new Date(2026, 5, 16, 9, 59, 59))
    const { unmount } = render(<FlipCountdown targetMinutes={600} onComplete={onComplete} />)
    unmount()
    act(() => vi.advanceTimersByTime(2000))
    expect(onComplete).not.toHaveBeenCalled()
  })

  it("applies a custom className to the timer container", () => {
    render(<FlipCountdown targetMinutes={600} className="my-custom-countdown" />)
    expect(screen.getByRole("timer")).toHaveClass("my-custom-countdown")
  })
})
