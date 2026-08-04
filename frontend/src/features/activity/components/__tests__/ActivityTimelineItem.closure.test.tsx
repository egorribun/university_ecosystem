import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { TimelineEntry } from "../../types"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { course?: string }) =>
      key === "activity:timeline.attendanceEntry"
        ? `${key}:${options?.course ?? ""}`
        : key,
  }),
}))

import { ActivityTimelineItem } from "../ActivityTimelineItem"

const formatDate = (date: string) => `formatted:${date}`
const attendanceStatusLabel = (status: "present" | "absent" | "late") => `status:${status}`

function renderItem(entry: TimelineEntry) {
  return render(
    <ActivityTimelineItem
      entry={entry}
      formatDate={formatDate}
      attendanceStatusLabel={attendanceStatusLabel}
      staggerIndex={0}
    />
  )
}

describe("ActivityTimelineItem closure paths", () => {
  it("renders attendance with fallback course and an unknown status color", () => {
    renderItem({
      type: "attendance",
      date: "2026-06-01",
      status: "absent",
    })
    expect(screen.getByRole("article")).toBeInTheDocument()
    expect(screen.getByText(/activity:timeline\.attendanceEntry/)).toBeInTheDocument()
    expect(screen.getByText("formatted:2026-06-01")).toBeInTheDocument()
  })

  it("renders grade entries with and without a maximum", () => {
    const { rerender } = renderItem({
      type: "grade",
      date: "2026-06-02",
      course: "Math",
      score: 4,
      max: 5,
    })
    expect(screen.getByText("activity:timeline.gradeEntry")).toBeInTheDocument()

    rerender(
      <ActivityTimelineItem
        entry={{ type: "grade", date: "2026-06-03", course: "Physics", score: 3 }}
        formatDate={formatDate}
        attendanceStatusLabel={attendanceStatusLabel}
        staggerIndex={1}
      />
    )
    expect(screen.getByText("activity:timeline.gradeEntry")).toBeInTheDocument()
  })

  it("renders participation role and optional subtitle branches", () => {
    const { rerender } = renderItem({
      type: "participation",
      date: "2026-06-04",
      title: "Workshop",
      role: "mentor",
    })
    expect(screen.getByText("mentor")).toBeInTheDocument()

    rerender(
      <ActivityTimelineItem
        entry={{ type: "participation", date: "2026-06-05", title: "Open day" }}
        formatDate={formatDate}
        attendanceStatusLabel={attendanceStatusLabel}
        staggerIndex={2}
      />
    )
    expect(screen.queryByText("mentor")).not.toBeInTheDocument()
  })

  it("falls back for an unknown attendance status at runtime", () => {
    renderItem({
      type: "attendance",
      date: "2026-06-06",
      status: "unknown" as "present",
      course: "History",
    })
    expect(screen.getByRole("article")).toBeInTheDocument()
  })
})
