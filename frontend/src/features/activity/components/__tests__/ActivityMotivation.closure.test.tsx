import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { AttendanceStats, GradeStats, ParticipationStats } from "@/features/activity/types"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count == null ? key : `${key}:${options.count}`,
  }),
}))

import { ActivityMotivation } from "@/features/activity/components/ActivityMotivation"

const attendance = (percent: number, recent: AttendanceStats["recent"] = []): AttendanceStats => ({
  percent,
  present: recent.filter((entry) => entry.status === "present").length,
  total: recent.length,
  trend: 0,
  periodLabel: "30 days",
  periodKey: "30d",
  recent,
})

const grades = (trend: number): GradeStats => ({
  average: 4,
  scale: "5",
  trend,
  recent: [],
})

const participation = (events: number): ParticipationStats => ({
  events,
  trend: 0,
  recent: [],
})

describe("ActivityMotivation closure", () => {
  it("renders nothing before the first successful load", () => {
    const { container } = render(<ActivityMotivation hasInitiallyLoaded={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("prioritizes excellent attendance and counts the leading streak", () => {
    render(
      <ActivityMotivation
        hasInitiallyLoaded
        attendance={attendance(95, [
          { date: "1", status: "present" },
          { date: "2", status: "present" },
          { date: "3", status: "present" },
          { date: "4", status: "absent" },
        ])}
        grades={grades(10)}
        participation={participation(10)}
      />
    )
    expect(screen.getByText("activity:motivation.excellent")).toBeInTheDocument()
    expect(screen.getByText("activity:motivation.streakDays:3")).toBeInTheDocument()
  })

  it.each([
    [
      "good attendance",
      <ActivityMotivation key="good" hasInitiallyLoaded attendance={attendance(80)} />,
    ],
    [
      "improving grades",
      <ActivityMotivation
        key="improving"
        hasInitiallyLoaded
        attendance={attendance(10)}
        grades={grades(1)}
      />,
    ],
    [
      "active participation",
      <ActivityMotivation
        key="active"
        hasInitiallyLoaded
        attendance={attendance(10)}
        participation={participation(5)}
      />,
    ],
    ["default motivation", <ActivityMotivation key="default" hasInitiallyLoaded />],
  ])("renders the %s message", (_label, element) => {
    render(element)
    const expected = {
      "good attendance": "activity:motivation.good",
      "improving grades": "activity:motivation.improving",
      "active participation": "activity:motivation.active",
      "default motivation": "activity:motivation.default",
    }[_label as string]
    expect(screen.getByText(expected)).toBeInTheDocument()
  })
})
