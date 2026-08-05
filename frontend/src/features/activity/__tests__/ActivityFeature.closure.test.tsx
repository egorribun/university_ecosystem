import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { AttendanceStats, GradeStats, ParticipationStats } from "@/features/activity/types"

type ChildProps = { children?: ReactNode; ringSize?: number }

const state = vi.hoisted(() => ({
  viewport: "default" as "default" | "sm" | "md" | "lg" | "xl",
  reducedMotion: false,
  indicator: null as { left: number; top: number; width: number; height: number } | null,
  setPeriod: vi.fn(),
  comparativeHasData: true,
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("lucide-react", () => ({
  Activity: () => <span data-testid="timeline-icon" />,
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    if (query.includes("prefers-reduced-motion")) return state.reducedMotion
    if (query.includes("max-width: 640px")) return state.viewport === "sm"
    if (query.includes("max-width: 768px")) {
      return state.viewport === "sm" || state.viewport === "md"
    }
    if (query.includes("max-width: 1100px")) {
      return state.viewport === "sm" || state.viewport === "md"
    }
    if (query.includes("min-width: 1280px")) return state.viewport === "xl"
    if (query.includes("min-width: 1024px")) return state.viewport === "lg"
    return false
  },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

const activityData = vi.hoisted(() => ({
  t: (key: string) => key,
  period: "90d" as const,
  setPeriod: state.setPeriod,
  attendance: {
    percent: 92,
    present: 9,
    total: 10,
    trend: 1,
    periodLabel: "90 days",
    periodKey: "90d",
    recent: [{ date: "2026-08-01", status: "present" as const }],
  } satisfies AttendanceStats,
  grades: {
    average: 4.4,
    scale: "5" as const,
    trend: 0.3,
    recent: [{ course: "Math", score: 5, date: "2026-08-01" }],
  } satisfies GradeStats,
  participation: {
    events: 2,
    hours: 4,
    groups: 1,
    trend: 1,
    recent: [{ title: "Club", date: "2026-08-01" }],
  } satisfies ParticipationStats,
  hasInitiallyLoaded: true,
  periodOptions: [
    { value: "30d" as const, label: "30 days" },
    { value: "90d" as const, label: "90 days" },
  ],
  separator: "·",
  formatDate: (value?: string | null) => value ?? "",
  attendanceStatusLabel: (status: string) => status,
  attendanceTrendData: [{ date: "2026-08-01", value: 100 }],
  gradesBySubject: [{ label: "Math", value: 5, max: 5 }],
  heatmapData: new Map([["2026-08-01", 3]]),
}))

vi.mock("@/hooks/useActivityData", () => ({
  default: () => activityData,
}))

vi.mock("@/hooks/useActivityComparative", () => ({
  useActivityComparative: () => ({
    hasData: state.comparativeHasData,
    attendance: { current: 90, previous: 80, delta: 12.5 },
    grades: { current: 4.5, previous: 4, delta: 12.5 },
    participation: { current: 2, previous: 1, delta: 100 },
  }),
}))

vi.mock("@/hooks/ui/useSlidingIndicator", () => ({
  useSlidingIndicator: () => state.indicator,
}))

vi.mock("@/components/motion/FadeSection", () => ({
  default: ({ children, ...props }: ChildProps & Record<string, unknown>) => (
    <div {...props}>{children}</div>
  ),
}))

vi.mock("@/features/activity/components/ActivityBackdrop", () => ({
  ActivityBackdrop: () => <div data-testid="activity-backdrop" />,
}))
vi.mock("@/features/activity/components/ActivityMotivation", () => ({
  ActivityMotivation: () => <div data-testid="activity-motivation" />,
}))
vi.mock("@/features/activity/components/AttendanceCard", () => ({
  AttendanceCard: ({ ringSize }: ChildProps) => <div data-testid="attendance-card">{ringSize}</div>,
}))
vi.mock("@/features/activity/components/GradesCard", () => ({
  GradesCard: ({ ringSize }: ChildProps) => <div data-testid="grades-card">{ringSize}</div>,
}))
vi.mock("@/features/activity/components/ParticipationCard", () => ({
  ParticipationCard: ({ ringSize }: ChildProps) => (
    <div data-testid="participation-card">{ringSize}</div>
  ),
}))
vi.mock("@/features/activity/components/ActivityTrendChart", () => ({
  ActivityTrendChart: () => <div data-testid="activity-trend-chart" />,
}))
vi.mock("@/features/activity/components/ActivityBarChart", () => ({
  ActivityBarChart: () => <div data-testid="activity-bar-chart" />,
}))
vi.mock("@/features/activity/components/ActivityHeatmap", () => ({
  ActivityHeatmap: () => <div data-testid="activity-heatmap" />,
}))
vi.mock("@/features/activity/components/ActivityComparativeCard", () => ({
  ActivityComparativeCard: ({ label }: { label: string }) => (
    <div data-testid="activity-comparative-card">{label}</div>
  ),
}))
vi.mock("@/features/activity/components/ActivityExportButton", () => ({
  ActivityExportButton: () => <button type="button">export</button>,
}))
vi.mock("@/features/activity/components/ActivityTimeline", () => ({
  ActivityTimeline: () => <div data-testid="activity-timeline" />,
}))

import { ActivityFeature } from "@/features/activity/ActivityFeature"

beforeEach(() => {
  state.viewport = "default"
  state.reducedMotion = false
  state.indicator = null
  state.comparativeHasData = true
  state.setPeriod.mockReset()
})

describe("ActivityFeature closure", () => {
  it("renders loaded conditional sections and selects a period", () => {
    state.indicator = { left: 4, top: 2, width: 60, height: 40 }
    render(<ActivityFeature />)

    expect(screen.getAllByText("96")).toHaveLength(3)
    expect(screen.getByTestId("activity-trend-chart")).toBeInTheDocument()
    expect(screen.getByTestId("activity-bar-chart")).toBeInTheDocument()
    expect(screen.getByTestId("activity-heatmap")).toBeInTheDocument()
    expect(screen.getAllByTestId("activity-comparative-card")).toHaveLength(3)
    expect(screen.getByTestId("activity-timeline")).toBeInTheDocument()
    expect(screen.getByRole("radio", { name: "30 days" })).toHaveAttribute("aria-checked", "false")

    fireEvent.click(screen.getByRole("radio", { name: "30 days" }))
    expect(state.setPeriod).toHaveBeenCalledWith("30d")
  })

  it("covers every responsive ring size and the empty comparative branch", () => {
    const { rerender } = render(<ActivityFeature />)

    state.viewport = "sm"
    rerender(<ActivityFeature />)
    expect(screen.getAllByText("68")).toHaveLength(3)

    state.viewport = "md"
    rerender(<ActivityFeature />)
    expect(screen.getAllByText("84")).toHaveLength(3)

    state.viewport = "lg"
    rerender(<ActivityFeature />)
    expect(screen.getAllByText("72")).toHaveLength(3)

    state.viewport = "xl"
    rerender(<ActivityFeature />)
    expect(screen.getAllByText("104")).toHaveLength(3)

    state.comparativeHasData = false
    rerender(<ActivityFeature />)
    expect(screen.queryByTestId("activity-comparative-card")).not.toBeInTheDocument()
  })
})
