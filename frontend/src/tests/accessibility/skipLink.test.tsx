import { describe, expect, it, vi } from "vitest"
import type { ContextType, ReactElement } from "react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { renderWithA11y } from "../axeTest"
import { AuthContext } from "@/contexts/AuthContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import Dashboard from "@/pages/Dashboard"
import Profile from "@/pages/Profile"
import Login from "@/pages/Login"

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
    name: "dashboard",
    element: <Dashboard />,
    initialEntries: ["/dashboard"],
    authValue: baseAuthValue,
  },
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

  const result = await renderWithA11y(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthContext.Provider value={authValue}>
        <LanguageProvider>
          <QueryClientProvider client={queryClient}>
            <>
              <GlobalSkipLink />
              {element}
            </>
          </QueryClientProvider>
        </LanguageProvider>
      </AuthContext.Provider>
    </MemoryRouter>
  )

  queryClient.clear()
  return result
}

describe("global skip link", () => {
  it.each(routes)("renders a single skip link on $name", async (route) => {
    const { container } = await renderRoute(route)
    expect(container.querySelectorAll("a.skip-link")).toHaveLength(1)
  })
})
