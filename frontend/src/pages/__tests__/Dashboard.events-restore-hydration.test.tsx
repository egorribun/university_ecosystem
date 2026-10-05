import { act, type ReactNode } from "react"
import { QueryClient, QueryClientProvider, dehydrate, hydrate } from "@tanstack/react-query"
import { PersistQueryClientProvider, type Persister } from "@tanstack/react-query-persist-client"
import { createRoot, hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  user: null as null | { role: string; group_id: string },
  apiGet: vi.fn(() => new Promise(() => undefined)),
  fetchStories: vi.fn(() => new Promise(() => undefined)),
}))

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, options?: { title?: string }) =>
        options?.title ? `${key}:${options.title}` : key,
    }),
  }
})
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>()
  return {
    ...actual,
    Link: ({
      children,
      to,
      className,
      ...props
    }: {
      children?: ReactNode
      to: string
      className?: string
    }) => (
      <a href={to} className={className} {...props}>
        {children}
      </a>
    ),
    useNavigate: () => () => Promise.resolve(),
  }
})
vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  m: {
    div: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    li: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <li className={className}>{children}</li>
    ),
  },
}))
vi.mock("@/api/client", () => ({ default: { get: state.apiGet } }))
vi.mock("@/api/stories", () => ({ fetchStories: state.fetchStories }))
vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))
vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: state.user, loading: false }),
}))
vi.mock("@/contexts/LanguageContext", () => ({
  getLocaleForLanguage: (language: string) => `${language}-locale`,
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
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => true }))
vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => ({ isLoading: false }),
}))
vi.mock("@/hooks/useDashboardNews", () => ({
  useDashboardNews: () => ({ isPending: false, isLoading: false }),
}))
vi.mock("@/hooks/useWeather", () => ({ useWeather: () => ({ data: undefined }) }))
vi.mock("@/components/dashboard/DashboardHero", () => ({
  DashboardHero: ({ storiesSlot }: { storiesSlot?: ReactNode }) => <section>{storiesSlot}</section>,
}))
vi.mock("@/components/dashboard/DashboardBackdrop", () => ({ DashboardBackdrop: () => null }))
vi.mock("@/components/dashboard/WeatherAmbient", () => ({ WeatherAmbient: () => null }))
vi.mock("@/components/dashboard/ScheduleCard", () => ({ ScheduleCard: () => <div /> }))
vi.mock("@/components/dashboard/NewsCard", () => ({ NewsCard: () => <div /> }))
vi.mock("@/components/dashboard/DashboardSkeleton", () => ({ DashboardSkeleton: () => <div /> }))
vi.mock("@/components/ui/Card", () => ({
  Card: ({ children }: { children: ReactNode }) => <section>{children}</section>,
}))
vi.mock("@/components/ui/Skeleton", () => ({ Skeleton: () => <span /> }))
vi.mock("@/components/error/WidgetErrorBoundary", () => ({
  WidgetErrorBoundary: ({ children }: { children: ReactNode }) => <section>{children}</section>,
}))
vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: () => undefined }),
}))

import { queryClient as browserQueryClient, setQueryCacheIdentity } from "@/app/queryClient"
import Dashboard from "@/pages/Dashboard"
import { EventsCard } from "@/components/dashboard/EventsCard"
import {
  createDashboardEventsQueryOptions,
  dashboardEventsQueryKey,
} from "@/hooks/useDashboardEvents"

function visibleState(html: string) {
  const documentCopy = new DOMParser().parseFromString(html, "text/html")
  const eventRegion = documentCopy.querySelector(".vt-dash-events")
  const storiesRegion = documentCopy.querySelector("[data-fade]")
  const storyList = storiesRegion?.querySelector('[aria-label="aria.storiesList"]')
  const storyButton = storyList?.querySelector("button")
  return {
    eventsBusy: eventRegion?.getAttribute("aria-busy") ?? null,
    eventsSkeleton: Boolean(
      eventRegion?.querySelector('.skeleton-morph-skeleton[data-loaded="false"]')
    ),
    eventsCard: Boolean(eventRegion?.querySelector("h2")),
    eventsContent: eventRegion?.textContent?.includes("Public event") ?? false,
    eventsEmpty: eventRegion?.textContent?.includes("dashboard:events.empty") ?? false,
    storiesLoading: storiesRegion?.getAttribute("aria-busy") ?? null,
    storyCount: String(storyList?.children.length ?? 0),
    storyAccessibleName: storyButton?.getAttribute("aria-label") ?? null,
    storyPreview: storyButton?.getAttribute("title") ?? null,
  }
}

beforeEach(() => {
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true })
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-10-05T10:30:00.000Z"))
  state.user = { role: "student", group_id: "group-1" }
  state.apiGet.mockClear()
  state.fetchStories.mockClear()
  window.sessionStorage.clear()
  window.sessionStorage.setItem("dash-cascade-done", "1")
  setQueryCacheIdentity(null)
  browserQueryClient.clear()
})

afterEach(() => {
  Reflect.deleteProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT")
  vi.unstubAllEnvs()
  vi.useRealTimers()
  setQueryCacheIdentity(null)
  browserQueryClient.clear()
  document.body.replaceChildren()
})

describe("Dashboard events during persisted-query hydration", () => {
  it("compares full Dashboard SSR markup with the persisted provider during cold restore", async () => {
    let finishRestore: (value: undefined) => void = () => undefined
    const restorePromise = new Promise<undefined>((resolve) => {
      finishRestore = resolve
    })
    const persister: Persister = {
      persistClient: async () => undefined,
      restoreClient: () => restorePromise,
      removeClient: async () => undefined,
    }
    const makeClient = () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, gcTime: Infinity },
          mutations: { retry: false },
        },
      })
    const serverClient = makeClient()
    const browserClient = makeClient()
    const recoverableErrors: unknown[] = []
    let root: Root | undefined
    let container: HTMLDivElement | undefined

    try {
      state.user = { role: "student", group_id: "group-1" }
      state.apiGet.mockReset().mockRejectedValue(new Error("controlled dashboard events failure"))
      const loaderOutcome = await Promise.allSettled([
        serverClient.ensureQueryData(createDashboardEventsQueryOptions(serverClient)),
      ])
      expect(loaderOutcome[0]?.status).toBe("rejected")
      expect(serverClient.getQueryState(dashboardEventsQueryKey)?.status).toBe("error")

      vi.stubGlobal("window", undefined)
      vi.stubGlobal("sessionStorage", undefined)
      const serverHtml = renderToString(
        <QueryClientProvider client={serverClient}>
          <Dashboard />
        </QueryClientProvider>
      )
      vi.unstubAllGlobals()
      const serverVisibleState = visibleState(serverHtml)
      const dehydratedState = dehydrate(serverClient)
      expect(
        dehydratedState.queries.some(
          (query) => JSON.stringify(query.queryKey) === JSON.stringify(dashboardEventsQueryKey)
        )
      ).toBe(false)
      state.apiGet.mockClear()

      container = document.createElement("div")
      container.innerHTML = serverHtml
      document.body.append(container)
      hydrate(browserClient, dehydratedState)

      await act(async () => {
        Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", {
          value: true,
          configurable: true,
        })
        root = hydrateRoot(
          container as HTMLDivElement,
          <PersistQueryClientProvider
            client={browserClient}
            persistOptions={{ persister, maxAge: 60_000, buster: "full-dashboard-events-probe" }}
          >
            <Dashboard />
          </PersistQueryClientProvider>,
          { onRecoverableError: (error) => recoverableErrors.push(error) }
        )
        await Promise.resolve()
      })

      const clientVisibleState = visibleState(container.innerHTML)
      expect(serverVisibleState).toMatchObject({
        eventsBusy: "true",
        eventsSkeleton: true,
        eventsCard: false,
      })
      expect(clientVisibleState).toEqual(serverVisibleState)
      expect(browserClient.getQueryState(dashboardEventsQueryKey)).toMatchObject({
        status: "pending",
        fetchStatus: "idle",
      })
      expect(recoverableErrors).toHaveLength(0)
      expect(clientVisibleState.storiesLoading).toBe(serverVisibleState.storiesLoading)
      expect(clientVisibleState.storyCount).toBe(serverVisibleState.storyCount)
      expect(state.apiGet).not.toHaveBeenCalled()

      state.apiGet.mockClear().mockResolvedValue({ status: 200, data: { items: [] } })
      await act(async () => {
        finishRestore(undefined)
        await Promise.resolve()
        await Promise.resolve()
      })
      await act(async () => {
        await vi.waitFor(() => {
          expect(browserClient.getQueryState(dashboardEventsQueryKey)?.status).toBe("success")
          expect(browserClient.getQueryState(dashboardEventsQueryKey)?.fetchStatus).toBe("idle")
        })
      })
      const afterEmptyState = visibleState(container.innerHTML)
      expect(state.apiGet).toHaveBeenCalledOnce()
      expect(afterEmptyState.eventsBusy).toBe("false")
      expect(afterEmptyState.eventsCard).toBe(true)
      expect(afterEmptyState.eventsEmpty).toBe(true)
      expect(recoverableErrors).toHaveLength(0)
    } finally {
      finishRestore(undefined)
      if (root) await act(async () => root?.unmount())
      container?.remove()
      serverClient.clear()
      browserClient.clear()
    }
  })

  it("renders the ordinary empty state after an events request settles with an error", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
    })
    const container = document.createElement("div")
    const root = createRoot(container)
    state.apiGet.mockReset().mockRejectedValue(new Error("controlled dashboard events failure"))
    state.user = { role: "student", group_id: "group-1" }

    try {
      await act(async () => {
        root.render(
          <QueryClientProvider client={client}>
            <EventsCard />
          </QueryClientProvider>
        )
      })
      await act(async () => {
        await vi.waitFor(() => {
          expect(client.getQueryState(dashboardEventsQueryKey)?.status).toBe("error")
          expect(client.getQueryState(dashboardEventsQueryKey)?.fetchStatus).toBe("idle")
        })
      })
      expect(state.apiGet).toHaveBeenCalledOnce()
      expect(container.textContent).toContain("dashboard:events.empty")
      expect(container.querySelector('[role="presentation"]')).toBeNull()
    } finally {
      await act(async () => root.unmount())
      client.clear()
    }
  })
})
