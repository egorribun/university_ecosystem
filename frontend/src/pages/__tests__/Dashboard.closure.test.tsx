import type { CSSProperties, MouseEventHandler, ReactNode } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type DashboardUser = { role?: string | null; group_id?: string | null }
type Story = { id: string; title: string; cta_url: string | null }

const state = vi.hoisted(() => ({
  authLoading: false,
  user: { role: "student", group_id: "group-1" } as DashboardUser | null,
  language: "en",
  narrow: false,
  storiesInHero: true,
  reduced: false,
  storiesData: undefined as Story[] | undefined,
  storiesLoading: false,
  weatherAnimation: undefined as string | undefined,
  scheduleQuery: { isLoading: false },
  newsQuery: { isLoading: false },
  eventsQuery: { isLoading: false },
  queryClient: { id: "dashboard-test-client" },
  prefetch: vi.fn(),
  tiltDisabled: [] as boolean[],
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => state.queryClient,
}))

vi.mock("framer-motion", () => {
  const MotionDiv = ({
    children,
    className,
    style,
    onMouseMove,
    onMouseLeave,
    initial,
  }: {
    children?: ReactNode
    className?: string
    style?: CSSProperties
    onMouseMove?: MouseEventHandler<HTMLDivElement>
    onMouseLeave?: MouseEventHandler<HTMLDivElement>
    initial?: unknown
  }) => (
    <div
      className={className}
      style={style}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      data-testid="motion-card"
      data-cascade={initial ? "active" : "idle"}
    >
      {children}
    </div>
  )

  return { m: { div: MotionDiv } }
})

vi.mock("@/components/ui/SEO", () => ({
  SEO: ({ title }: { title: string }) => <span data-testid="seo" data-title={title} />,
}))

vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children, className }: { children?: ReactNode; className?: string }) => (
    <main data-testid="page-layout" className={className}>
      {children}
    </main>
  ),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: state.user, loading: state.authLoading }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  getLocaleForLanguage: (language: string) => `${language}-locale`,
  useLanguage: () => ({ language: state.language }),
}))

vi.mock("@/hooks/useClock", () => ({
  useClock: () => ({ hh: "10", mm: "30", dateStr: "Friday", time: "10:30" }),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    if (query.includes("max-width")) return state.narrow
    if (query.includes("min-width")) return state.storiesInHero
    return state.reduced
  },
}))

vi.mock("@/hooks/useTilt", () => ({
  useTilt: ({ disabled }: { disabled: boolean }) => {
    state.tiltDisabled.push(disabled)
    return {
      ref: vi.fn(),
      style: {} as CSSProperties,
      onMouseMove: vi.fn(),
      onMouseLeave: vi.fn(),
    }
  },
}))

vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => state.scheduleQuery,
}))

vi.mock("@/hooks/useDashboardNews", () => ({
  useDashboardNews: () => state.newsQuery,
}))

vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => state.eventsQuery,
}))

vi.mock("@/hooks/useDashboardStories", () => ({
  useDashboardStories: () => ({
    data: state.storiesData,
    isLoading: state.storiesLoading,
  }),
  prefetchDashboardStories: state.prefetch,
}))

vi.mock("@/hooks/useWeather", () => ({
  useWeather: () => ({
    data: state.weatherAnimation === undefined ? undefined : { animation: state.weatherAnimation },
  }),
}))

vi.mock("@/components/dashboard/DashboardHero", () => ({
  DashboardHero: ({ time, storiesSlot }: { time: string; storiesSlot?: ReactNode }) => (
    <section data-testid="dashboard-hero">
      <span data-testid="hero-time">{time}</span>
      {storiesSlot ? <div data-testid="hero-stories">{storiesSlot}</div> : null}
    </section>
  ),
}))

vi.mock("@/components/stories", () => ({
  DashboardStories: ({
    stories,
    loading,
    onPrefetch,
    onStoryOpen,
    maxVisibleStories,
  }: {
    stories: Story[]
    loading: boolean
    onPrefetch: () => void
    onStoryOpen: () => void
    maxVisibleStories?: number
  }) => (
    <section
      data-testid="dashboard-stories"
      data-loading={String(loading)}
      data-count={String(stories.length)}
      data-max-visible={maxVisibleStories === undefined ? "all" : String(maxVisibleStories)}
    >
      <button type="button" onMouseEnter={onPrefetch}>
        prefetch stories
      </button>
      {stories.length > 0 && (
        <button type="button" onClick={onStoryOpen}>
          open story
        </button>
      )}
      {stories.map((story) => (
        <span key={story.id} data-testid="story" data-cta={story.cta_url ?? "none"}>
          {story.title}
        </span>
      ))}
    </section>
  ),
}))

vi.mock("@/components/dashboard/DashboardBackdrop", () => ({
  DashboardBackdrop: () => <span data-testid="dashboard-backdrop" />,
}))

vi.mock("@/components/dashboard/WeatherAmbient", () => ({
  WeatherAmbient: ({ animation, disabled }: { animation: string; disabled: boolean }) => (
    <span
      data-testid="weather-ambient"
      data-animation={animation}
      data-disabled={String(disabled)}
    />
  ),
}))

vi.mock("@/components/dashboard/ScheduleCard", () => ({
  ScheduleCard: () => <span data-testid="schedule-card" />,
}))

vi.mock("@/components/dashboard/NewsCard", () => ({
  NewsCard: () => <span data-testid="news-card" />,
}))

vi.mock("@/components/dashboard/EventsCard", () => ({
  EventsCard: () => <span data-testid="events-card" />,
}))

vi.mock("@/components/dashboard/DashboardSkeleton", () => ({
  default: () => <span data-testid="dashboard-skeleton" />,
}))

vi.mock("@/components/ui/SkeletonMorph", () => ({
  SkeletonMorph: ({
    loaded,
    skeleton,
    children,
  }: {
    loaded: boolean
    skeleton: ReactNode
    children: ReactNode
  }) => (loaded ? <>{children}</> : <div data-testid="widget-skeleton">{skeleton}</div>),
}))

vi.mock("@/components/ui", () => ({
  Card: ({ children }: { children?: ReactNode }) => <section>{children}</section>,
  Skeleton: ({ className }: { className?: string }) => (
    <span data-testid="skeleton" className={className} />
  ),
}))

vi.mock("@/components/error/WidgetErrorBoundary", () => ({
  WidgetErrorBoundary: ({ children, widgetName }: { children: ReactNode; widgetName: string }) => (
    <section data-widget={widgetName}>{children}</section>
  ),
}))

import Dashboard from "../Dashboard"

const realStory: Story = { id: "story-1", title: "Real story", cta_url: "/events" }
const e2eMode = import.meta.env.VITE_E2E_MODE === "1"

beforeEach(() => {
  state.authLoading = false
  state.user = { role: "student", group_id: "group-1" }
  state.language = "en"
  state.narrow = false
  state.storiesInHero = true
  state.reduced = false
  state.storiesData = undefined
  state.storiesLoading = false
  state.weatherAnimation = undefined
  state.scheduleQuery = { isLoading: false }
  state.newsQuery = { isLoading: false }
  state.eventsQuery = { isLoading: false }
  state.prefetch.mockClear()
  state.tiltDisabled.length = 0
  window.sessionStorage.clear()
  vi.useRealTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("Dashboard closure behavior", () => {
  it("keeps loaded cards content-sized without tilt or scroll-driven transforms", () => {
    window.sessionStorage.setItem("dash-cascade-done", "1")
    const addEventListener = vi.spyOn(window, "addEventListener")

    render(<Dashboard />)

    expect(state.tiltDisabled).toEqual([])
    expect(
      addEventListener.mock.calls.filter(([eventName]) => String(eventName) === "scroll")
    ).toHaveLength(0)

    for (const card of document.querySelectorAll(
      ".vt-dash-schedule, .vt-dash-news, .vt-dash-events"
    )) {
      expect(card).not.toHaveClass("min-h-[400px]")
      expect((card as HTMLElement).style.transform).toBe("")
    }
  })

  it("shows the auth loading shell before rendering dashboard content", () => {
    state.authLoading = true

    render(<Dashboard />)

    expect(screen.getByTestId("dashboard-skeleton")).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard-hero")).not.toBeInTheDocument()
  })

  it("renders an honest stories loading state, stable widgets, and a restrained cascade reveal", () => {
    vi.useFakeTimers()
    state.scheduleQuery = { isLoading: true }
    state.newsQuery = { isLoading: true }
    state.eventsQuery = { isLoading: true }
    state.storiesLoading = true
    state.weatherAnimation = "drizzle"

    const rect = {
      top: -500,
      left: 0,
      right: 1000,
      bottom: 500,
      width: 1000,
      height: 1000,
      x: 0,
      y: -500,
      toJSON: () => ({}),
    } as DOMRect
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(rect)
    const callbacks: FrameRequestCallback[] = []
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        callbacks.push(callback)
        return callbacks.length
      })
    const cancelAnimationFrame = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation(() => undefined)

    const { unmount } = render(<Dashboard />)

    if (e2eMode) {
      expect(screen.queryByTestId("dashboard-hero")).not.toBeInTheDocument()
      expect(document.querySelector('[data-e2e-stub="dashboard-hero"]')).toBeInTheDocument()
      expect(screen.queryByTestId("dashboard-stories")).not.toBeInTheDocument()
      expect(document.querySelector('[data-e2e-stub="dashboard-stories"]')).toBeNull()
      expect(screen.queryByTestId("weather-ambient")).not.toBeInTheDocument()
    } else {
      expect(screen.getByTestId("dashboard-hero")).toBeInTheDocument()
      expect(screen.getByTestId("hero-stories")).toBeInTheDocument()
      expect(screen.getByTestId("dashboard-stories")).toHaveAttribute("data-loading", "true")
      expect(screen.getByTestId("dashboard-stories")).toHaveAttribute("data-count", "0")
      expect(screen.getByTestId("dashboard-stories")).toHaveAttribute("data-max-visible", "9")
      expect(screen.queryAllByTestId("story")).toHaveLength(0)
      expect(screen.getByTestId("weather-ambient")).toHaveAttribute("data-animation", "drizzle")
    }
    expect(screen.getAllByTestId("motion-card")).toHaveLength(3)
    expect(screen.getAllByTestId("motion-card").at(0)).toHaveAttribute("data-cascade", "active")
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0)
    expect(state.tiltDisabled).toEqual([])
    expect(window.sessionStorage.getItem("dash-cascade-done")).toBe("1")

    if (!e2eMode) {
      fireEvent.mouseEnter(screen.getByRole("button", { name: "prefetch stories" }))
      expect(screen.queryByRole("button", { name: "open story" })).not.toBeInTheDocument()
      expect(state.prefetch).not.toHaveBeenCalled()
    }

    window.dispatchEvent(new Event("scroll"))
    window.dispatchEvent(new Event("scroll"))
    expect(requestAnimationFrame).not.toHaveBeenCalled()
    expect(callbacks).toHaveLength(0)
    const aurora = document.querySelector(".aurora-mesh")!
    const backdrop = aurora.children[0] as HTMLElement
    const grid = document.querySelector(".vt-dash-schedule")!.parentElement!.parentElement!
    expect(backdrop.style.getPropertyValue("--dashboard-backdrop-y")).toBe("")
    expect(grid.style.getPropertyValue("--dashboard-grid-scale")).toBe("")
    expect(grid.style.getPropertyValue("--dashboard-grid-opacity")).toBe("")

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getAllByTestId("motion-card").at(0)).toHaveAttribute("data-cascade", "idle")

    window.dispatchEvent(new Event("scroll"))
    unmount()
    expect(cancelAnimationFrame).not.toHaveBeenCalled()
  })

  it("renders real stories below the hero and falls back to no weather animation", () => {
    state.storiesInHero = false
    state.storiesData = [realStory]
    state.storiesLoading = true
    state.user = null
    window.sessionStorage.setItem("dash-cascade-done", "1")

    render(<Dashboard />)

    if (e2eMode) {
      expect(screen.queryByTestId("dashboard-hero")).not.toBeInTheDocument()
      expect(document.querySelector('[data-e2e-stub="dashboard-hero"]')).toBeInTheDocument()
      expect(screen.queryByTestId("dashboard-stories")).not.toBeInTheDocument()
      expect(document.querySelector('[data-e2e-stub="dashboard-stories"]')).toBeInTheDocument()
      expect(screen.queryByTestId("weather-ambient")).not.toBeInTheDocument()
    } else {
      expect(screen.getByTestId("dashboard-hero")).toBeInTheDocument()
      expect(screen.queryByTestId("hero-stories")).not.toBeInTheDocument()
      expect(screen.getByTestId("dashboard-stories")).toHaveAttribute("data-loading", "false")
      expect(screen.getByTestId("dashboard-stories")).toHaveAttribute("data-count", "1")
      expect(screen.getByText("Real story")).toBeInTheDocument()
      expect(screen.getByTestId("weather-ambient")).toHaveAttribute("data-animation", "none")
    }
    expect(screen.getAllByTestId("motion-card").at(0)).toHaveAttribute("data-cascade", "idle")
    expect(screen.getByTestId("schedule-card")).toBeInTheDocument()
    expect(screen.getByTestId("news-card")).toBeInTheDocument()
    expect(screen.getByTestId("events-card")).toBeInTheDocument()
    expect(state.tiltDisabled).toEqual([])
  })

  it("disables motion for narrow reduced-motion users and tolerates missing sessionStorage", () => {
    state.narrow = true
    state.reduced = true
    state.storiesInHero = false
    state.weatherAnimation = "snow"
    vi.stubGlobal("sessionStorage", undefined)

    const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")
    render(<Dashboard />)

    if (e2eMode) {
      expect(screen.queryByTestId("dashboard-stories")).not.toBeInTheDocument()
      expect(document.querySelector('[data-e2e-stub="dashboard-stories"]')).toBeInTheDocument()
      expect(screen.queryByTestId("weather-ambient")).not.toBeInTheDocument()
    } else {
      expect(screen.getByTestId("dashboard-stories")).toBeInTheDocument()
      expect(screen.getByTestId("weather-ambient")).toHaveAttribute("data-animation", "snow")
      expect(screen.getByTestId("weather-ambient")).toHaveAttribute("data-disabled", "true")
    }
    expect(screen.queryByTestId("skeleton")).not.toBeInTheDocument()
    expect(state.tiltDisabled).toEqual([])
    expect(requestAnimationFrame).not.toHaveBeenCalled()

    const backdrop = document.querySelector(".aurora-mesh")!.children[0] as HTMLElement
    const grid = document.querySelector(".vt-dash-schedule")!.parentElement!.parentElement!
    expect(backdrop.style.transform).toBe("")
    expect(grid.style.transform).toBe("")
    expect(grid.style.opacity).toBe("")
  })

  it("disables ambient particles on narrow devices even without reduced motion", () => {
    state.narrow = true
    state.reduced = false
    state.weatherAnimation = "storm"

    render(<Dashboard />)

    if (!e2eMode) {
      expect(screen.getByTestId("weather-ambient")).toHaveAttribute("data-disabled", "true")
    }
  })

  it("renders the lightweight compile-time E2E stubs", async () => {
    vi.stubEnv("VITE_E2E_MODE", "1")
    vi.resetModules()
    state.storiesInHero = false

    const { default: E2EDashboard } = await import("../Dashboard")
    const { unmount } = render(<E2EDashboard />)

    expect(document.querySelector('[data-e2e-stub="dashboard-hero"]')).toBeInTheDocument()
    expect(document.querySelector('[data-e2e-stub="dashboard-stories"]')).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard-hero")).not.toBeInTheDocument()
    expect(screen.queryByTestId("weather-ambient")).not.toBeInTheDocument()
    unmount()
  })

  it("keeps the first viewport paint-ready during Lighthouse SSR audits", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    vi.resetModules()

    const { default: LhciDashboard } = await import("../Dashboard")
    const { unmount } = render(<LhciDashboard />)

    expect(screen.getAllByTestId("motion-card").at(0)).toHaveAttribute("data-cascade", "idle")
    expect(window.sessionStorage.getItem("dash-cascade-done")).toBeNull()
    unmount()
  })
})
