import { describe, expect, it, vi } from "vitest"
import type { ContextType, ReactElement } from "react"
import { QueryClient } from "@tanstack/react-query"

import { checkA11y } from "../axeTest"
import { AuthContext } from "@/contexts/AuthContext"
import Profile from "@/pages/Profile"
import Login from "@/pages/Login"
// Wave 115 SW1-remainder: Dashboard route omitted — Dashboard uses framer-motion
// `useScroll` which throws "Target ref is defined but not hydrated" under jsdom.
// `a11y.test.tsx` mocks the dashboard hooks to work around this; this file
// intentionally renders the real page, so the route gets restored once the
// hook mocks move to a shared helper or framer's scroll primitives get a jsdom
// polyfill.
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

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
  loginWithPasskey: vi.fn(),
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
