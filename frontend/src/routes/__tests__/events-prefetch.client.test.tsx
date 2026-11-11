import { QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import { render, screen, cleanup } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { RouterContext } from "@/router"
import type { UserState } from "@/types/Auth"
type RouterModule = typeof import("@tanstack/react-router")
const sdk = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: sdk.list,
  myEventsApiV1EventsMyGet: vi.fn(),
  myEventsPageApiV1EventsMyPageGet: vi.fn(),
}))
vi.mock("@/pages/Events", () => ({ default: () => null }))
vi.mock("@/contexts/AuthContext", async () => {
  const { useAuthStore } = await import("@/stores/useAuthStore")
  return { useAuth: () => ({ user: useAuthStore((state) => state.user) }) }
})
vi.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: "en" }) }))
vi.mock("@/contexts/CampusTimezoneContext", () => ({ useCampusTimezone: () => "Europe/Moscow" }))
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<RouterModule>()
  return {
    ...actual,
    useSearch: () => ({}),
    useNavigate: () => () => undefined,
  }
})
vi.mock("@/hooks/useEventsKeyboardNav", () => ({
  useEventsKeyboardNav: () => ({ activeIndex: -1, registerRef: () => undefined }),
}))
vi.mock("@/hooks/ui/useStableListHeight", () => ({ useStableListHeight: () => undefined }))
vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => null }))
vi.mock("@/features/events/components/EventsHeader", () => ({ EventsHeader: () => null }))
vi.mock("@/features/events/components/EventsList", () => ({
  EventsList: ({
    isInitialLoading,
    eventsList,
  }: {
    isInitialLoading: boolean
    eventsList: Array<{ id: string; title: string }>
  }) =>
    isInitialLoading ? (
      <p>Loading events</p>
    ) : (
      <section>
        {eventsList.map((event) => (
          <article key={event.id}>{event.title}</article>
        ))}
      </section>
    ),
}))
vi.mock("@/features/events/components/EventFormDialog", () => ({ EventFormDialog: () => null }))
vi.mock("@/features/events/components/EventsShortcutsOverlay", () => ({
  EventsShortcutsOverlay: () => null,
}))
import { EventsFeature } from "@/features/events/EventsFeature"
import { Route } from "../_auth/events.index"
import { createQueryClient } from "@/app/queryClient"
import { useAuthStore } from "@/stores/useAuthStore"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { EVENTS_PAGE_SIZE, eventsListQueryKey } from "@/api/hooks/events"
const filters = {
  language: "en",
  limit: EVENTS_PAGE_SIZE,
  is_active: true,
  order: "starts_at_desc" as const,
}
const earlier = { id: "earlier-event", title: "Earlier event", starts_at: "2026-12-01T09:00:00Z" }
const later = { id: "later-event", title: "Later event", starts_at: "2026-12-15T09:00:00Z" }
const previousAuth = useAuthStore.getState()
const clients: QueryClient[] = []
function client() {
  const value = createQueryClient()
  clients.push(value)
  return value
}
async function load(queryClient: QueryClient) {
  const loader = Route.options.loader as (args: { context: RouterContext }) => Promise<void>
  await loader({
    context: { queryClient, auth: { isAuth: true, user: { role: "student" }, loading: false } },
  })
}
beforeEach(() => {
  vi.stubEnv("SSR", false)
  localStorage.clear()
  acceptBrowserSessionGeneration()
  localStorage.setItem("ue:language", "en")
  useAuthStore.setState({
    user: {
      id: "prefetch-owner",
      email: "prefetch-owner@example.test",
      is_active: true,
    } satisfies NonNullable<UserState>,
    loading: false,
  })
  expect(getConfirmedUserId(useAuthStore.getState())).toBe("prefetch-owner")
  sdk.list.mockReset().mockImplementation(async (options) => ({
    status: 200,
    data: {
      items: options.query.order === "starts_at_desc" ? [later, earlier] : [earlier, later],
      total: 2,
      limit: EVENTS_PAGE_SIZE,
      has_more: false,
      next_cursor: null,
    },
  }))
})
afterEach(() => {
  vi.unstubAllEnvs()
  cleanup()
  clients.forEach((value) => value.clear())
  clients.length = 0
  useAuthStore.setState(previousAuth)
  localStorage.clear()
  acceptBrowserSessionGeneration()
})
it("renders the actual EventsFeature default ordered feed immediately after an owned client loader without another request", async () => {
  const queryClient = client()
  await load(queryClient)
  render(
    <QueryClientProvider client={queryClient}>
      <EventsFeature />
    </QueryClientProvider>
  )
  expect(sdk.list).toHaveBeenCalledTimes(1)
  expect(screen.queryByText("Loading events")).toBeNull()
  expect(screen.getAllByRole("article").map((node) => node.textContent)).toEqual([
    "Later event",
    "Earlier event",
  ])
  expect(sdk.list).toHaveBeenCalledTimes(1)
  expect(sdk.list.mock.calls[0]?.[0]).toMatchObject({
    query: { is_active: true, order: "starts_at_desc", limit: EVENTS_PAGE_SIZE },
  })
  expect(
    queryClient.getQueryData(eventsListQueryKey({ language: "en", limit: EVENTS_PAGE_SIZE }))
  ).toBeUndefined()
})
it("does not fetch or populate private feed data before owner confirmation", async () => {
  useAuthStore.setState({ user: null, loading: true })
  const queryClient = client()
  await load(queryClient)
  expect(sdk.list).not.toHaveBeenCalled()
  expect(queryClient.getQueryData(eventsListQueryKey(filters))).toBeUndefined()
  expect(
    queryClient
      .getQueryCache()
      .findAll()
      .every((query) => query.state.data === undefined)
  ).toBe(true)
})
it("discards an in-flight loader response if account ownership changes", async () => {
  let finish: (response: unknown) => void = () => undefined
  sdk.list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const queryClient = client()
  const loading = load(queryClient)
  expect(sdk.list).toHaveBeenCalledTimes(1)
  useAuthStore.setState({ user: null, loading: false })
  finish({
    status: 200,
    data: { items: [later], total: 1, limit: EVENTS_PAGE_SIZE, has_more: false, next_cursor: null },
  })
  await loading
  expect(queryClient.getQueryData(eventsListQueryKey(filters))).toBeUndefined()
  expect(
    queryClient
      .getQueryCache()
      .findAll()
      .every((query) => query.state.data === undefined)
  ).toBe(true)
})

it("uses the SSR build flag even if a DOM exists in the test host", async () => {
  vi.stubEnv("SSR", true)
  const queryClient = client()
  await load(queryClient)
  expect(sdk.list).not.toHaveBeenCalled()
  expect(queryClient.getQueryCache().findAll()).toEqual([])
})

it.each([
  ["archive", { ...filters, is_active: false }],
  ["upcoming", { ...filters, order: "starts_at_asc" as const }],
  ["popular", { ...filters, order: undefined }],
  ["search", { ...filters, search: "lecture" }],
  ["location", { ...filters, location: "hall" }],
])("does not populate the %s feed with the default page", async (_name, otherFilters) => {
  const queryClient = client()
  const legacyKey = eventsListQueryKey({ language: "en", limit: EVENTS_PAGE_SIZE })
  const legacy = { pages: [{ items: [earlier, later] }], pageParams: [null] }
  queryClient.setQueryData(legacyKey, legacy)
  await load(queryClient)
  expect(queryClient.getQueryData(eventsListQueryKey(otherFilters))).toBeUndefined()
  expect(queryClient.getQueryData(legacyKey)).toEqual(legacy)
  expect(queryClient.getQueryData(eventsListQueryKey(filters))).toMatchObject({
    pages: [{ items: [later, earlier] }],
  })
})

it("resolves a failed best-effort prefetch without publishing successful data", async () => {
  sdk.list.mockRejectedValue(new Error("Backend unavailable"))
  const queryClient = client()
  await expect(load(queryClient)).resolves.toBeUndefined()
  expect(queryClient.getQueryState(eventsListQueryKey(filters))?.status).toBe("error")
  expect(queryClient.getQueryData(eventsListQueryKey(filters))).toBeUndefined()
})

it("discards a response after the same owner moves to another browser session generation", async () => {
  let finish: (response: unknown) => void = () => undefined
  sdk.list.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  // The normal client retries once. Keep that fresh retry unsuccessful so
  // cached data would identify an improperly accepted old-generation response.
  sdk.list.mockRejectedValueOnce(new Error("Fresh retry unavailable"))
  const queryClient = client()
  const loading = load(queryClient)
  expect(sdk.list).toHaveBeenCalledTimes(1)
  localStorage.setItem(
    "ecosystem.session.generation.v1",
    JSON.stringify({ nonce: "new-session-generation", hash: null })
  )
  acceptBrowserSessionGeneration()
  expect(getConfirmedUserId(useAuthStore.getState())).toBe("prefetch-owner")
  finish({
    status: 200,
    data: { items: [later], total: 1, limit: EVENTS_PAGE_SIZE, has_more: false, next_cursor: null },
  })
  await loading
  expect(
    queryClient
      .getQueryCache()
      .findAll()
      .every((query) => query.state.data === undefined)
  ).toBe(true)
})
