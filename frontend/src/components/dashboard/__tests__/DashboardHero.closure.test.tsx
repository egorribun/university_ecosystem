import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { User } from "@/types/User"

const greetingState = vi.hoisted(() => ({
  greeting: "Good morning",
  greetingKey: "morning",
  specialKey: null as string | null,
  emoji: null as string | null,
}))

const parityMock = vi.hoisted(() => vi.fn(() => "even" as "even" | "odd"))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { week?: number }) =>
      options?.week == null ? key : `${key}:${options.week}`,
  }),
}))

vi.mock("@/hooks/useGreeting", () => ({
  useGreeting: () => greetingState,
}))

vi.mock("@/utils/scheduleUtils", () => ({
  nowParity: () => parityMock(),
}))

vi.mock("@/components/motion/ScrollReveal", () => ({
  ScrollReveal: ({ children }: { children?: ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/ui/WeatherWidget", () => ({
  default: () => <div data-testid="weather-widget" />,
}))

vi.mock("@/components/ui", () => ({
  Badge: ({
    children,
    "aria-label": ariaLabel,
  }: {
    children?: ReactNode
    "aria-label"?: string
  }) => <div aria-label={ariaLabel}>{children}</div>,
}))

vi.mock("framer-motion", () => ({
  m: {
    span: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <span className={className}>{children}</span>
    ),
  },
}))

vi.mock("lucide-react", () => ({
  Sparkles: () => <svg data-testid="sparkles" aria-hidden="true" />,
}))

import { DashboardHero } from "@/components/dashboard/DashboardHero"

const baseProps = {
  time: new Date(2026, 7, 3, 9, 15),
  hh: "09",
  mm: "15",
  dateStr: "Monday, 3 August",
  isNarrow: false,
  prefersReducedMotion: false,
}

describe("DashboardHero closure", () => {
  beforeEach(() => {
    greetingState.greeting = "Good morning"
    greetingState.greetingKey = "morning"
    greetingState.specialKey = null
    greetingState.emoji = null
    parityMock.mockReturnValue("even")
  })

  it("renders personalized greeting, special marker, motion decorations, and stories", () => {
    greetingState.greeting = "Happy birthday"
    greetingState.greetingKey = "birthday"
    greetingState.specialKey = "birthday"
    greetingState.emoji = "🎉"

    render(
      <DashboardHero
        {...baseProps}
        user={{ full_name: "Ada Lovelace" } as User}
        storiesSlot={<div data-testid="stories-slot">Stories</div>}
      />
    )

    expect(screen.getByRole("heading", { name: /Happy birthday, Ada!/ })).toBeInTheDocument()
    expect(screen.getByTestId("sparkles")).toBeInTheDocument()
    expect(screen.getByText("🎉")).toBeInTheDocument()
    expect(screen.getByTestId("stories-slot")).toBeInTheDocument()
    expect(screen.getByLabelText("common:ariaCurrentTime")).toHaveTextContent("09")
    expect(screen.getByText(/dashboard:academicWeek:/)).toBeInTheDocument()
    expect(screen.getByText("dashboard:parityEven")).toBeInTheDocument()
    expect(screen.getByTestId("weather-widget")).toBeInTheDocument()
  })

  it("renders the reduced narrow fallback without optional decorations", () => {
    parityMock.mockReturnValue("odd")

    const { container } = render(
      <DashboardHero
        {...baseProps}
        time={new Date(2026, 7, 2, 9, 15)}
        user={null}
        isNarrow
        prefersReducedMotion
      />
    )

    expect(screen.getByRole("heading", { name: "Good morning!" })).toBeInTheDocument()
    expect(screen.queryByTestId("sparkles")).not.toBeInTheDocument()
    expect(screen.queryByText("🎉")).not.toBeInTheDocument()
    expect(screen.getByText("dashboard:parityOdd")).toBeInTheDocument()
    expect(screen.queryByTestId("stories-slot")).not.toBeInTheDocument()
    expect(container.querySelector('[class*="animate-[spin_40s_linear_infinite]"]')).toBeNull()
  })
})
