import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"
import { afterEach, describe, it, expect, vi, beforeEach } from "vitest"

const effectDependencyCalls = vi.hoisted(() => [] as unknown[][])

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>()
  return {
    ...actual,
    useEffect: (...args: Parameters<typeof actual.useEffect>) => {
      effectDependencyCalls.push((args[1] ?? []) as unknown[])
      return actual.useEffect(...args)
    },
  }
})

const translationCalls = vi.hoisted(() => ({
  entries: [] as Array<{ key: string; options?: Record<string, unknown> }>,
  namespaces: [] as unknown[][],
}))

vi.mock("react-i18next", () => ({
  useTranslation: (...namespaces: unknown[]) => {
    translationCalls.namespaces.push(namespaces)
    return {
      t: (key: string, options?: Record<string, unknown>) => {
        translationCalls.entries.push({ key, options })
        return key
      },
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))
vi.mock("@/hooks/useCountUp", () => ({
  useCountUp: (n: number) => ({ ref: { current: null }, value: n }),
}))

import {
  getInitialEffectDeps,
  normalizeLessonRange,
  ScheduleTimeline,
} from "@/components/dashboard/ScheduleTimeline"
import type { DashboardLesson } from "@/hooks/useDashboardSchedule"

function lesson(over: Partial<DashboardLesson>): DashboardLesson {
  return {
    id: "x",
    subject: "Subject",
    teacher: "Teacher",
    room: "Room",
    lesson_type: "lecture",
    weekday: "monday",
    start_time: "09:00",
    end_time: "10:30",
    parity: "both",
    ...over,
  }
}

// Lessons that land at the left edge (<15%), middle, and right edge (>80%) of
// the 8:00–20:00 axis — exercises every tooltip-alignment branch.
const LEFT = lesson({
  id: "left",
  subject: "Early Lecture",
  start_time: "08:00",
  end_time: "08:45",
})
const MID = lesson({ id: "mid", subject: "Midday Seminar", start_time: "13:00", end_time: "14:30" })
const RIGHT = lesson({
  id: "right",
  subject: "Evening Lab",
  start_time: "19:00",
  end_time: "19:45",
  teacher: "",
  room: "",
})

const baseProps = {
  lessons: [LEFT, MID, RIGHT],
  minutesNow: 600,
  currentLesson: null,
  nextLesson: null,
}

describe("ScheduleTimeline — branches", () => {
  beforeEach(() => {
    vi.useRealTimers()
    translationCalls.entries = []
    translationCalls.namespaces = []
    effectDependencyCalls.length = 0
  })

  afterEach(() => vi.useRealTimers())

  it("keeps the mount-only effect dependency and parsed range contracts explicit", () => {
    const [mountOnlyToken] = getInitialEffectDeps()
    expect(getInitialEffectDeps()).toHaveLength(1)
    expect(typeof mountOnlyToken).toBe("symbol")
    expect(normalizeLessonRange(540, 630)).toEqual([540, 630])
    expect(normalizeLessonRange(null, 630)).toBeNull()
    expect(normalizeLessonRange(540, null)).toBeNull()

    render(<ScheduleTimeline {...baseProps} />)
    expect(effectDependencyCalls).toContainEqual([mountOnlyToken])
  })

  it("auto-scrolls to the now-indicator on mount when now is in range", async () => {
    // jsdom doesn't implement Element.scrollTo — install a stub then spy on it.
    const proto = HTMLElement.prototype as unknown as { scrollTo?: (..._a: unknown[]) => void }
    const had = Object.prototype.hasOwnProperty.call(proto, "scrollTo")
    const original = proto.scrollTo
    // Plain vi.fn assigned directly — vi.spyOn() on an OPTIONAL property
    // resolves to `never` under strict typing; scrollTo must stay optional
    // because the restore below uses `delete proto.scrollTo`.
    const scrollSpy = vi.fn((..._a: unknown[]) => {})
    proto.scrollTo = scrollSpy
    render(<ScheduleTimeline {...baseProps} />)
    await waitFor(() => expect(scrollSpy).toHaveBeenCalled(), { timeout: 500 })
    expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "smooth" }))
    if (had) {
      proto.scrollTo = original
    } else {
      delete proto.scrollTo
    }
  })

  it("clears the deferred auto-scroll when the timeline unmounts", () => {
    vi.useFakeTimers()
    const scrollSpy = vi.fn()
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")
    const descriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTo")
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollSpy,
    })

    try {
      const { unmount } = render(<ScheduleTimeline {...baseProps} />)
      const clearCallsBeforeUnmount = clearTimeoutSpy.mock.calls.length
      unmount()
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(scrollSpy).not.toHaveBeenCalled()
      expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThan(clearCallsBeforeUnmount)
    } finally {
      clearTimeoutSpy.mockRestore()
      if (descriptor) {
        Object.defineProperty(HTMLElement.prototype, "scrollTo", descriptor)
      } else {
        delete (HTMLElement.prototype as unknown as { scrollTo?: unknown }).scrollTo
      }
    }
  })

  it("does NOT render the now-line when minutesNow is out of range", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} minutesNow={300} />)
    // animate-ping is unique to the now-indicator pulse ring.
    expect(container.querySelector(".animate-ping")).not.toBeInTheDocument()
  })

  it("skips auto-scroll when the now indicator is outside the range", () => {
    vi.useFakeTimers()
    const scrollSpy = vi.fn()
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollSpy,
    })
    render(<ScheduleTimeline {...baseProps} minutesNow={300} />)

    vi.advanceTimersByTime(100)

    expect(scrollSpy).not.toHaveBeenCalled()
  })

  it("runs the deferred auto-scroll only on the initial mount", () => {
    vi.useFakeTimers()
    const scrollSpy = vi.fn()
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")
    const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTo")
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollSpy,
    })

    try {
      const { rerender } = render(<ScheduleTimeline {...baseProps} />)
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(scrollSpy).toHaveBeenCalledOnce()

      const clearCallsAfterInitialTimer = clearTimeoutSpy.mock.calls.length
      act(() => {
        rerender(<ScheduleTimeline {...baseProps} minutesNow={baseProps.minutesNow + 1} />)
      })
      // The mount-only effect must not tear down/re-register its timer when
      // the timeline receives a new time value.  A mutated dependency array
      // allocates a fresh array on every render and would add a clear call.
      expect(clearTimeoutSpy.mock.calls.length).toBe(clearCallsAfterInitialTimer)
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(scrollSpy).toHaveBeenCalledOnce()
    } finally {
      if (originalScrollTo) {
        Object.defineProperty(HTMLElement.prototype, "scrollTo", originalScrollTo)
      } else {
        delete (HTMLElement.prototype as unknown as { scrollTo?: unknown }).scrollTo
      }
    }
  })

  it("renders the now-line when minutesNow is in range", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} minutesNow={720} />)
    expect(container.querySelector(".animate-ping")).toBeInTheDocument()
  })

  it("skips lessons with unparseable times (positionedLessons null branch)", () => {
    const broken = lesson({ id: "broken", subject: "Broken", start_time: "", end_time: "" })
    render(<ScheduleTimeline {...baseProps} lessons={[broken, MID]} />)
    expect(screen.queryByRole("img", { name: /Broken/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole("img")).toHaveLength(1)
    expect(screen.getByRole("img", { name: /Midday Seminar/ })).toBeInTheDocument()
  })

  it("skips a lesson when either endpoint is unparseable", () => {
    const invalidStart = lesson({
      id: "invalid-start",
      subject: "Invalid start",
      start_time: "bad",
      end_time: "10:00",
    })
    const invalidEnd = lesson({
      id: "invalid-end",
      subject: "Invalid end",
      start_time: "10:00",
      end_time: "bad",
    })

    render(<ScheduleTimeline {...baseProps} lessons={[invalidStart, invalidEnd, MID]} />)

    expect(screen.queryByRole("img", { name: /Invalid start/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("img", { name: /Invalid end/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole("img")).toHaveLength(1)
    expect(screen.getByRole("img", { name: /Midday Seminar/ })).toBeInTheDocument()
  })

  it("filters out lessons entirely outside the 8:00–20:00 window", () => {
    // Lesson before range entirely (ends at 7:00) should be filtered.
    const before = lesson({
      id: "before",
      subject: "Dawn Class",
      start_time: "06:00",
      end_time: "07:00",
    })
    render(<ScheduleTimeline {...baseProps} lessons={[before, MID]} />)
    expect(screen.queryByRole("img", { name: /Dawn Class/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole("img")).toHaveLength(1)
    expect(screen.getByRole("img", { name: /Midday Seminar/ })).toBeInTheDocument()
  })

  it("skips zero-length and reversed lesson ranges", () => {
    const zeroLength = lesson({
      id: "zero-length",
      subject: "Zero length",
      start_time: "10:00",
      end_time: "10:00",
    })
    const reversed = lesson({
      id: "reversed",
      subject: "Reversed range",
      start_time: "11:00",
      end_time: "10:30",
    })

    render(<ScheduleTimeline {...baseProps} lessons={[zeroLength, reversed, MID]} />)

    expect(screen.queryByRole("img", { name: /Zero length/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("img", { name: /Reversed range/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole("img")).toHaveLength(1)
    expect(screen.getByRole("img", { name: /Midday Seminar/ })).toBeInTheDocument()
  })

  it("flags the current lesson and shows the pulse dot", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} currentLesson={MID} />)
    // The current-lesson block contains an extra animate-pulse dot.
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument()
  })

  it("flags the next lesson with the next-lesson styling", () => {
    render(<ScheduleTimeline {...baseProps} nextLesson={MID} />)
    // Render still succeeds and the lesson block is present.
    expect(screen.getByRole("img", { name: /Midday Seminar/ })).toBeInTheDocument()
  })

  it("shows the hover tooltip with teacher and room for a middle lesson", () => {
    render(<ScheduleTimeline {...baseProps} />)
    const block = screen.getByRole("img", { name: /Midday Seminar/ })
    fireEvent.mouseEnter(block)
    // Tooltip duplicates the subject (block label + tooltip heading).
    expect(screen.getAllByText("Midday Seminar").length).toBeGreaterThan(1)
    expect(screen.getByText("Teacher")).toBeInTheDocument()
    expect(screen.getByText("Room")).toBeInTheDocument()
    fireEvent.mouseLeave(block)
    expect(screen.queryByText("Teacher")).not.toBeInTheDocument()
  })

  it("shows a left-aligned tooltip for an early (<15%) lesson", () => {
    render(<ScheduleTimeline {...baseProps} />)
    const block = screen.getByRole("img", { name: /Early Lecture/ })
    fireEvent.focus(block)
    expect(screen.getAllByText("Early Lecture").length).toBeGreaterThan(1)
    fireEvent.blur(block)
  })

  it("shows a right-aligned tooltip for a late (>80%) lesson with no teacher/room", () => {
    render(<ScheduleTimeline {...baseProps} />)
    const block = screen.getByRole("img", { name: /Evening Lab/ })
    fireEvent.mouseEnter(block)
    // The tooltip heading appears, but teacher/room paragraphs are omitted
    // because both are empty strings (conditional-render false branch).
    expect(screen.getAllByText("Evening Lab").length).toBeGreaterThan(1)
    expect(screen.queryByText("Teacher")).not.toBeInTheDocument()
    expect(screen.queryByText("Room")).not.toBeInTheDocument()
    const tooltip = screen.getAllByText("Evening Lab")[1]?.parentElement
    expect(tooltip?.querySelectorAll("p")).toHaveLength(2)
    fireEvent.mouseLeave(block)
  })

  it("preserves proportional geometry when lessons cross the timeline bounds", () => {
    render(
      <ScheduleTimeline
        {...baseProps}
        lessons={[
          lesson({
            id: "cross-left",
            subject: "Crosses left",
            start_time: "07:00",
            end_time: "09:00",
          }),
          lesson({
            id: "cross-right",
            subject: "Crosses right",
            start_time: "19:00",
            end_time: "21:00",
          }),
          lesson({ id: "full-span", subject: "Full span", start_time: "07:00", end_time: "21:00" }),
        ]}
      />
    )

    const left = screen.getByRole("img", { name: /Crosses left/ })
    const right = screen.getByRole("img", { name: /Crosses right/ })
    const full = screen.getByRole("img", { name: /Full span/ })

    expect(left).toHaveStyle({ left: "0%", width: "8.333333333333332%" })
    expect(right).toHaveStyle({ left: "91.66666666666666%", width: "8.333333333333343%" })
    expect(full).toHaveStyle({ left: "0%", width: "100%" })
  })

  it("keeps lesson geometry and structural styles stable", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} />)
    const block = screen.getByRole("img", { name: /Midday Seminar/ })
    expect(block).toHaveClass(
      "absolute",
      "cursor-pointer",
      "rounded-lg",
      "border",
      "transition-all",
      "hover:z-10",
      "hover:shadow-premium",
      "hover:-translate-y-0.5"
    )
    expect(block).toHaveAttribute("tabindex", "0")
    expect(block).toHaveAttribute("role", "img")
    expect(block).toHaveStyle({
      left: "41.66666666666667%",
      width: "12.499999999999993%",
      top: "14px",
      height: "44px",
      minWidth: "40px",
    })
    expect(block.getAttribute("style")).toContain("left: 41.66666666666667%")
    expect(block.getAttribute("style")).toContain("width: 12.499999999999993%")

    const inner = Array.from(container.querySelectorAll("div")).find((element) =>
      element.getAttribute("style")?.includes("height: 5.5rem")
    )
    expect(inner).toHaveClass("relative")
    expect(inner).toHaveStyle({ height: "88px", minWidth: "100%" })

    const track = Array.from(container.querySelectorAll("div")).find((element) =>
      element.getAttribute("style")?.includes("height: 3rem")
    )
    expect(track).toHaveClass(
      "absolute",
      "left-0",
      "right-0",
      "rounded-xl",
      "bg-(--bg-matte-list)",
      "border",
      "border-(--border-matte)"
    )
    expect(track).toHaveStyle({ top: "12px", height: "48px" })

    const markerTicks = container.querySelectorAll(".h-2.w-px")
    expect(markerTicks).toHaveLength(7)
    markerTicks.forEach((tick) => expect(tick).toHaveStyle({ marginTop: "12px" }))

    const markerLabels = container.querySelectorAll(".font-mono")
    expect(markerLabels).toHaveLength(7)
    ;["8:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"].forEach((label) => {
      expect(screen.getByText(label)).toBeInTheDocument()
    })
    markerLabels.forEach((label) =>
      expect(label).toHaveStyle({
        transform: "translateX(-50%)",
        position: "absolute",
        top: "60px",
      })
    )
  })

  it("excludes lessons exactly at the 08:00 and 20:00 boundaries", () => {
    render(
      <ScheduleTimeline
        {...baseProps}
        lessons={[
          lesson({
            id: "ends-at-start",
            subject: "Ends at eight",
            start_time: "07:00",
            end_time: "08:00",
          }),
          lesson({
            id: "starts-at-end",
            subject: "Starts at eight",
            start_time: "20:00",
            end_time: "21:00",
          }),
          MID,
        ]}
      />
    )

    expect(screen.queryByRole("img", { name: /Ends at eight/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("img", { name: /Starts at eight/ })).not.toBeInTheDocument()
    expect(screen.getByRole("img", { name: /Midday Seminar/ })).toBeInTheDocument()
  })

  it("renders exact now-line boundary semantics", () => {
    const atStart = render(<ScheduleTimeline {...baseProps} minutesNow={480} />)
    expect(atStart.container.querySelector(".animate-ping")).toBeInTheDocument()
    atStart.unmount()

    const atEnd = render(<ScheduleTimeline {...baseProps} minutesNow={1200} />)
    expect(atEnd.container.querySelector(".animate-ping")).toBeInTheDocument()
    atEnd.unmount()

    const beforeStart = render(<ScheduleTimeline {...baseProps} minutesNow={479} />)
    expect(beforeStart.container.querySelector(".animate-ping")).not.toBeInTheDocument()
    beforeStart.unmount()

    const afterEnd = render(<ScheduleTimeline {...baseProps} minutesNow={1201} />)
    expect(afterEnd.container.querySelector(".animate-ping")).not.toBeInTheDocument()
  })

  it("clamps and exposes the proportional now-line position", () => {
    const middle = render(<ScheduleTimeline {...baseProps} minutesNow={840} />)
    const middleIndicator = middle.container.querySelector(".animate-ping")?.parentElement
    expect(middleIndicator).toHaveStyle({
      left: "50%",
      top: "6px",
      transform: "translateX(-50%)",
    })
    middle.unmount()

    const end = render(<ScheduleTimeline {...baseProps} minutesNow={1200} />)
    const endIndicator = end.container.querySelector(".animate-ping")?.parentElement
    expect(endIndicator).toHaveStyle({ left: "100%" })
    end.unmount()
  })

  it("uses the proportional hour-marker positions", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} />)
    const labels = ["8:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"]
    const expectedLeft = [
      "0%",
      "16.666666666666664%",
      "33.33333333333333%",
      "50%",
      "66.66666666666666%",
      "83.33333333333334%",
      "100%",
    ]

    expect(container.querySelectorAll(".font-mono")).toHaveLength(labels.length)
    labels.forEach((label, index) => {
      const text = screen.getByText(label)
      expect(text.parentElement).toHaveStyle({ left: expectedLeft[index] })
    })
  })

  it("computes the exact auto-scroll anchor instead of only smooth behavior", () => {
    vi.useFakeTimers()
    const scrollSpy = vi.fn()
    const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTo")
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollSpy,
    })

    try {
      const { container } = render(<ScheduleTimeline {...baseProps} />)
      const scrollContainer = container.querySelector(".overflow-x-auto") as HTMLElement
      const nowIndicator = container.querySelector(".animate-ping")?.parentElement as HTMLElement
      Object.defineProperty(scrollContainer, "clientWidth", { configurable: true, value: 900 })
      Object.defineProperty(nowIndicator, "offsetLeft", { configurable: true, value: 600 })

      act(() => {
        vi.advanceTimersByTime(100)
      })

      expect(scrollSpy).toHaveBeenCalledWith({ left: 300, behavior: "smooth" })
    } finally {
      if (originalScrollTo) {
        Object.defineProperty(HTMLElement.prototype, "scrollTo", originalScrollTo)
      } else {
        delete (HTMLElement.prototype as unknown as { scrollTo?: unknown }).scrollTo
      }
    }
  })

  it("exposes distinct current and next lesson states", () => {
    const { rerender } = render(<ScheduleTimeline {...baseProps} />)

    rerender(<ScheduleTimeline {...baseProps} currentLesson={MID} nextLesson={RIGHT} />)

    const current = screen.getByRole("img", { name: /Midday Seminar/ })
    expect(current).toHaveClass("border-brand", "bg-brand/(--opacity-subtle)", "shadow-sm", "z-[2]")
    expect(current.querySelector(".animate-pulse")).toBeInTheDocument()

    const next = screen.getByRole("img", { name: /Evening Lab/ })
    expect(next).toHaveClass("border-brand/(--opacity-soft)", "bg-brand/(--opacity-faint)", "z-[1]")
    expect(next.querySelector(".animate-pulse")).not.toBeInTheDocument()

    const regular = screen.getByRole("img", { name: /Early Lecture/ })
    expect(regular).toHaveClass("border-(--border-matte)", "bg-(--bg-matte-list)")
    expect(regular).not.toHaveClass("z-[1]", "z-[2]")
  })

  it("renders the current-time indicator geometry and pulse layers", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} minutesNow={720} />)
    const indicator = container.querySelector(".animate-ping")?.parentElement
    expect(indicator).toHaveClass("absolute", "z-[5]", "flex", "flex-col", "items-center")
    expect(indicator).toHaveStyle({ left: "33.33333333333333%", top: "6px" })

    const line = indicator?.querySelector(".w-0\\.5")
    expect(line).toHaveClass("w-0.5", "bg-brand", "opacity-heavy")
    expect(line).toHaveStyle({ height: "48px" })
    expect(indicator?.querySelectorAll(".rounded-full")).toHaveLength(2)
  })

  it("aligns the tooltip at the left, center, and right edges", () => {
    render(<ScheduleTimeline {...baseProps} />)

    const leftBlock = screen.getByRole("img", { name: /Early Lecture/ })
    fireEvent.mouseEnter(leftBlock)
    const leftTooltip = screen.getAllByText("Early Lecture")[1]?.parentElement
    expect(leftTooltip).toHaveClass(
      "absolute",
      "z-20",
      "rounded-xl",
      "px-3",
      "py-2",
      "glass-layer-floating",
      "glass-noise",
      "pointer-events-none",
      "shadow-premium",
      "min-w-40"
    )
    expect(leftTooltip).toHaveStyle({
      bottom: "calc(100% + 0.5rem)",
      left: "0px",
      right: "auto",
      transform: "none",
    })
    expect(leftTooltip?.getAttribute("style")).toContain("left: 0px")
    expect(leftTooltip?.getAttribute("style")).toContain("right: auto")
    expect(leftTooltip?.getAttribute("style")).toContain("transform: none")
    const leftArrow = leftTooltip?.querySelector(".rotate-45")
    expect(leftArrow).toHaveStyle({
      bottom: "-4px",
      left: "16px",
      right: "auto",
      transform: "none",
    })
    expect(leftArrow?.getAttribute("style")).toContain("left: 1rem")
    expect(leftArrow?.getAttribute("style")).toContain("right: auto")
    expect(leftArrow?.getAttribute("style")).toContain("transform: none")
    expect(leftArrow?.getAttribute("style")).toContain(
      "border-right: 1px solid var(--glass-border)"
    )
    expect(leftArrow?.getAttribute("style")).toContain(
      "border-bottom: 1px solid var(--glass-border)"
    )
    fireEvent.mouseLeave(leftBlock)

    const midBlock = screen.getByRole("img", { name: /Midday Seminar/ })
    fireEvent.mouseEnter(midBlock)
    const midTooltip = screen.getAllByText("Midday Seminar")[1]?.parentElement
    expect(midTooltip).toHaveStyle({ left: "50%", right: "auto", transform: "translateX(-50%)" })
    expect(midTooltip).toHaveStyle({ bottom: "calc(100% + 0.5rem)" })
    expect(midTooltip?.getAttribute("style")).toContain("left: 50%")
    expect(midTooltip?.getAttribute("style")).toContain("right: auto")
    expect(midTooltip?.getAttribute("style")).toContain("transform: translateX(-50%)")
    const midArrow = midTooltip?.querySelector(".rotate-45")
    expect(midArrow).toHaveStyle({
      bottom: "-4px",
      left: "50%",
      right: "auto",
      transform: "translateX(-50%)",
    })
    expect(midArrow?.getAttribute("style")).toContain("left: 50%")
    expect(midArrow?.getAttribute("style")).toContain("right: auto")
    expect(midArrow?.getAttribute("style")).toContain("transform: translateX(-50%)")
    expect(midArrow?.getAttribute("style")).toContain("border-right: 1px solid var(--glass-border)")
    expect(midArrow?.getAttribute("style")).toContain(
      "border-bottom: 1px solid var(--glass-border)"
    )
    fireEvent.mouseLeave(midBlock)

    const rightBlock = screen.getByRole("img", { name: /Evening Lab/ })
    fireEvent.mouseEnter(rightBlock)
    const rightTooltip = screen.getAllByText("Evening Lab")[1]?.parentElement
    expect(rightTooltip).toHaveStyle({
      bottom: "calc(100% + 0.5rem)",
      left: "auto",
      right: "0px",
      transform: "none",
    })
    expect(rightTooltip?.getAttribute("style")).toContain("left: auto")
    expect(rightTooltip?.getAttribute("style")).toContain("right: 0px")
    expect(rightTooltip?.getAttribute("style")).toContain("transform: none")
    const rightArrow = rightTooltip?.querySelector(".rotate-45")
    expect(rightArrow).toHaveStyle({
      bottom: "-4px",
      left: "auto",
      right: "16px",
      transform: "none",
    })
    expect(rightArrow?.getAttribute("style")).toContain("left: auto")
    expect(rightArrow?.getAttribute("style")).toContain("right: 1rem")
    expect(rightArrow?.getAttribute("style")).toContain("transform: none")
    expect(rightArrow?.getAttribute("style")).toContain(
      "border-right: 1px solid var(--glass-border)"
    )
    expect(rightArrow?.getAttribute("style")).toContain(
      "border-bottom: 1px solid var(--glass-border)"
    )
  })

  it("keeps strict tooltip threshold semantics at 15% and 80%", () => {
    const leftBoundary = lesson({
      id: "left-boundary",
      subject: "Left boundary",
      start_time: "09:48", // exactly 15% of the 08:00–20:00 range
      end_time: "10:30",
    })
    const rightBoundary = lesson({
      id: "right-boundary",
      subject: "Right boundary",
      start_time: "17:36", // exactly 80% of the 08:00–20:00 range
      end_time: "18:00",
    })

    render(<ScheduleTimeline {...baseProps} lessons={[leftBoundary, rightBoundary]} />)

    fireEvent.focus(screen.getByRole("img", { name: /Left boundary/ }))
    const leftTooltip = screen.getAllByText("Left boundary")[1]?.parentElement
    expect(leftTooltip).toHaveStyle({ left: "50%", right: "auto", transform: "translateX(-50%)" })
    const leftArrow = leftTooltip?.querySelector(".rotate-45")
    expect(leftArrow).toHaveStyle({
      left: "50%",
      right: "auto",
      bottom: "-4px",
      transform: "translateX(-50%)",
    })
    fireEvent.blur(screen.getByRole("img", { name: /Left boundary/ }))
    expect(screen.getAllByText("Left boundary")).toHaveLength(1)

    fireEvent.focus(screen.getByRole("img", { name: /Right boundary/ }))
    const rightTooltip = screen.getAllByText("Right boundary")[1]?.parentElement
    expect(rightTooltip).toHaveStyle({ left: "50%", right: "auto", transform: "translateX(-50%)" })
    const rightArrow = rightTooltip?.querySelector(".rotate-45")
    expect(rightArrow).toHaveStyle({ left: "50%", right: "auto", transform: "translateX(-50%)" })
  })

  it("passes the lesson count to i18n and hides the count for an empty timeline", () => {
    render(<ScheduleTimeline {...baseProps} lessons={[MID]} />)
    const countCall = translationCalls.entries.find(
      (entry) => entry.key === "dashboard:timeline.lessonCount"
    )
    expect(countCall?.options).toEqual({ count: 1 })
    expect(translationCalls.entries.some((entry) => entry.key === "dashboard:now")).toBe(true)

    const { container } = render(<ScheduleTimeline {...baseProps} lessons={[]} />)
    expect(container.querySelector(".tabular-nums")).not.toBeInTheDocument()
  })

  it("loads the dashboard translation namespace for the legend", () => {
    render(<ScheduleTimeline {...baseProps} lessons={[]} />)
    expect(translationCalls.namespaces).toContainEqual([["dashboard"]])
  })
})
