import { act } from "react"
import { waitFor } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { hydrateRoot, type Root } from "react-dom/client"
import { QueryClient, QueryClientProvider, dehydrate, hydrate } from "@tanstack/react-query"
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
const sdk = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock("@/contexts/AuthContext", async () => {
  const { useAuthStore } = await import("@/stores/useAuthStore")
  return { useAuth: () => ({ user: useAuthStore((state) => state.user) }) }
})
vi.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: "en" }) }))
vi.mock("@/contexts/CampusTimezoneContext", () => ({ useCampusTimezone: () => "Europe/Moscow" }))
vi.mock("@tanstack/react-router", () => ({
  useSearch: () => ({}),
  useNavigate: () => () => undefined,
}))
vi.mock("@/api/client", () => ({ resetEtagCache: () => undefined }))
vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: sdk.list,
  myEventsApiV1EventsMyGet: () => new Promise(() => undefined),
  myEventsPageApiV1EventsMyPageGet: () => new Promise(() => undefined),
}))
vi.mock("@/hooks/useEventsKeyboardNav", () => ({
  useEventsKeyboardNav: () => ({ activeIndex: -1, registerRef: () => undefined }),
}))
vi.mock("@/hooks/ui/useStableListHeight", () => ({ useStableListHeight: () => undefined }))
vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => null }))
vi.mock("../components/EventsHeader", () => ({ EventsHeader: () => null }))
vi.mock("../components/EventsList", () => ({
  EventsList: ({ isInitialLoading }: { isInitialLoading: boolean }) =>
    isInitialLoading ? (
      <div data-testid="loading">Loading</div>
    ) : (
      <section data-testid="empty">Empty</section>
    ),
}))
vi.mock("../components/EventFormDialog", () => ({ EventFormDialog: () => null }))
vi.mock("../components/EventsShortcutsOverlay", () => ({ EventsShortcutsOverlay: () => null }))
import { EventsFeature } from "../EventsFeature"
import { eventsListQueryKey } from "@/api/hooks/events"
import { useAuthStore } from "@/stores/useAuthStore"
import { getConfirmedUserId } from "@/stores/authIdentity"
import type { UserState } from "@/types/Auth"
const previousAuth = useAuthStore.getState()
beforeEach(() => {
  useAuthStore.setState({
    user: { id: "events-hydration-owner", role: "student" } as UserState,
    loading: false,
  })
  sdk.list.mockReset()
})
let container: HTMLDivElement | undefined
let root: Root | undefined
const clients: QueryClient[] = []
afterEach(async () => {
  if (root) await act(() => root?.unmount())
  root = undefined
  container?.remove()
  container = undefined
  useAuthStore.setState(previousAuth)
  clients.forEach((client) => client.clear())
  clients.length = 0
  vi.unstubAllGlobals()
})
it("keeps the pending Events feed stable while the browser restores private query storage", async () => {
  expect(getConfirmedUserId(useAuthStore.getState())).toBe("events-hydration-owner")
  let finishRequest: (response: unknown) => void = () => undefined
  const request = new Promise((resolve) => {
    finishRequest = resolve
  })
  sdk.list.mockReturnValue(request)
  const server = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(server, client)
  server.setQueryData(eventsListQueryKey({ language: "en", limit: 12 }), {
    pages: [{ items: [], has_more: false }],
    pageParams: [null],
  })
  hydrate(client, dehydrate(server))
  const browserWindow = window
  vi.stubGlobal("window", undefined)
  let html: string
  try {
    html = renderToString(
      <QueryClientProvider client={server}>
        <EventsFeature />
      </QueryClientProvider>
    )
  } finally {
    vi.stubGlobal("window", browserWindow)
  }
  expect(html).toContain('data-testid="loading"')
  container = document.createElement("div")
  const host = container
  container.innerHTML = html
  document.body.append(container)
  const errors: unknown[] = []
  let finishRestore: (value: undefined) => void = () => undefined
  const restoration = new Promise<undefined>((resolve) => {
    finishRestore = resolve
  })
  await act(async () => {
    root = hydrateRoot(
      host,
      <PersistQueryClientProvider
        client={client}
        persistOptions={{
          persister: {
            persistClient: async () => undefined,
            removeClient: async () => undefined,
            restoreClient: () => restoration,
          },
        }}
      >
        <EventsFeature />
      </PersistQueryClientProvider>,
      { onRecoverableError: (error) => errors.push(error) }
    )
  })
  expect(sdk.list).not.toHaveBeenCalled()
  expect(errors).toEqual([])
  expect(host.querySelector('[data-testid="loading"]')).not.toBeNull()
  await act(async () => {
    finishRestore(undefined)
    await restoration
  })
  await act(async () => {
    expect(sdk.list).toHaveBeenCalledTimes(1)
    expect(sdk.list.mock.calls[0]?.[0]).toMatchObject({
      query: { is_active: true, order: "starts_at_desc", limit: 12 },
    })
    expect(host.querySelector('[data-testid="loading"]')).not.toBeNull()
    finishRequest({
      status: 200,
      data: { items: [], total: 0, limit: 12, has_more: false, next_cursor: null },
    })
    await request
  })
  await waitFor(() => expect(host.querySelector('[data-testid="empty"]')).not.toBeNull())
  expect(errors).toEqual([])
})
