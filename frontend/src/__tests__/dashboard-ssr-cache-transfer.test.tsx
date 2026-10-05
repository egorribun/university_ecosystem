import { act, type ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { hydrateRoot, type Root } from "react-dom/client"
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
vi.mock("@/hooks/useDashboardNews", () => ({ useDashboardNews: () => ({ isLoading: false }) }))
vi.mock("@/hooks/useWeather", () => ({ useWeather: () => ({ data: undefined }) }))
vi.mock("@/components/dashboard/DashboardHero", () => ({
  DashboardHero: ({ storiesSlot }: { storiesSlot?: ReactNode }) => <section>{storiesSlot}</section>,
}))
vi.mock("@/components/dashboard/DashboardBackdrop", () => ({ DashboardBackdrop: () => null }))
vi.mock("@/components/dashboard/WeatherAmbient", () => ({ WeatherAmbient: () => null }))
vi.mock("@/components/dashboard/ScheduleCard", () => ({ ScheduleCard: () => <div /> }))
vi.mock("@/components/dashboard/NewsCard", () => ({ NewsCard: () => <div /> }))
vi.mock("@/components/dashboard/DashboardSkeleton", () => ({ DashboardSkeleton: () => <div /> }))
vi.mock("@/components/ui/SkeletonMorph", () => ({
  SkeletonMorph: ({
    loaded,
    skeleton,
    children,
  }: {
    loaded: boolean
    skeleton: ReactNode
    children: ReactNode
  }) => (loaded ? children : <div data-testid="widget-skeleton">{skeleton}</div>),
}))
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
import { dashboardEventsQueryKey } from "@/hooks/useDashboardEvents"
import { dashboardStoriesQueryKey } from "@/hooks/useDashboardStories"
import { getRouter, type RouterContext } from "../router"

type SsrAuthGetter = (() => RouterContext["auth"] | undefined) | undefined

declare global {
  var __ssrAuthGetter__: SsrAuthGetter
}

const createEventPayload = () => {
  const startsAt = new Date("2026-10-05T10:00:00.000Z")
  const endsAt = new Date(startsAt.getTime() + 60 * 60_000)
  return {
    items: [
      {
        created_at: "2026-10-01T00:00:00.000Z",
        created_by: "private-event-owner",
        ends_at: endsAt.toISOString(),
        id: "public-event",
        is_active: true,
        is_registered: true,
        location: null,
        my_qr_token: "private-attendance-token",
        starts_at: startsAt.toISOString(),
        title: "Public event",
      },
    ],
  }
}

const storyPayload = [
  {
    id: "public-story",
    created_at: "2026-10-01T00:00:00.000Z",
    expires_at: "2026-10-31T23:59:59.000Z",
    is_active: true,
    published_at: "2026-10-01T00:00:00.000Z",
    short_text: "Public preview",
    title: "Public story",
    cover_url: null,
    cover_url_optimized: "https://images.example/public-story.webp",
    cta_url: "https://app.example/stories/public-story",
    created_by: "private-story-owner",
    short_text_en: "Private translation",
    title_en: "Private translated title",
  },
]

function visibleState(html: string) {
  const documentCopy = new DOMParser().parseFromString(html, "text/html")
  const eventRegion = documentCopy.querySelector(".vt-dash-events")
  const storiesRegion = documentCopy.querySelector("[data-fade]")
  const storyList = storiesRegion?.querySelector('[aria-label="aria.storiesList"]')
  const storyButton = storyList?.querySelector("button")
  return {
    eventsBusy: eventRegion?.getAttribute("aria-busy") ?? null,
    eventsSkeleton: Boolean(eventRegion?.querySelector('[data-testid="widget-skeleton"]')),
    eventsCard: Boolean(eventRegion?.querySelector("h2")),
    eventsContent: eventRegion?.textContent?.includes("Public event") ?? false,
    storiesLoading: storiesRegion?.getAttribute("aria-busy") ?? null,
    storyCount: String(storyList?.children.length ?? 0),
    storyAccessibleName: storyButton?.getAttribute("aria-label") ?? null,
    storyPreview: storyButton?.getAttribute("title") ?? null,
  }
}

async function hydrateDashboard(client: QueryClient, html: string) {
  const container = document.createElement("div")
  container.innerHTML = html
  document.body.appendChild(container)
  let recoverableErrors = 0
  let root: Root | undefined
  await act(async () => {
    root = hydrateRoot(
      container,
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>,
      {
        onRecoverableError: () => {
          recoverableErrors += 1
        },
      }
    )
    await Promise.resolve()
  })
  const hydratedState = visibleState(container.innerHTML)
  await act(async () => root?.unmount())
  container.remove()
  return { hydratedState, recoverableErrors }
}

beforeEach(() => {
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
  globalThis.__ssrAuthGetter__ = undefined
  vi.unstubAllEnvs()
  vi.useRealTimers()
  setQueryCacheIdentity(null)
  browserQueryClient.clear()
  document.body.replaceChildren()
})

describe("Dashboard SSR query transfer", () => {
  it("hydrates the same public dashboard state from the router cache before owner confirmation", async () => {
    const ssrAuth: RouterContext["auth"] = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => ssrAuth
    vi.stubEnv("SSR", true)

    const serverRouter = getRouter()
    const serverClient = serverRouter.options.context.queryClient
    expect(serverRouter.options.context.auth).toEqual(ssrAuth)
    const events = createEventPayload()
    serverClient.setQueryData(dashboardEventsQueryKey, events)
    serverClient.setQueryData(dashboardStoriesQueryKey, storyPayload)

    const serverHtml = renderToString(
      <QueryClientProvider client={serverClient}>
        <Dashboard />
      </QueryClientProvider>
    )
    const serverVisibleState = visibleState(serverHtml)
    const dehydratedState = await serverRouter.options.dehydrate?.()
    if (!dehydratedState) throw new Error("SSR router did not produce a dehydrated state")

    const serializedState = JSON.stringify(dehydratedState)
    expect(serializedState).not.toContain("private-event-owner")
    expect(serializedState).not.toContain("private-attendance-token")
    expect(serializedState).not.toContain("private-story-owner")
    expect(serializedState).not.toContain("Private translation")
    expect(dehydratedState.mutations).toEqual([])

    const freshBrowserClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const freshClientResult = await hydrateDashboard(freshBrowserClient, serverHtml)
    expect(freshClientResult.hydratedState.eventsBusy).toBe("true")
    expect(freshClientResult.hydratedState.eventsSkeleton).toBe(true)
    expect(freshClientResult.hydratedState.storyCount).toBe("0")
    expect(freshClientResult.recoverableErrors).toBeGreaterThan(0)
    freshBrowserClient.clear()
    state.apiGet.mockClear()
    state.fetchStories.mockClear()

    vi.stubEnv("SSR", false)
    globalThis.__ssrAuthGetter__ = undefined
    const browserRouter = getRouter()
    expect(browserRouter.options.context.queryClient).toBe(browserQueryClient)
    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toBeUndefined()
    const hydrateTransferredState = browserRouter.options.hydrate as unknown as (
      state: typeof dehydratedState
    ) => void | Promise<void>
    await hydrateTransferredState(dehydratedState)

    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toEqual({
      items: [
        {
          id: "public-event",
          title: "Public event",
          starts_at: events.items[0]?.starts_at,
          location: null,
        },
      ],
    })
    expect(browserQueryClient.getQueryData(dashboardStoriesQueryKey)).toEqual([
      {
        id: "public-story",
        created_at: "2026-10-01T00:00:00.000Z",
        expires_at: "2026-10-31T23:59:59.000Z",
        is_active: true,
        published_at: "2026-10-01T00:00:00.000Z",
        short_text: "Public preview",
        title: "Public story",
        cover_url: null,
        cover_url_optimized: "https://images.example/public-story.webp",
        cta_url: "https://app.example/stories/public-story",
      },
    ])

    const clientResult = await hydrateDashboard(browserQueryClient, serverHtml)
    expect(serverVisibleState).toEqual({
      eventsBusy: "false",
      eventsSkeleton: false,
      eventsCard: true,
      eventsContent: true,
      storiesLoading: "false",
      storyCount: "1",
      storyAccessibleName: "aria.storyItem:Public story",
      storyPreview: "Public preview",
    })
    expect(clientResult.hydratedState).toEqual(serverVisibleState)
    expect(clientResult.recoverableErrors).toBe(0)
    expect(state.apiGet).not.toHaveBeenCalled()
    expect(state.fetchStories).not.toHaveBeenCalled()

    setQueryCacheIdentity("confirmed-owner")
    expect(browserQueryClient.getQueryData(dashboardEventsQueryKey)).toBeUndefined()
    expect(browserQueryClient.getQueryData(dashboardStoriesQueryKey)).toBeUndefined()
  })
})
