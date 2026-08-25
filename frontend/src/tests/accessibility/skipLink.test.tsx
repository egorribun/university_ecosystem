import { describe, expect, it, vi } from "vitest"
import type { ContextType, ReactElement } from "react"
import { QueryClient } from "@tanstack/react-query"

import { checkA11y } from "../axeTest"
import { AuthContext } from "@/contexts/AuthContext"
import Profile from "@/pages/Profile"
import Login from "@/pages/Login"
import Dashboard from "@/pages/Dashboard"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// Wave 115 SW2 closed SW1-remainder: Dashboard uses framer-motion `useScroll`
// which requires a hydrated container ref to compute scroll progress. jsdom
// doesn't run layout, so `useScroll` throws "Target ref is defined but not
// hydrated" on mount. Returning real MotionValue instances from a mocked
// `useScroll` sidesteps the hydration check while keeping `useTransform`
// untouched (it accepts MotionValues normally). `a11y.test.tsx` uses a
// different workaround via hook-level mocks of DashboardHero sub-components;
// both patterns coexist.
vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion")
  return {
    ...actual,
    useScroll: () => ({
      scrollY: actual.motionValue(0),
      scrollYProgress: actual.motionValue(0),
      scrollX: actual.motionValue(0),
      scrollXProgress: actual.motionValue(0),
    }),
  }
})

vi.mock("@/hooks/useDashboardStories", () => ({
  useDashboardStories: () => ({ data: [], isLoading: false }),
  prefetchDashboardStories: vi.fn(),
}))

vi.mock("@/hooks/useDashboardNews", () => ({
  useDashboardNews: () => ({ data: [], isLoading: false }),
  prefetchDashboardNews: vi.fn(),
}))

vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => ({ data: [], isLoading: false }),
  prefetchDashboardEvents: vi.fn(),
}))

vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => ({ data: [], isLoading: false }),
}))

vi.mock("@/components/DashboardStories", () => ({
  default: () => <div data-testid="stub-dashboard-stories" />,
}))

vi.mock("@/components/ui/WeatherWidget", () => ({
  default: () => <div data-testid="stub-weather-widget" />,
}))

type AuthContextValue = ContextType<typeof AuthContext>

const baseAuthValue: AuthContextValue = {
  login: vi.fn(),
  logout: vi.fn(),
  setUser: vi.fn(),
  refresh: vi.fn(),
  submitMfaChallenge: vi.fn(),
  requireMfa: vi.fn(),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

const unauthenticatedAuthValue: AuthContextValue = {
  ...baseAuthValue,
}

type RouteTestCase = {
  name: string
  element: ReactElement
  initialEntries: string[]
  authValue: typeof baseAuthValue
}

const routes: RouteTestCase[] = [
  {
    name: "profile",
    element: <Profile />,
    initialEntries: ["/profile"],
    authValue: baseAuthValue,
  },
  {
    name: "login",
    element: <Login />,
    initialEntries: ["/login"],
    authValue: unauthenticatedAuthValue,
  },
  {
    name: "dashboard",
    element: <Dashboard />,
    initialEntries: ["/dashboard"],
    authValue: baseAuthValue,
  },
]

const GlobalSkipLink = () => (
  <a href="#main" className="skip-link">
    Skip to content
  </a>
)

async function renderRoute({ element, authValue, initialEntries }: RouteTestCase) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  const [initialPath] = initialEntries
  const routePath = initialPath ? initialPath.split("?")[0] || "/" : "/"

  const Wrapped = () => (
    <AuthContext.Provider value={authValue}>
      <>
        <GlobalSkipLink />
        {element}
      </>
    </AuthContext.Provider>
  )

  const result = await renderWithRouter({
    ui: Wrapped,
    path: routePath,
    initialPath,
    queryClient,
    authProvider: false,
  })

  await checkA11y(result.container)

  queryClient.clear()
  return result
}

describe("global skip link", () => {
  it.each(routes)("renders a single skip link on $name", async (route) => {
    const { container } = await renderRoute(route)
    expect(container.querySelectorAll("a.skip-link")).toHaveLength(1)
  })
})
