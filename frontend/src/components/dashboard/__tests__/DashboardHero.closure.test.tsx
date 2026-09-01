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
const useTranslationMock = vi.hoisted(() =>
  vi.fn((_namespaces: string[]) => ({
    t: (key: string, options?: { week?: number }) =>
      options?.week == null ? key : `${key}:${options.week}`,
  }))
)

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
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
    useTranslationMock.mockClear()
  })

  it("renders personalized greeting, a static special marker, and stories", () => {
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
    expect(useTranslationMock).toHaveBeenCalledWith(["dashboard", "common"])
    expect(document.querySelector('[class*="animate-[spin_40s_linear_infinite]"]')).toBeNull()
    expect(document.querySelector('[class*="group-hover:translate-x"]')).toBeNull()
    expect(document.querySelector(".animate-dash-colon-blink")).toBeNull()
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

  it("refreshes academic-week parity when the clock date changes", () => {
    const { rerender } = render(<DashboardHero {...baseProps} user={null} />)
    expect(screen.getByRole("status")).toHaveTextContent("dashboard:academicWeek:32")
    expect(screen.getByText("dashboard:parityEven")).toBeInTheDocument()

    parityMock.mockReturnValue("odd")
    rerender(
      <DashboardHero
        {...baseProps}
        time={new Date(2026, 7, 10, 9, 15)}
        dateStr="Monday, 10 August"
        user={null}
      />
    )

    expect(screen.getByRole("status")).toHaveTextContent("dashboard:academicWeek:33")
    expect(screen.getByText("dashboard:parityOdd")).toBeInTheDocument()
  })

  it("computes ISO academic weeks across year boundaries", () => {
    const cases = [
      [new Date(2021, 0, 1, 9, 15), 53],
      [new Date(2021, 0, 4, 9, 15), 1],
      [new Date(2020, 11, 31, 9, 15), 53],
      [new Date(2022, 0, 1, 9, 15), 52],
    ] as const

    for (const [time, expectedWeek] of cases) {
      const { unmount } = render(
        <DashboardHero
          {...baseProps}
          time={time}
          user={null}
          dateStr={time.toISOString().slice(0, 10)}
        />
      )
      expect(screen.getByRole("status")).toHaveTextContent(`dashboard:academicWeek:${expectedWeek}`)
      unmount()
    }
  })

  it("preserves the dashboard header visual contract and separator", () => {
    render(<DashboardHero {...baseProps} user={null} />)

    const header = screen.getByRole("banner")
    expect(header).toHaveClass(
      "glass-noise",
      "relative",
      "rounded-xl",
      "border",
      "border-(--dash-border)",
      "px-8",
      "py-8",
      "md:px-10",
      "md:py-9",
      "greeting-morning"
    )
    expect(header).toHaveStyle({
      background: "var(--hero-card-bg)",
      boxShadow:
        "0 1px 3px color-mix(in srgb, black 8%, transparent), 0 4px 16px color-mix(in srgb, black 6%, transparent), inset 0 1px 0 color-mix(in srgb, white 4%, transparent)",
    })

    const accent = header.querySelector('span[aria-hidden="true"]')
    expect(accent).toHaveClass(
      "pointer-events-none",
      "absolute",
      "inset-x-[20%]",
      "top-0",
      "z-10",
      "h-px"
    )
    expect(accent).toHaveStyle({ background: "var(--dash-accent-line)", opacity: "0.5" })

    const heading = screen.getByRole("heading")
    expect(heading).toHaveClass(
      "font-display",
      "font-extrabold",
      "leading-[1.15]",
      "tracking-tight",
      "min-h-[2lh]"
    )
    expect(heading).toHaveAttribute(
      "style",
      expect.stringContaining("font-size: clamp(1.75rem, 3vw, 2.75rem)")
    )

    const parity = screen.getByText("dashboard:parityEven")
    expect(parity.parentElement?.textContent).toBe(
      "dashboard:academicWeek:32 · dashboard:parityEven"
    )
  })

  it("does not mount an empty stories wrapper when no slot is provided", () => {
    render(<DashboardHero {...baseProps} user={null} />)

    const header = screen.getByRole("banner")
    expect(
      [...header.querySelectorAll("div")].some((node) =>
        String(node.className).includes("min-[1220px]:flex-1")
      )
    ).toBe(false)
  })
})
