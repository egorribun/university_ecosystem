import { act, cleanup } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"

import { LanguageProvider } from "@/contexts/LanguageContext"
import i18n from "@/i18n/config"
import { dashboardEventsQueryKey, type DashboardEvent } from "@/hooks/useDashboardEvents"

import { EventsCard } from "../EventsCard"

const EVENT_START = "2026-10-09T15:00:00.000Z"
const FROZEN_NOW = new Date("2026-10-09T08:56:00.000Z")
const MIDNIGHT_EVENT: DashboardEvent = {
  id: "midnight-hydration-event",
  title: "Timezone boundary event",
  starts_at: "2026-10-09T00:30:00.000Z",
  location: "",
}
const MIDNIGHT_FROZEN_NOW = new Date("2026-10-08T23:56:00.000Z")
const SEEDED_EVENT: DashboardEvent = {
  id: "hydration-event",
  title: "Timezone hydration event",
  starts_at: EVENT_START,
  location: "",
}

const queryClients: QueryClient[] = []
let hydratedRoot: Root | undefined
let hydrationContainer: HTMLDivElement | undefined
let previousTimezone: string | undefined
let previousLanguage: string | null = null
let previousSelectedLanguage: typeof window.__UE_SELECTED_LANG__
let previousI18nLanguage = "ru"
let originalWindowDescriptor: PropertyDescriptor | undefined

function createQueryClient(events: DashboardEvent[] = [SEEDED_EVENT]): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { gcTime: Infinity, retry: false } },
  })
  queryClient.setQueryData(dashboardEventsQueryKey, { items: events })
  queryClients.push(queryClient)
  return queryClient
}

function createDashboardTree(queryClient: QueryClient) {
  const rootRoute = createRootRoute({ component: Outlet })
  const dashboardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/dashboard",
    component: EventsCard,
  })
  const eventsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/events",
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([dashboardRoute, eventsRoute]),
    history: createMemoryHistory({ initialEntries: ["/dashboard"] }),
  })

  const tree = (
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <RouterProvider router={router as never} />
      </LanguageProvider>
    </QueryClientProvider>
  )

  return { router, tree }
}

describe("EventsCard SSR hydration across host timezones", () => {
  afterEach(async () => {
    if (hydratedRoot) {
      await act(async () => hydratedRoot?.unmount())
      hydratedRoot = undefined
    }
    cleanup()
    hydrationContainer?.remove()
    hydrationContainer = undefined

    queryClients.splice(0).forEach((client) => client.clear())
    vi.useRealTimers()

    if (previousTimezone === undefined) delete process.env.TZ
    else process.env.TZ = previousTimezone
    previousTimezone = undefined

    if (typeof window !== "undefined") {
      if (previousLanguage === null) window.localStorage.removeItem("ue:language")
      else window.localStorage.setItem("ue:language", previousLanguage)
      if (previousSelectedLanguage === undefined) delete window.__UE_SELECTED_LANG__
      else window.__UE_SELECTED_LANG__ = previousSelectedLanguage
      document.cookie = "ue:language=; Max-Age=0; Path=/"
    }
    await i18n.changeLanguage(previousI18nLanguage)
  })

  it("uses one event-time string for the server and first browser render, then keeps local time", async () => {
    previousTimezone = process.env.TZ
    previousLanguage = window.localStorage.getItem("ue:language")
    previousSelectedLanguage = window.__UE_SELECTED_LANG__
    previousI18nLanguage = i18n.language
    originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window")

    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(FROZEN_NOW)
    window.localStorage.setItem("ue:language", "ru")
    window.__UE_SELECTED_LANG__ = "ru"
    await i18n.changeLanguage("ru")

    process.env.TZ = "UTC"
    const serverSetup = createDashboardTree(createQueryClient())
    await serverSetup.router.load()

    let serverMarkup: string
    try {
      Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
      serverMarkup = renderToString(serverSetup.tree)
    } finally {
      if (originalWindowDescriptor) {
        Object.defineProperty(globalThis, "window", originalWindowDescriptor)
      }
    }

    expect(serverMarkup).toContain("15:00")

    process.env.TZ = "Europe/Istanbul"
    const browserSetup = createDashboardTree(createQueryClient())
    await browserSetup.router.load()

    hydrationContainer = document.createElement("div")
    hydrationContainer.innerHTML = serverMarkup
    document.body.append(hydrationContainer)
    const recoverableErrors: unknown[] = []

    await act(async () => {
      hydratedRoot = hydrateRoot(hydrationContainer as HTMLDivElement, browserSetup.tree, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
    })

    expect(recoverableErrors).toEqual([])
    expect(hydrationContainer.textContent).toContain("18:00")
    expect(hydrationContainer.querySelector('[aria-label^="Опубликовано:"]')).toHaveAttribute(
      "aria-label",
      expect.stringContaining("09 октября 2026 г. в 18:00")
    )
  })

  it("keeps the server and first client event-day filter aligned across local midnight", async () => {
    previousTimezone = process.env.TZ
    previousLanguage = window.localStorage.getItem("ue:language")
    previousSelectedLanguage = window.__UE_SELECTED_LANG__
    previousI18nLanguage = i18n.language
    originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window")

    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(MIDNIGHT_FROZEN_NOW)
    window.localStorage.setItem("ue:language", "ru")
    window.__UE_SELECTED_LANG__ = "ru"
    await i18n.changeLanguage("ru")

    process.env.TZ = "UTC"
    const serverSetup = createDashboardTree(createQueryClient([MIDNIGHT_EVENT]))
    await serverSetup.router.load()

    let serverMarkup: string
    try {
      Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
      serverMarkup = renderToString(serverSetup.tree)
    } finally {
      if (originalWindowDescriptor) {
        Object.defineProperty(globalThis, "window", originalWindowDescriptor)
      }
    }

    expect(serverMarkup).not.toContain(MIDNIGHT_EVENT.title)

    process.env.TZ = "Europe/Istanbul"
    const browserSetup = createDashboardTree(createQueryClient([MIDNIGHT_EVENT]))
    await browserSetup.router.load()

    hydrationContainer = document.createElement("div")
    hydrationContainer.innerHTML = serverMarkup
    document.body.append(hydrationContainer)
    const recoverableErrors: unknown[] = []

    await act(async () => {
      hydratedRoot = hydrateRoot(hydrationContainer as HTMLDivElement, browserSetup.tree, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
    })

    expect(recoverableErrors).toEqual([])
    expect(hydrationContainer.textContent).toContain(MIDNIGHT_EVENT.title)
  })
})
