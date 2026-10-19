import { act, fireEvent, render, screen } from "@testing-library/react"
import {
  notifyManager,
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { http, HttpResponse } from "msw"
import { expect, it, vi } from "vitest"
import * as v from "valibot"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@/features/news/components/NewsHeader", () => ({
  NewsHeader: () => null,
}))
vi.mock("@/features/news/components/NewsFormDialog", () => ({
  NewsFormDialog: () => null,
}))
vi.mock("@/features/news/components/NewsShortcutsOverlay", () => ({
  NewsShortcutsOverlay: () => null,
}))
vi.mock("@/components/news/NewsCard", () => ({
  default: ({ title }: { title: string }) => <article>{title}</article>,
}))

import "@/api/client"
import { newsListQueryKey } from "@/api/hooks/news"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { NewsFeature } from "@/features/news/NewsFeature"
import i18n from "@/i18n/config"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import type { UserState } from "@/types/Auth"

const searchSchema = v.object({
  sort: v.optional(v.picklist(["newest", "popular"])),
})

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function verifyRetryExhaustion() {
  const oldOnline = onlineManager.isOnline()
  const oldAuth = useAuthStore.getState()
  const oldLanguage = i18n.language
  const oldSelectedLanguage = window.__UE_SELECTED_LANG__
  const notifications: Array<() => void> = []
  const pendingWaits = new Set<() => void>()
  const unexpectedResponseGate = deferred()
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
  const queryKey = newsListQueryKey({ language: "en" })
  const state = () => client.getQueryState(queryKey)
  let view: ReturnType<typeof render> | undefined
  let unsubscribe = () => {}
  let manualRetry = false
  let terminalErrorObserved = false
  let restartedAfterExhaustion = false
  let firstPageRequests = 0
  let cursorRequests = 0
  let unexpectedCursorRequests = 0

  // The timeout diagnoses absent transitions, never proves request quiescence.
  function awaitCacheCondition(predicate: () => boolean): Promise<void> {
    if (predicate()) return Promise.resolve()
    return new Promise<void>((resolve, reject) => {
      let remove = () => {}
      const dispose = () => {
        clearTimeout(timeout)
        remove()
        pendingWaits.delete(dispose)
      }
      const timeout = setTimeout(() => {
        dispose()
        reject(new Error("Expected news query transition did not occur"))
      }, 5000)
      remove = client.getQueryCache().subscribe(() => {
        if (!predicate()) return
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
    throw new Error("News notification queue did not settle")
  }

  const article = (id: string, title: string) => ({
    id,
    title,
    content: title,
    created_at: "2026-10-01T10:00:00Z",
    likes_count: 0,
    comments_count: 0,
    is_liked: false,
  })
  const first = article("550e8400-e29b-41d4-a716-446655440101", "First article")
  const second = article("550e8400-e29b-41d4-a716-446655440102", "Recovered article")

  try {
    window.localStorage.clear()
    window.localStorage.setItem("ue:language", "en")
    window.__UE_SELECTED_LANG__ = "en"
    await i18n.changeLanguage("en")
    acceptBrowserSessionGeneration()
    useAuthStore.setState({
      user: { ...testUser } as UserState,
      loading: false,
      pendingMfa: null,
    })
    acceptBrowserSessionGeneration()
    onlineManager.setOnline(true)
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(true)
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
        takeRecords() {
          return []
        }
      }
    )
    notifyManager.setScheduler((callback) => {
      notifications.push(callback)
    })

    server.use(
      http.get("*/api/v1/news", async ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get("limit")).toBe("12")
        const cursor = url.searchParams.get("cursor")
        if (cursor === null) {
          firstPageRequests += 1
          return HttpResponse.json({
            items: [first],
            has_more: true,
            next_cursor: "audit-next",
          })
        }

        expect(cursor).toBe("audit-next")
        cursorRequests += 1
        if (manualRetry) {
          return HttpResponse.json({
            items: [second],
            has_more: false,
            next_cursor: null,
          })
        }
        if (cursorRequests <= 2) {
          return HttpResponse.text("Controlled next-page failure", { status: 500 })
        }

        // Bound the faulty effect: a third request stays pending until cleanup.
        unexpectedCursorRequests += 1
        await unexpectedResponseGate.promise
        return HttpResponse.text("Released during cleanup", { status: 500 })
      })
    )

    unsubscribe = client.getQueryCache().subscribe(() => {
      const current = state()
      if (!current) return
      if (current.status === "error" && current.fetchStatus === "idle") {
        terminalErrorObserved = true
      }
      if (terminalErrorObserved && !manualRetry && current.fetchStatus === "fetching") {
        restartedAfterExhaustion = true
      }
    })

    const rootRoute = createRootRoute()
    const newsRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: "/news",
      validateSearch: (search: Record<string, unknown>) => v.parse(searchSchema, search),
      component: NewsFeature,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([newsRoute]),
      history: createMemoryHistory({ initialEntries: ["/news?sort=popular"] }),
    })
    await router.load()
    view = render(
      <QueryClientProvider client={client}>
        <LanguageProvider>
          <RouterProvider router={router as never} />
        </LanguageProvider>
      </QueryClientProvider>
    )

    await awaitCacheCondition(() => state()?.status === "success")
    await flushNotifications()
    await awaitCacheCondition(() => terminalErrorObserved)
    await flushNotifications()

    expect(firstPageRequests).toBe(1)
    expect(state()?.error).toMatchObject({ response: { status: 500 } })
    expect(restartedAfterExhaustion).toBe(false)
    expect(cursorRequests).toBe(2)
    expect(unexpectedCursorRequests).toBe(0)
    expect(state()).toMatchObject({ status: "error", fetchStatus: "idle" })
    expect(screen.getByText("First article")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toBeInTheDocument()

    manualRetry = true
    fireEvent.click(screen.getByRole("button", { name: i18n.t("common:statuses.tryAgain") }))
    await awaitCacheCondition(() => firstPageRequests === 2 && state()?.status === "success")
    await flushNotifications()
    await awaitCacheCondition(() => {
      const data = client.getQueryData<{ pages: unknown[] }>(queryKey)
      return data?.pages.length === 2 && state()?.fetchStatus === "idle"
    })
    await flushNotifications()

    expect(cursorRequests).toBe(3)
    expect(screen.getByText("First article")).toBeInTheDocument()
    expect(screen.getByText("Recovered article")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(state()).toMatchObject({ status: "success", fetchStatus: "idle" })
    expect(client.getQueryData(queryKey)).toMatchObject({
      pages: [
        { next_cursor: "audit-next" },
        { next_cursor: null, has_more: false },
      ],
    })
  } finally {
    view?.unmount()
    unsubscribe()
    for (const dispose of pendingWaits) dispose()
    try {
      await client.cancelQueries()
    } finally {
      unexpectedResponseGate.resolve()
      client.clear()
      notifications.length = 0
      notifyManager.setScheduler((callback) => {
        setTimeout(callback, 0)
      })
      vi.unstubAllGlobals()
      vi.restoreAllMocks()
      onlineManager.setOnline(oldOnline)
      useAuthStore.setState({
        user: oldAuth.user,
        loading: oldAuth.loading,
        pendingMfa: oldAuth.pendingMfa,
      })
      window.localStorage.clear()
      acceptBrowserSessionGeneration()
      await i18n.changeLanguage(oldLanguage)
      if (oldSelectedLanguage === undefined) delete window.__UE_SELECTED_LANG__
      else window.__UE_SELECTED_LANG__ = oldSelectedLanguage
    }
  }
}

it(
  "stops automatic pagination after retry exhaustion and permits explicit retry",
  verifyRetryExhaustion,
  20000
)
