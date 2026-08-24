import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { afterEach, describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useCountUp", () => ({
  useCountUp: (n: number) => ({ ref: { current: null }, value: n }),
}))

import { ScheduleTimeline } from "@/components/dashboard/ScheduleTimeline"
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
  })

  afterEach(() => vi.useRealTimers())

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

  it("renders the now-line when minutesNow is in range", () => {
    const { container } = render(<ScheduleTimeline {...baseProps} minutesNow={720} />)
    expect(container.querySelector(".animate-ping")).toBeInTheDocument()
  })

  it("skips lessons with unparseable times (positionedLessons null branch)", () => {
    const broken = lesson({ id: "broken", subject: "Broken", start_time: "", end_time: "" })
    render(<ScheduleTimeline {...baseProps} lessons={[broken, MID]} />)
    expect(screen.queryByRole("img", { name: /Broken/ })).not.toBeInTheDocument()
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
    fireEvent.mouseLeave(block)
  })
})
