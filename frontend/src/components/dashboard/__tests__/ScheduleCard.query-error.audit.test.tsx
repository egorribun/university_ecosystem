import { render, screen } from "@testing-library/react"
import type { ElementType, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const query = vi.hoisted(() => ({
  current: {
    data: undefined as unknown[] | undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
  },
}))
const router = vi.hoisted(() => ({ current: { preloadRoute: vi.fn() } }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options?.returnObjects) {
        return ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
      }
      return key === "common:statuses.error" ? "Something went wrong" : key
    },
  }),
}))
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    ...props
  }: { children?: ReactNode; to?: unknown } & Record<string, unknown>) => (
    <a href={typeof to === "string" ? to : "/schedule"} {...props}>
      {children}
    </a>
  ),
  useRouter: () => router.current,
}))
vi.mock("@/hooks/useDashboardSchedule", () => ({ useDashboardSchedule: () => query.current }))
vi.mock("@/utils/scheduleUtils", () => ({
  fmtTime: (value: string) => value,
  nowParity: () => "odd",
  parseMinutes: (value?: string) => {
    const [hours = Number.NaN, minutes = Number.NaN] = (value ?? "").split(":").map(Number)
    return Number.isFinite(hours) && Number.isFinite(minutes) ? hours * 60 + minutes : null
  },
}))
vi.mock("@/components/ui/Card", () => ({
  Card: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <article {...props}>{children}</article>
  ),
}))
vi.mock("@/components/ui/Badge", () => ({
  Badge: ({ label }: { label: string }) => <span>{label}</span>,
}))
vi.mock("@/components/ui/Button", () => ({
  Button: ({
    as: Component = "button",
    children,
    ...props
  }: {
    as?: ElementType
    children?: ReactNode
  } & Record<string, unknown>) => <Component {...props}>{children}</Component>,
}))
vi.mock("@/components/ui/ProgressBar", () => ({
  ProgressBar: ({ value, ariaLabel }: { value: number; ariaLabel: string }) => (
    <progress aria-label={ariaLabel} max={100} value={value} />
  ),
}))
vi.mock("@/components/ui/Skeleton", () => ({
  Skeleton: ({ width, height }: { width: number | string; height: number }) => (
    <span data-testid="schedule-skeleton" data-width={width} data-height={height} />
  ),
}))

import { ScheduleCard } from "../ScheduleCard"

const time = new Date(2026, 6, 31, 10, 30)
const renderCard = () =>
  render(<ScheduleCard time={time} userRole="student" userGroupId="group-1" />)

describe("AUD-213 dashboard schedule query state", () => {
  beforeEach(() => {
    query.current = { data: undefined, isLoading: false, isFetching: false, isError: false }
  })

  it("preserves the translated empty state after a successful empty response", () => {
    renderCard()

    expect(screen.getByText("dashboard:noClasses")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("keeps the loading state distinct from a successful empty schedule", () => {
    query.current = { data: undefined, isLoading: true, isFetching: true, isError: false }

    renderCard()

    expect(screen.getAllByTestId("schedule-skeleton")).not.toHaveLength(0)
    expect(screen.queryByText("dashboard:noClasses")).not.toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("does not report a failed schedule request as a day with no classes", () => {
    query.current = { data: undefined, isLoading: false, isFetching: false, isError: true }

    renderCard()

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong")
    expect(screen.queryByText("dashboard:noClasses")).not.toBeInTheDocument()
  })
})
