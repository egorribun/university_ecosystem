import { randomUUID } from "node:crypto"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClientProvider } from "@tanstack/react-query"
import {
  createBrowserHistory,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  type AnyRouter,
} from "@tanstack/react-router"
import { LazyMotion, domAnimation } from "framer-motion"
import { renderToString } from "react-dom/server"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AppShellProvider } from "@/contexts/AppShellContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import i18n from "@/i18n/config"
import { createTestQueryClient, renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { server } from "@/tests/mocks/server"
import ResetPassword from "../ResetPassword"
const typedValue = "Password123!"

const tAuth = (key: string) => i18n.t("auth:" + key)
type ResetTestRouter = ReturnType<typeof createRouter>
type BeforeRender = (router: Pick<ResetTestRouter, "navigate">) => void

function observeNavigationPromises(promises: Promise<unknown>[]): BeforeRender {
  return (candidate) => {
    const realNavigate = candidate.navigate.bind(candidate)
    vi.spyOn(candidate, "navigate").mockImplementation((options) => {
      const migration = realNavigate(options)
      promises.push(migration)
      return migration
    })
  }
}

async function waitForSettledMigration(getSearch: () => unknown, promises: Promise<unknown>[]) {
  await waitFor(() => expect(getSearch()).not.toHaveProperty("token"))
  const migrations = promises.splice(0)
  expect(migrations).toHaveLength(1)
  await act(async () => {
    await Promise.all(migrations)
  })
}

function interceptResetRequests(payloads: unknown[]) {
  server.use(
    http.post("*/password/reset", async ({ request }) => {
      payloads.push(await request.json())
      return HttpResponse.json({ ok: true })
    })
  )
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("", { status: 200 }))
}

async function submitValidPassword() {
  const user = userEvent.setup()
  await user.type(
    screen.getByLabelText((content) => content.startsWith(tAuth("fields.password"))),
    "Password123!"
  )
  await user.type(
    screen.getByLabelText((content) => content.startsWith(tAuth("fields.confirmPassword"))),
    "Password123!"
  )
  await user.click(screen.getByRole("button", { name: tAuth("reset.saveButton") }))
  await screen.findByText(tAuth("reset.successTitle"))
}

const RESET_TOKEN_TTL_MS = 45 * 60 * 1000
const LONG_TIMER_THRESHOLD_MS = 50_000
const realDateNow = Date.now.bind(Date)

type CapturedLongTimer = {
  id: number
  delay: number
  scheduledAt: number
  cleared: boolean
  fired: boolean
  callback: () => void
}

let testRunId = ""
let previousLocalStorage: Array<[string, string]> = []
let capturedTimers: CapturedLongTimer[] = []
let nextCapturedTimerId = 1_000_000
const cleanupCallbacks: Array<() => void> = []

const makeTestToken = (purpose: string) => purpose + "-" + testRunId

async function renderResetWithCleanup(initialPath: string) {
  const rendered = await renderWithRouter({
    ui: ResetPassword,
    path: "/reset",
    initialPath,
    authProvider: false,
  })
  cleanupCallbacks.push(() => rendered.router.history.destroy())
  cleanupCallbacks.push(() => rendered.queryClient.clear())
  return rendered
}

function createResetRouteTree() {
  const rootRoute = createRootRoute({ component: Outlet })
  const resetRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/reset",
    component: ResetPassword,
  })
  return rootRoute.addChildren([resetRoute])
}

function renderResetRouter<TRouter extends AnyRouter>(
  router: TRouter,
  queryClient: ReturnType<typeof createTestQueryClient>
) {
  render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <LazyMotion features={domAnimation}>
          <AppShellProvider>
            <RouterProvider router={router} />
          </AppShellProvider>
        </LazyMotion>
      </LanguageProvider>
    </QueryClientProvider>
  )
}

async function renderWithBrowserHistory(
  history: ReturnType<typeof createBrowserHistory>,
  beforeRender?: BeforeRender
) {
  const router = createRouter({
    routeTree: createResetRouteTree(),
    history,
  })
  const queryClient = createTestQueryClient()
  try {
    await router.load()
    beforeRender?.(router)
    renderResetRouter(router, queryClient)
    return { router, queryClient }
  } catch (error) {
    queryClient.clear()
    throw error
  }
}

async function renderWithMemoryHistory(initialPath: string, beforeRender?: BeforeRender) {
  const router = createRouter({
    routeTree: createResetRouteTree(),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })
  const queryClient = createTestQueryClient()
  try {
    await router.load()
    beforeRender?.(router)
    renderResetRouter(router, queryClient)
    cleanupCallbacks.push(() => router.history.destroy())
    cleanupCallbacks.push(() => queryClient.clear())
    return { router, queryClient }
  } catch (error) {
    router.history.destroy()
    queryClient.clear()
    throw error
  }
}

describe("ResetPassword legacy cache snapshots", () => {
  beforeEach(() => {
    const keys = Array.from({ length: localStorage.length }, (_, index) =>
      localStorage.key(index)
    ).filter((key): key is string => key !== null)
    previousLocalStorage = keys.map((key): [string, string] => [
      key,
      localStorage.getItem(key) ?? "",
    ])
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
    testRunId = randomUUID()
    capturedTimers = []
    cleanupCallbacks.length = 0

    const browserTimers: Pick<Window, "setTimeout" | "clearTimeout"> = window
    const originalSetTimeout = browserTimers.setTimeout.bind(browserTimers)
    const originalClearTimeout = browserTimers.clearTimeout.bind(browserTimers)
    vi.spyOn(browserTimers, "setTimeout").mockImplementation((handler, timeout, ...args) => {
      const delay = Number(timeout ?? 0)
      if (typeof handler === "function" && delay >= LONG_TIMER_THRESHOLD_MS) {
        const timer: CapturedLongTimer = {
          id: nextCapturedTimerId++,
          delay,
          scheduledAt: Date.now(),
          cleared: false,
          fired: false,
          callback: () => {},
        }
        timer.callback = () => {
          if (timer.fired) return
          timer.fired = true
          Reflect.apply(handler, window, args)
        }
        capturedTimers.push(timer)
        return timer.id
      }
      return originalSetTimeout(handler, timeout, ...args)
    })
    vi.spyOn(browserTimers, "clearTimeout").mockImplementation((id) => {
      const timer = capturedTimers.find((candidate) => candidate.id === id)
      if (timer) {
        timer.cleared = true
        return
      }
      originalClearTimeout(id)
    })
  })

  afterEach(async () => {
    try {
      cleanup()
      cleanupCallbacks.forEach((dispose) => dispose())
      vi.spyOn(Date, "now").mockReturnValue(realDateNow() + RESET_TOKEN_TTL_MS + 1)
      await act(async () => {
        for (let index = 0; index < capturedTimers.length; index += 1) {
          const timer = capturedTimers[index]
          if (timer && !timer.cleared && !timer.fired) timer.callback()
        }
        await Promise.resolve()
      })
      expect(capturedTimers.every((timer) => timer.cleared || timer.fired)).toBe(true)
    } finally {
      server.resetHandlers()
      localStorage.clear()
      previousLocalStorage.forEach(([key, value]) => localStorage.setItem(key, value))
      vi.restoreAllMocks()
    }
  })

  it("uses the empty external-store snapshot while rendering on the server", async () => {
    const queryClient = createTestQueryClient()
    const router = createRouter({
      routeTree: createResetRouteTree(),
      history: createMemoryHistory({ initialEntries: ["/reset"] }),
    })

    try {
      await router.load()
      const html = renderToString(
        <QueryClientProvider client={queryClient}>
          <LanguageProvider>
            <LazyMotion features={domAnimation}>
              <AppShellProvider>
                <RouterProvider router={router as never} />
              </AppShellProvider>
            </LazyMotion>
          </LanguageProvider>
        </QueryClientProvider>
      )

      expect(html).toContain('name="password"')
      expect(html).not.toContain(tAuth("reset.invalidLink"))
    } finally {
      router.history.destroy()
      queryClient.clear()
    }
  })

  it("retains a cached token and rearms pruning after the wall clock moves backward", async () => {
    const realTimeAtStart = realDateNow()
    let mockedNow: number | null = null
    vi.spyOn(Date, "now").mockImplementation(() => mockedNow ?? realTimeAtStart)

    const { router } = await renderResetWithCleanup(
      "/reset?token=" + encodeURIComponent(makeTestToken("rollback-cache"))
    )

    await screen.findByRole("button", { name: tAuth("reset.saveButton") })
    await waitFor(() => expect(router.state.location.search).not.toHaveProperty("token"))

    const originalDeadlineTimers = capturedTimers.filter(
      (timer) => !timer.cleared && !timer.fired && timer.delay >= 50_000
    )
    expect(originalDeadlineTimers).toHaveLength(2)
    const originalDeadline = Math.max(
      ...originalDeadlineTimers.map((timer) => timer.scheduledAt + timer.delay)
    )

    const rollbackNow =
      Math.min(...originalDeadlineTimers.map((timer) => timer.scheduledAt)) - 60_000
    mockedNow = rollbackNow
    await act(async () => {
      originalDeadlineTimers.forEach((timer) => timer.callback())
      await Promise.resolve()
    })

    expect(screen.queryByText(tAuth("reset.invalidLink"))).not.toBeInTheDocument()
    const rescheduledTimers = capturedTimers.filter((timer) => !timer.cleared && !timer.fired)
    expect(rescheduledTimers).toHaveLength(1)
    expect(rescheduledTimers[0]?.delay).toBe(originalDeadline - rollbackNow)

    mockedNow = originalDeadline
    await act(async () => {
      rescheduledTimers[0]?.callback()
      await Promise.resolve()
    })
    expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument()

    mockedNow = rollbackNow
    expect(screen.getByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
  })

  it.each([true, false])(
    "migrates a legacy-key browser entry with source index present=%s",
    async (hasLegacyIndex) => {
      const previousUrl = window.location.pathname + window.location.search + window.location.hash
      const previousState = window.history.state
      const legacyKey = "legacy-history-key-" + testRunId
      const token = makeTestToken("browser-history-legacy")
      const migrationPromises: Promise<unknown>[] = []
      const payloads: unknown[] = []
      const legacyState: Record<string, unknown> = {
        key: legacyKey,
        ...(hasLegacyIndex ? { __TSR_index: 0 } : {}),
      }
      let history: ReturnType<typeof createBrowserHistory> | undefined
      let mounted: Awaited<ReturnType<typeof renderWithBrowserHistory>> | undefined
      try {
        window.history.replaceState(
          { ...legacyState },
          "",
          "/reset?token=" + encodeURIComponent(token)
        )

        history = createBrowserHistory()
        expect(history.location.state).toMatchObject(legacyState)
        expect(history.location.state.__TSR_index ?? null).toBe(hasLegacyIndex ? 0 : null)
        mounted = await renderWithBrowserHistory(
          history,
          observeNavigationPromises(migrationPromises)
        )

        await screen.findByRole("button", { name: tAuth("reset.saveButton") })
        const mountedRouter = mounted.router
        await waitForSettledMigration(() => mountedRouter.state.location.search, migrationPromises)
        expect(mounted.router.state.location.pathname).toBe("/reset")
        expect(screen.queryByText(tAuth("reset.invalidLink"))).not.toBeInTheDocument()

        interceptResetRequests(payloads)
        await submitValidPassword()
        expect(payloads).toEqual([{ password: typedValue, token }])
      } finally {
        cleanup()
        history?.destroy()
        mounted?.queryClient.clear()
        window.history.replaceState(previousState, "", previousUrl)
      }
    }
  )

  it.each([
    { label: "numeric key", state: { key: 42, __TSR_key: true } },
    { label: "empty key", state: { key: "", __TSR_key: true } },
  ])(
    "treats a browser history entry with a $label and malformed marker as uncached",
    async ({ state }) => {
      const previousUrl = window.location.pathname + window.location.search + window.location.hash
      const previousState = window.history.state
      let history: ReturnType<typeof createBrowserHistory> | undefined
      let mounted: Awaited<ReturnType<typeof renderWithBrowserHistory>> | undefined
      try {
        window.history.replaceState({ ...state }, "", "/reset")

        history = createBrowserHistory()
        expect(history.location.state).toMatchObject(state)
        mounted = await renderWithBrowserHistory(history)
        expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()
      } finally {
        cleanup()
        history?.destroy()
        mounted?.queryClient.clear()
        window.history.replaceState(previousState, "", previousUrl)
      }
    }
  )

  it("retains only the newest 64 migrated history entries", async () => {
    const tokenAt = (index: number) => "bounded-cache-" + testRunId + "-" + index
    const migrationPromises: Promise<unknown>[] = []
    const payloads: unknown[] = []
    const { router } = await renderWithMemoryHistory(
      "/reset?token=" + encodeURIComponent(tokenAt(0)),
      observeNavigationPromises(migrationPromises)
    )

    await screen.findByRole("button", { name: tAuth("reset.saveButton") })
    await waitForSettledMigration(() => router.state.location.search, migrationPromises)
    for (let index = 1; index < 65; index += 1) {
      await act(async () => {
        router.history.push("/reset?token=" + encodeURIComponent(tokenAt(index)), {})
      })
      await waitForSettledMigration(() => router.state.location.search, migrationPromises)
    }

    expect(router.history.location.state.__TSR_index).toBe(64)
    await act(async () => {
      router.history.go(-64)
    })
    expect(router.history.location.state.__TSR_index).toBe(0)
    expect(await screen.findByText(tAuth("reset.invalidLink"))).toBeInTheDocument()

    await act(async () => {
      router.history.go(1)
    })
    await waitFor(() =>
      expect(screen.queryByText(tAuth("reset.invalidLink"))).not.toBeInTheDocument()
    )
    expect(screen.getByRole("button", { name: tAuth("reset.saveButton") })).toBeInTheDocument()

    interceptResetRequests(payloads)
    await submitValidPassword()
    expect(payloads).toEqual([{ password: typedValue, token: tokenAt(1) }])
  })
})
