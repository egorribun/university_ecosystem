/** @vitest-environment node */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { RouterContext } from "@/router"

const sdk = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: sdk.list,
  myEventsApiV1EventsMyGet: vi.fn(),
  myEventsPageApiV1EventsMyPageGet: vi.fn(),
}))
vi.mock("@/pages/Events", () => ({ default: () => null }))
vi.mock("@/routeTree.gen", async () => {
  const { createRootRoute } = await import("@tanstack/react-router")
  return { routeTree: createRootRoute() }
})
import { Route } from "../_auth/events.index"
import { getRouter } from "@/router"
import {
  EVENTS_PAGE_SIZE,
  prefetchEventsListQuery,
  useEventsListQuery,
  eventsListQueryKey,
} from "@/api/hooks/events"

const filters = {
  language: "en",
  limit: EVENTS_PAGE_SIZE,
  is_active: true,
  order: "starts_at_desc" as const,
}
const event = {
  id: "prefetched-event",
  title: "Server-prefetched opening lecture",
  starts_at: "2026-12-15T09:00:00Z",
  ends_at: "2026-12-15T10:00:00Z",
  is_active: true,
}
const clients: QueryClient[] = []
function Feed() {
  const query = useEventsListQuery(filters)
  return query.isPending ? (
    <p>Loading events</p>
  ) : (
    <section>
      {query.events.map((item) => (
        <article key={item.id}>{item.title}</article>
      ))}
    </section>
  )
}
function markup(client: QueryClient) {
  return renderToString(
    <QueryClientProvider client={client}>
      <Feed />
    </QueryClientProvider>
  )
}
function client() {
  const value = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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
  expect(import.meta.env.SSR).toBe(true)
  expect(typeof window).toBe("undefined")
  vi.stubGlobal("localStorage", undefined)
  vi.stubGlobal("__ssrLangGetter__", () => "en")
  sdk.list.mockReset().mockResolvedValue({
    status: 200,
    data: {
      items: [event],
      total: 1,
      limit: EVENTS_PAGE_SIZE,
      has_more: false,
      next_cursor: null,
    },
  })
})
afterEach(() => {
  clients.forEach((value) => value.clear())
  clients.length = 0
  vi.unstubAllGlobals()
})
it("keeps the SSR feed pending without fetching data excluded from client hydration", async () => {
  const queryClient = client()
  await load(queryClient)
  expect(sdk.list).not.toHaveBeenCalled()
  expect(markup(queryClient)).toBe("<p>Loading events</p>")
})
it("shows why matching the default key alone cannot provide safe SSR content transfer", async () => {
  const router = getRouter()
  const queryClient = router.options.context.queryClient
  clients.push(queryClient)
  await prefetchEventsListQuery(queryClient, filters)
  expect(queryClient.getQueryData(eventsListQueryKey(filters))).toMatchObject({
    pages: [{ items: [event] }],
  })
  expect(markup(queryClient)).toBe("<section></section>")
  const transferred = await router.options.dehydrate?.()
  expect(transferred).toEqual({ queries: [], mutations: [] })
  const receivingRouter = getRouter()
  const receiver = receivingRouter.options.context.queryClient
  clients.push(receiver)
  if (receivingRouter.options.hydrate && transferred)
    await receivingRouter.options.hydrate({ queries: transferred.queries, mutations: [] })
  expect(receiver.getQueryData(eventsListQueryKey(filters))).toBeUndefined()
  expect(markup(receiver)).toBe("<p>Loading events</p>")
})
