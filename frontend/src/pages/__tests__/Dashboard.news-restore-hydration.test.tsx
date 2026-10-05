import type { ReactNode } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { PersistQueryClientProvider, type Persister } from "@tanstack/react-query-persist-client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { testUser } from "@/tests/mocks/handlers"
import Dashboard from "../Dashboard"

const sdk = vi.hoisted(() => ({ newsList: vi.fn() }))

vi.mock("@/api/generated/sdk.gen", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/generated/sdk.gen")>()
  return {
    ...actual,
    newsListApiV1NewsGet: (...args: unknown[]) => sdk.newsList(...args),
  }
})

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: "admin", group_id: null }, loading: false }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  getLocaleForLanguage: (language: string) => (language === "ru" ? "ru-RU" : "en-US"),
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
  default: (query: string) => query.includes("prefers-reduced-motion"),
}))

vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => ({ isLoading: true }),
}))

vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => ({ isLoading: true }),
}))

vi.mock("@/hooks/useDashboardStories", () => ({
  useDashboardStories: () => ({ data: [], isLoading: false }),
}))

vi.mock("@/hooks/useWeather", () => ({ useWeather: () => ({ data: undefined }) }))

vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))
vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/components/dashboard/DashboardHero", () => ({ DashboardHero: () => null }))
vi.mock("@/components/dashboard/DashboardBackdrop", () => ({ DashboardBackdrop: () => null }))
vi.mock("@/components/dashboard/WeatherAmbient", () => ({ WeatherAmbient: () => null }))
vi.mock("@/components/dashboard/ScheduleCard", () => ({ ScheduleCard: () => null }))
vi.mock("@/components/dashboard/EventsCard", () => ({ EventsCard: () => null }))
vi.mock("@/components/stories", () => ({ DashboardStories: () => null }))
vi.mock("@/components/dashboard/NewsCardBackground", () => ({ NewsCardBackground: () => null }))
vi.mock("@/components/error/WidgetErrorBoundary", () => ({
  WidgetErrorBoundary: ({ children }: { children: ReactNode }) => children,
}))
vi.mock("@/components/ui/Button", () => ({
  Button: ({
    children,
    "aria-label": ariaLabel,
  }: {
    children: ReactNode
    "aria-label"?: string
  }) => (
    <button type="button" aria-label={ariaLabel}>
      {children}
    </button>
  ),
}))
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: ReactNode }) => <a href="/news">{children}</a>,
  useNavigate: () => () => undefined,
}))
vi.mock("framer-motion", () => ({ m: { div: "div" } }))

const article = {
  id: "news-hydration-item",
  title: "Hydrated news item",
  content: "The real news query resolved after the owner was confirmed.",
  created_at: "2026-10-05T08:00:00.000Z",
}

const response = {
  status: 200,
  data: {
    items: [article],
    total: 1,
    limit: 4,
    cursor: null,
    next_cursor: null,
    has_more: false,
  },
}

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  })

describe("Dashboard news during persisted-query hydration", () => {
  beforeEach(() => {
    window.localStorage.clear()
    acceptBrowserSessionGeneration()
    useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
  })

  afterEach(() => {
    useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
    vi.unstubAllGlobals()
    if (typeof window !== "undefined") window.sessionStorage.clear()
    if (typeof window !== "undefined") window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it("keeps the SSR news skeleton through cold persistence restore, then displays the confirmed owner's result", async () => {
    let finishRestore!: (value: undefined) => void
    const restorePromise = new Promise<undefined>((resolve) => {
      finishRestore = () => resolve(undefined)
    })
    let finishRequest!: (value: typeof response) => void
    const requestPromise = new Promise<typeof response>((resolve) => {
      finishRequest = resolve
    })
    sdk.newsList.mockReset().mockReturnValue(requestPromise)

    const serverClient = makeQueryClient()
    const browserClient = makeQueryClient()
    const persister: Persister = {
      persistClient: async () => undefined,
      restoreClient: () => restorePromise,
      removeClient: async () => undefined,
    }
    const recoverableErrors: unknown[] = []
    let root: Root | undefined
    let container: HTMLDivElement | undefined

    try {
      vi.stubGlobal("window", undefined)
      vi.stubGlobal("sessionStorage", undefined)
      const serverMarkup = renderToString(
        <QueryClientProvider client={serverClient}>
          <Dashboard />
        </QueryClientProvider>
      )
      vi.unstubAllGlobals()
      window.sessionStorage.setItem("dash-cascade-done", "1")
      container = document.createElement("div")
      container.innerHTML = serverMarkup
      document.body.append(container)
      const readNewsShape = (element: Element) => {
        const section = element.querySelector(".vt-dash-news")
        return {
          sectionFound: Boolean(section),
          sectionBusy: section?.getAttribute("aria-busy"),
          skeletonLoaded: section
            ?.querySelector(".skeleton-morph-skeleton")
            ?.getAttribute("data-loaded"),
          contentLoaded: section
            ?.querySelector(".skeleton-morph-content")
            ?.getAttribute("data-loaded"),
          newsCardFound: Boolean(section?.querySelector(".dash-panel-news")),
        }
      }
      const serverNewsShape = readNewsShape(container)

      await act(async () => {
        root = hydrateRoot(
          container as HTMLDivElement,
          <PersistQueryClientProvider
            client={browserClient}
            persistOptions={{ persister, maxAge: 60_000, buster: "dashboard-news-hydration" }}
          >
            <Dashboard />
          </PersistQueryClientProvider>,
          { onRecoverableError: (error) => recoverableErrors.push(error) }
        )
        await Promise.resolve()
      })

      expect(serverNewsShape).toEqual({
        sectionFound: true,
        sectionBusy: "true",
        skeletonLoaded: "false",
        contentLoaded: "false",
        newsCardFound: false,
      })
      expect(recoverableErrors).toHaveLength(0)
      expect(
        container
          .querySelector(".vt-dash-news .skeleton-morph-content")
          ?.getAttribute("data-loaded")
      ).toBe("false")
      expect(container.querySelector(".vt-dash-news .dash-panel-news")).toBeNull()

      await act(async () => {
        finishRestore(undefined)
        await Promise.resolve()
      })
      await act(async () => {
        acceptBrowserSessionGeneration()
        invalidateSessionEpoch()
        useAuthStore.setState({
          user: { ...testUser, role: "student" },
          loading: false,
          pendingMfa: null,
          authOperation: false,
        })
      })
      expect(getConfirmedUserId(useAuthStore.getState())).toBe(testUser.id)
      await waitFor(() => expect(sdk.newsList).toHaveBeenCalledTimes(1))

      await act(async () => {
        finishRequest(response)
        await Promise.resolve()
      })
      await waitFor(() => expect(container?.textContent).toContain(article.title))
    } finally {
      finishRestore(undefined)
      finishRequest(response)
      if (root) {
        await act(async () => root?.unmount())
      }
      container?.remove()
      serverClient.clear()
      browserClient.clear()
    }
  })
})
