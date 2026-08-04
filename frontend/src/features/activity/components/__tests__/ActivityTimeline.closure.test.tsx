import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@/features/activity/components/ActivityTimelineItem", () => ({
  ActivityTimelineItem: ({ entry }: { entry: { type: string; date: string } }) => (
    <div data-testid="timeline-item">
      {entry.type}:{entry.date}
    </div>
  ),
}))

import { ActivityTimeline } from "../ActivityTimeline"

const formatDate = (date: string) => `formatted:${date}`
const attendanceStatusLabel = (status: "present" | "absent" | "late") => `status:${status}`

function isoDateOffset(offset: number): string {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
    .map((part, index) => (index === 0 ? String(part) : String(part).padStart(2, "0")))
    .join("-")
}

describe("ActivityTimeline closure paths", () => {
  it("does not render before the initial load and renders the empty state", () => {
    const { rerender } = render(
      <ActivityTimeline
        hasInitiallyLoaded={false}
        attendanceStatusLabel={attendanceStatusLabel}
        formatDate={formatDate}
      />
    )
    expect(screen.queryByRole("region")).not.toBeInTheDocument()

    rerender(
      <ActivityTimeline
        hasInitiallyLoaded
        attendance={null}
        grades={null}
        participation={null}
        attendanceStatusLabel={attendanceStatusLabel}
        formatDate={formatDate}
      />
    )
    expect(screen.getByText("activity:timeline.noActivity")).toBeInTheDocument()
  })

  it("merges, sorts, groups, keys, and expands mixed activity entries", () => {
    const today = isoDateOffset(0)
    const yesterday = isoDateOffset(-1)
    render(
      <ActivityTimeline
        hasInitiallyLoaded
        attendance={{
          percent: 90,
          present: 9,
          total: 10,
          trend: 1,
          periodLabel: "week",
          periodKey: "7d",
          recent: [
            { date: `${today}T09:00:00Z`, status: "present", course: "Math" },
            { date: `${yesterday}T09:00:00Z`, status: "late" },
          ],
        }}
        grades={{
          average: 4,
          scale: "5",
          trend: 0,
          recent: [
            { date: "2026-01-03", course: "Physics", score: 4 },
            { date: "invalid-grade", course: "History", score: 5, max: 5 },
          ],
        }}
        participation={{
          events: 2,
          trend: 0,
          recent: [
            { date: "2026-01-02", title: "Hackathon", role: "Mentor" },
            { date: "invalid-participation", title: "Open day" },
          ],
        }}
        attendanceStatusLabel={attendanceStatusLabel}
        formatDate={formatDate}
      />
    )

    expect(screen.getByRole("region", { name: "activity:a11y.timeline" })).toBeInTheDocument()
    expect(screen.getAllByTestId("timeline-item")).toHaveLength(6)
    expect(screen.getByText("activity:timeline.today")).toBeInTheDocument()
    expect(screen.getByText("activity:timeline.yesterday")).toBeInTheDocument()
    expect(screen.getByText("formatted:2026-01-03")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "activity:timeline.showMore" })
    ).not.toBeInTheDocument()
  })

  it("reveals the next page when more than ten entries are available", () => {
    const recent = Array.from({ length: 11 }, (_, index) => ({
      date: `2026-02-${String(index + 1).padStart(2, "0")}`,
      status: "present" as const,
      course: `Course ${index}`,
    }))
    render(
      <ActivityTimeline
        hasInitiallyLoaded
        attendance={{
          percent: 100,
          present: 11,
          total: 11,
          trend: 0,
          periodLabel: "month",
          periodKey: "30d",
          recent,
        }}
        attendanceStatusLabel={attendanceStatusLabel}
        formatDate={formatDate}
      />
    )

    const showMore = screen.getByRole("button", { name: "activity:timeline.showMore" })
    expect(screen.getAllByTestId("timeline-item")).toHaveLength(10)
    fireEvent.click(showMore)
    expect(screen.getAllByTestId("timeline-item")).toHaveLength(11)
    expect(
      screen.queryByRole("button", { name: "activity:timeline.showMore" })
    ).not.toBeInTheDocument()
  })
})
