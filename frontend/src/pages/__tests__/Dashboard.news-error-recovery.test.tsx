import type { AnchorHTMLAttributes, ReactNode } from "react"
import { act, render } from "@testing-library/react"
import {
  notifyManager,
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { expect, it, vi } from "vitest"

import "@/api/client"
import { newsListQueryKey } from "@/api/hooks/news"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import Dashboard from "../Dashboard"

// Only unrelated widgets and decorative/browser integration are replaced.
// Dashboard, NewsCard, NewsCardList, SkeletonMorph, Button, the query hooks,
// the generated SDK and the Axios error path all remain real.
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: "admin", group_id: null }, loading: false }),
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
  default: (query: string) => query.includes("prefers-reduced-motion"),
}))
vi.mock("@/hooks/useDashboardSchedule", () => ({
  useDashboardSchedule: () => ({ isLoading: true }),
}))
vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => ({ isPending: true }),
}))
vi.mock("@/hooks/useDashboardStories", () => ({
  useDashboardStories: () => ({ data: [], isLoading: false }),
}))
vi.mock("@/hooks/useWeather", () => ({ useWeather: () => ({ data: undefined }) }))
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
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => () => undefined,
}))
vi.mock("framer-motion", async () => {
  const { useState } = await import("react")
  return {
    m: {
      div: ({ children, className }: { children?: ReactNode; className?: string }) => (
        <div className={className}>{children}</div>
      ),
    },
    useAnimationControls: () => {
      const [controls] = useState(() => ({
        set: () => undefined,
        start: () => Promise.resolve(),
        stop: () => undefined,
      }))
      return controls
    },
  }
})

it("keeps exhausted dashboard news requests stopped when revealing the card", async () => {
  const oldAuth = useAuthStore.getState()
  const oldOnline = onlineManager.isOnline()
  const notifications: Array<() => void> = []
  const pendingWaits = new Set<() => void>()
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        retryDelay: 0,
        gcTime: Infinity,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    },
  })
  const queryKey = newsListQueryKey({ language: "en", limit: 4 })
  const state = () => client.getQueryState(queryKey)
  let view: ReturnType<typeof render> | undefined
  let unsubscribe = () => {}
  let releaseUnexpectedResponse!: () => void
  const unexpectedResponse = new Promise<void>((resolve) => {
    releaseUnexpectedResponse = resolve
  })
  let requests = 0
  let terminalErrorObserved = false
  let terminalError: unknown
  let restartedAfterExhaustion = false

  // The timeout diagnoses an absent transition, not a period of quiescence.
  function awaitTerminalError(): Promise<void> {
    if (terminalErrorObserved) return Promise.resolve()
    return new Promise<void>((resolve, reject) => {
      let remove = () => {}
      const dispose = () => {
        clearTimeout(timeout)
        remove()
        pendingWaits.delete(dispose)
      }
      const timeout = setTimeout(() => {
        dispose()
        reject(new Error("Initial dashboard news request did not reach its error state"))
      }, 5000)
      remove = client.getQueryCache().subscribe(() => {
        if (!terminalErrorObserved) return
        dispose()
        resolve()
      })
      pendingWaits.add(dispose)
    })
  }

  async function flushNotifications() {
    for (let round = 0; round < 50; round += 1) {
      const batch = notifications.splice(0)
      await act(async () => {
        for (const callback of batch) callback()
      })
      if (notifications.length === 0) return
    }
    throw new Error("Dashboard news notification queue did not settle")
  }

  try {
    window.localStorage.clear()
    window.sessionStorage.setItem("dash-cascade-done", "1")
    acceptBrowserSessionGeneration()
    useAuthStore.setState({
      user: { ...testUser },
      loading: false,
      pendingMfa: null,
      authOperation: false,
    })
    expect(getConfirmedUserId(useAuthStore.getState())).toBe(testUser.id)
    onlineManager.setOnline(true)
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(true)
    notifyManager.setScheduler((callback) => {
      notifications.push(callback)
    })

    server.use(
      http.get("*/api/v1/news", async ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get("limit")).toBe("4")
        expect(url.searchParams.has("cursor")).toBe(false)
        requests += 1
        if (requests <= 2) {
          return HttpResponse.text("Controlled initial news failure", { status: 500 })
        }
        // A remount must not replenish the exhausted budget. Hold any third
        // request until cleanup so the regression cannot create an HTTP loop.
        await unexpectedResponse
        return HttpResponse.text("Released during cleanup", { status: 500 })
      })
    )
    unsubscribe = client.getQueryCache().subscribe(() => {
      const current = state()
      if (!current) return
      if (current.status === "error" && current.fetchStatus === "idle") {
        terminalErrorObserved = true
        terminalError = current.error
      }
      if (terminalErrorObserved && current.fetchStatus === "fetching") {
        restartedAfterExhaustion = true
      }
    })

    view = render(
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    )
    await awaitTerminalError()
    await flushNotifications()

    expect(terminalError).toMatchObject({ response: { status: 500 } })
    expect(restartedAfterExhaustion).toBe(false)
    expect(requests).toBe(2)
    expect(state()).toMatchObject({ status: "error", fetchStatus: "idle" })
    const region = view.container.querySelector(".vt-dash-news")
    expect(region).toHaveAttribute("aria-busy", "false")
    expect(region?.querySelector(".dash-panel-news")).toBeInTheDocument()
    expect(region?.querySelector(".skeleton-morph-content")).toHaveAttribute("data-loaded", "true")

    // Flush the settled view once more: a new observer must not restart it.
    await flushNotifications()
    expect(restartedAfterExhaustion).toBe(false)
    expect(requests).toBe(2)
    expect(state()).toMatchObject({ status: "error", fetchStatus: "idle" })
  } finally {
    view?.unmount()
    unsubscribe()
    for (const dispose of pendingWaits) dispose()
    try {
      await client.cancelQueries()
    } finally {
      releaseUnexpectedResponse()
      client.clear()
      notifications.length = 0
      notifyManager.setScheduler((callback) => {
        setTimeout(callback, 0)
      })
      vi.restoreAllMocks()
      onlineManager.setOnline(oldOnline)
      useAuthStore.setState({
        user: oldAuth.user,
        loading: oldAuth.loading,
        pendingMfa: oldAuth.pendingMfa,
        authOperation: oldAuth.authOperation,
      })
      window.localStorage.clear()
      window.sessionStorage.clear()
      acceptBrowserSessionGeneration()
    }
  }
})
