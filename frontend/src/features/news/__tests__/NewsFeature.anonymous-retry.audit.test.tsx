import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { onlineManager, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router"
import { http, HttpResponse } from "msw"
import { expect, it, vi } from "vitest"

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
import { anonymousNewsListQueryKey } from "@/api/hooks/news"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { NewsFeature } from "@/features/news/NewsFeature"
import i18n from "@/i18n/config"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { server } from "@/tests/mocks/server"

async function verifyAnonymousRetry() {
  const oldAuth = useAuthStore.getState()
  const oldOnline = onlineManager.isOnline()
  const oldLanguage = i18n.language
  const oldStoredLanguage = window.localStorage.getItem("ue:language")
  const oldSelectedLanguage = window.__UE_SELECTED_LANG__
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    },
  })
  const queryKey = anonymousNewsListQueryKey({ language: "en" })
  let releaseSuccess!: () => void
  const successGate = new Promise<void>((resolve) => {
    releaseSuccess = resolve
  })
  let requests = 0
  let allowSuccess = false
  let observeRetry = false
  let retryInitiated = false
  let unsubscribe = () => {}
  let view: ReturnType<typeof render> | undefined
  const fetchSpy = vi.spyOn(globalThis, "fetch")
  const newsFetches = () =>
    fetchSpy.mock.calls.filter(
      ([input]) => input instanceof URL && input.pathname === "/api/v1/news"
    )

  try {
    window.__UE_SELECTED_LANG__ = "en"
    window.localStorage.setItem("ue:language", "en")
    await i18n.changeLanguage("en")
    acceptBrowserSessionGeneration()
    useAuthStore.setState({ user: null, loading: false, pendingMfa: null })
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

    server.use(
      http.get("*/api/v1/news", async ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get("limit")).toBe("12")
        expect(url.searchParams.get("cursor")).toBeNull()
        requests += 1

        if (!allowSuccess) {
          return HttpResponse.text("Controlled anonymous feed failure", { status: 500 })
        }

        await successGate
        return HttpResponse.json({
          items: [
            {
              id: "550e8400-e29b-41d4-a716-446655440103",
              title: "Recovered public article",
              content: "Public article body",
              created_at: "2026-10-01T10:00:00Z",
              likes_count: 0,
              comments_count: 0,
              is_liked: false,
            },
          ],
          has_more: false,
          next_cursor: null,
        })
      })
    )

    unsubscribe = client.getQueryCache().subscribe((event) => {
      const anonymousQuery = client.getQueryCache().find({ queryKey, exact: true })
      if (
        observeRetry &&
        event.query === anonymousQuery &&
        event.query.state.fetchStatus === "fetching"
      ) {
        retryInitiated = true
      }
    })

    const rootRoute = createRootRoute()
    const newsRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: "/news",
      component: NewsFeature,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([newsRoute]),
      history: createMemoryHistory({ initialEntries: ["/news"] }),
    })
    await router.load()
    view = render(
      <QueryClientProvider client={client}>
        <LanguageProvider>
          <RouterProvider router={router as never} />
        </LanguageProvider>
      </QueryClientProvider>
    )

    await waitFor(
      () => {
        expect(screen.getByRole("alert")).toBeInTheDocument()
        expect(client.getQueryState(queryKey)).toMatchObject({
          status: "error",
          fetchStatus: "idle",
        })
      },
      { timeout: 2000 }
    )
    expect(requests).toBe(1)
    expect(newsFetches()).toHaveLength(1)
    expect(newsFetches()[0]?.[1]).toMatchObject({
      method: "GET",
      mode: "same-origin",
      credentials: "omit",
      cache: "no-store",
    })
    expect(client.getQueryState(queryKey)?.error).toMatchObject({
      message: "News request failed with status 500",
    })

    allowSuccess = true
    observeRetry = true
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: i18n.t("common:statuses.tryAgain") }))
    })

    // Observe actual query work; elapsed time is not the absence-of-retry oracle.
    expect(retryInitiated).toBe(true)
    expect(client.getQueryState(queryKey)?.fetchStatus).toBe("fetching")
    await waitFor(() => expect(requests).toBe(2), { timeout: 2000 })
    expect(newsFetches()).toHaveLength(2)
    expect(newsFetches()[1]?.[1]).toMatchObject({
      credentials: "omit",
      cache: "no-store",
    })

    await act(async () => {
      releaseSuccess()
    })
    await waitFor(
      () => {
        expect(screen.getByText("Recovered public article")).toBeInTheDocument()
        expect(screen.queryByRole("alert")).not.toBeInTheDocument()
        expect(client.getQueryState(queryKey)).toMatchObject({
          status: "success",
          fetchStatus: "idle",
        })
      },
      { timeout: 2000 }
    )
    expect(requests).toBe(2)
  } finally {
    view?.unmount()
    unsubscribe()
    releaseSuccess()
    try {
      await client.cancelQueries()
    } finally {
      client.clear()
      vi.unstubAllGlobals()
      vi.restoreAllMocks()
      onlineManager.setOnline(oldOnline)
      useAuthStore.setState({
        user: oldAuth.user,
        loading: oldAuth.loading,
        pendingMfa: oldAuth.pendingMfa,
      })
      acceptBrowserSessionGeneration()
      if (oldSelectedLanguage === undefined) delete window.__UE_SELECTED_LANG__
      else window.__UE_SELECTED_LANG__ = oldSelectedLanguage
      if (oldStoredLanguage === null) {
        window.localStorage.removeItem("ue:language")
      } else {
        window.localStorage.setItem("ue:language", oldStoredLanguage)
      }
      await i18n.changeLanguage(oldLanguage)
    }
  }
}

it("retries the real anonymous query from the visible Retry button", verifyAnonymousRetry, 10000)
