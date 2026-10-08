import { act, StrictMode, type ReactNode } from "react"
import { LazyMotion, MotionConfig, domAnimation } from "framer-motion"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ prefersReducedMotion: false }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children?: ReactNode }) => <a href="/">{children}</a>,
  useNavigate: () => () => Promise.resolve(),
}))
vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))
vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: "student", group_id: "group-1" }, loading: false }),
}))
vi.mock("@/contexts/LanguageContext", () => ({
  getLocaleForLanguage: () => "en-US",
  useLanguage: () => ({ language: "en" }),
}))
vi.mock("@/hooks/useClock", () => ({
  useClock: () => ({
    hh: "10",
    mm: "30",
    dateStr: "Monday",
    time: new Date("2026-10-05T10:30:00.000Z"),
    isReady: true,
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) =>
    query === "(prefers-reduced-motion: reduce)" && state.prefersReducedMotion,
}))
vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => ({ isLoading: false }),
}))
vi.mock("@/hooks/useDashboardNews", () => ({
  useDashboardNews: () => ({ isPending: false }),
}))
vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => ({ isPending: false }),
}))
vi.mock("@/hooks/useDashboardStories", () => ({
  useDashboardStories: () => ({ data: [], isLoading: false }),
}))
vi.mock("@/hooks/useWeather", () => ({ useWeather: () => ({ data: undefined }) }))
vi.mock("@/components/dashboard/DashboardHero", () => ({
  DashboardHero: () => null,
}))
vi.mock("@/components/dashboard/DashboardBackdrop", () => ({ DashboardBackdrop: () => null }))
vi.mock("@/components/dashboard/WeatherAmbient", () => ({ WeatherAmbient: () => null }))
vi.mock("@/components/dashboard/ScheduleCard", () => ({ ScheduleCard: () => <article /> }))
vi.mock("@/components/dashboard/NewsCard", () => ({ NewsCard: () => <article /> }))
vi.mock("@/components/dashboard/EventsCard", () => ({ EventsCard: () => <article /> }))
vi.mock("@/components/stories", () => ({ DashboardStories: () => null }))
vi.mock("@/components/dashboard/DashboardSkeleton", () => ({ DashboardSkeleton: () => null }))
vi.mock("@/components/ui/SkeletonMorph", () => ({
  SkeletonMorph: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock("@/components/error/WidgetErrorBoundary", () => ({
  WidgetErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

import Dashboard from "@/pages/Dashboard"

function DashboardUnderMotionProviders() {
  return (
    <StrictMode>
      <LazyMotion strict features={domAnimation}>
        <MotionConfig reducedMotion="user">
          <Dashboard />
        </MotionConfig>
      </LazyMotion>
    </StrictMode>
  )
}

const cardSelectors = [".vt-dash-schedule", ".vt-dash-news", ".vt-dash-events"]
const hydratedRoots: Root[] = []

function cardMotionStyles(markup: string): Array<string | null> {
  const parsed = new DOMParser().parseFromString(markup, "text/html")
  return cardSelectors.map((selector) => {
    const card = parsed.querySelector(selector)
    const wrapper = card?.parentElement
    return wrapper?.getAttribute("style") ? wrapper.style.cssText : null
  })
}

function cardMotionOpacities(markup: string): Array<string | null> {
  const parsed = new DOMParser().parseFromString(markup, "text/html")
  return cardSelectors.map((selector) => {
    const wrapper = parsed.querySelector(selector)?.parentElement
    return wrapper?.hasAttribute("style") ? wrapper.style.opacity : null
  })
}

function renderFreshServerMarkup(): string {
  const browserSessionStorage = window.sessionStorage
  vi.stubGlobal("sessionStorage", undefined)
  try {
    return renderToString(<DashboardUnderMotionProviders />)
  } finally {
    vi.stubGlobal("sessionStorage", browserSessionStorage)
  }
}

afterEach(() => {
  for (const root of hydratedRoots.splice(0)) {
    act(() => root.unmount())
  }
  state.prefersReducedMotion = false
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  document.body.replaceChildren()
  window.sessionStorage.clear()
})

describe("Dashboard first-session cascade hydration", () => {
  it("renders the same initial card visibility on the server and for a fresh browser session", () => {
    const browserSessionStorage = window.sessionStorage
    browserSessionStorage.clear()
    const serverMarkup = renderFreshServerMarkup()
    const freshBrowserMarkup = renderToString(<DashboardUnderMotionProviders />)

    expect(cardMotionStyles(freshBrowserMarkup)).toEqual(cardMotionStyles(serverMarkup))
  })

  it("hydrates fresh-session markup without replacing the server-rendered dashboard", async () => {
    const browserSessionStorage = window.sessionStorage
    browserSessionStorage.clear()
    const serverMarkup = renderFreshServerMarkup()

    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.appendChild(container)
    const serverCardNodes = cardSelectors.map((selector) => container.querySelector(selector))

    const recoverableErrors: unknown[] = []
    let root: Root | undefined
    await act(async () => {
      root = hydrateRoot(container, <DashboardUnderMotionProviders />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
      hydratedRoots.push(root)
      await Promise.resolve()
    })

    expect(recoverableErrors).toEqual([])
    expect(cardSelectors.map((selector) => container.querySelector(selector))).toEqual(
      serverCardNodes
    )
    expect(cardMotionOpacities(container.innerHTML)).toEqual(["0", "0", "0"])
    expect(browserSessionStorage.getItem("dash-cascade-done")).toBe("1")

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1000))
    })
    expect(cardMotionOpacities(container.innerHTML)).toEqual(["1", "1", "1"])
  })

  it("does not start the cascade when reduced motion is preferred", async () => {
    state.prefersReducedMotion = true
    const browserSessionStorage = window.sessionStorage
    browserSessionStorage.clear()
    const serverMarkup = renderFreshServerMarkup()

    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.appendChild(container)
    const recoverableErrors: unknown[] = []
    let root: Root | undefined

    await act(async () => {
      root = hydrateRoot(container, <DashboardUnderMotionProviders />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
      hydratedRoots.push(root)
      await Promise.resolve()
    })

    expect(recoverableErrors).toEqual([])
    expect(cardMotionStyles(container.innerHTML)).toEqual([
      "opacity: 1; transform: translateY(0);",
      "opacity: 1; transform: translateY(0);",
      "opacity: 1; transform: translateY(0);",
    ])
    expect(browserSessionStorage.getItem("dash-cascade-done")).toBeNull()
  })

  it("restores visible cards and clears an interrupted cascade when reduced motion turns on", async () => {
    const browserSessionStorage = window.sessionStorage
    browserSessionStorage.clear()
    const serverMarkup = renderFreshServerMarkup()

    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.appendChild(container)
    let root: Root | undefined
    const recoverableErrors: unknown[] = []

    await act(async () => {
      root = hydrateRoot(container, <DashboardUnderMotionProviders />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
      hydratedRoots.push(root)
      await Promise.resolve()
    })

    expect(cardMotionOpacities(container.innerHTML)).toEqual(["0", "0", "0"])
    expect(browserSessionStorage.getItem("dash-cascade-done")).toBe("1")

    state.prefersReducedMotion = true
    await act(async () => {
      root?.render(<DashboardUnderMotionProviders />)
      await Promise.resolve()
    })

    expect(recoverableErrors).toEqual([])
    expect(cardMotionOpacities(container.innerHTML)).toEqual(["1", "1", "1"])
    expect(browserSessionStorage.getItem("dash-cascade-done")).toBeNull()
  })

  it("keeps the first client render SSR-identical when only the browser media query prefers reduced motion", async () => {
    state.prefersReducedMotion = false
    const browserSessionStorage = window.sessionStorage
    browserSessionStorage.clear()
    const serverMarkup = renderFreshServerMarkup()
    vi.stubGlobal("matchMedia", () => ({ matches: true }))

    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.appendChild(container)
    const serverCardNodes = cardSelectors.map((selector) => container.querySelector(selector))
    const recoverableErrors: unknown[] = []

    await act(async () => {
      const root = hydrateRoot(container, <DashboardUnderMotionProviders />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
      hydratedRoots.push(root)
      await Promise.resolve()
    })

    expect(recoverableErrors).toEqual([])
    expect(cardSelectors.map((selector) => container.querySelector(selector))).toEqual(
      serverCardNodes
    )
    expect(cardMotionStyles(container.innerHTML)).toEqual([
      "opacity: 1; transform: translateY(0);",
      "opacity: 1; transform: translateY(0);",
      "opacity: 1; transform: translateY(0);",
    ])
    expect(browserSessionStorage.getItem("dash-cascade-done")).toBeNull()
  })
})
