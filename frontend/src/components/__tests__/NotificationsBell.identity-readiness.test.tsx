import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { afterEach, beforeEach, expect, it } from "vitest"

import { resetEtagCache } from "@/api/client"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import {
  getCheckScheduleAndGenerateApiV1NotificationsCheckSchedulePost200Response,
  getListNotificationsApiV1NotificationsGet200Response,
} from "@/tests/mocks/generated/handlers"
import { server } from "@/tests/mocks/server"
import type { UserState } from "@/types/Auth"
import NotificationsBell from "../feedback/NotificationsBell"

const notificationId = "33333333-3333-4333-8333-333333333333"
const readPath = `/api/v1/notifications/${notificationId}/read`

const createListResponse = (url: string | null = "/news/welcome") => {
  const response = getListNotificationsApiV1NotificationsGet200Response()
  return {
    ...response,
    items: [
      {
        ...response.items[0],
        id: notificationId,
        title: "Welcome",
        body: "A new update is available.",
        url,
        created_at: "2026-01-01T00:00:00Z",
        read: false,
        read_at: null,
      },
    ],
    unread_count: 1,
    has_more: false,
    next_cursor: null,
  }
}

let previousAuthState = useAuthStore.getState()

beforeEach(() => {
  previousAuthState = useAuthStore.getState()
  localStorage.clear()
  acceptBrowserSessionGeneration()
  resetEtagCache()
  act(() => {
    useAuthStore.setState({
      user: { ...testUser } as UserState,
      loading: false,
      pendingMfa: null,
      authOperation: false,
    })
  })
})

afterEach(() => {
  const { user, loading, pendingMfa, authOperation } = previousAuthState
  act(() => {
    useAuthStore.setState({ user, loading, pendingMfa, authOperation })
  })
  localStorage.clear()
  resetEtagCache()
  acceptBrowserSessionGeneration()
})

function installListHandlers(url: string | null = "/news/welcome") {
  let listRequests = 0
  server.use(
    http.post("*api/v1/notifications/check-schedule", () =>
      HttpResponse.json(getCheckScheduleAndGenerateApiV1NotificationsCheckSchedulePost200Response())
    ),
    http.get("*api/v1/notifications", () => {
      listRequests += 1
      return HttpResponse.json(createListResponse(url))
    })
  )
  return { listRequests: () => listRequests }
}

function renderBell() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <NotificationsBell />
    </QueryClientProvider>
  )
  return queryClient
}

async function openBell(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Open notifications" }))
  await screen.findByText("Welcome")
}

it("keeps individual and bulk mutations disabled until the notification owner is confirmed", async () => {
  act(() => useAuthStore.setState({ user: null, loading: true }))
  installListHandlers()
  const mutations: string[] = []
  server.use(
    http.patch(`*${readPath}`, () => {
      mutations.push("read")
      return HttpResponse.json({ read: true })
    }),
    http.post("*api/v1/notifications/read-all", () => {
      mutations.push("all")
      return HttpResponse.json({ read: true })
    }),
    http.delete("*api/v1/notifications", () => {
      mutations.push("clear")
      return HttpResponse.json({ ok: true })
    })
  )
  const user = userEvent.setup()
  renderBell()
  await openBell(user)
  const read = screen.getByTitle("Mark as read")
  const all = screen.getByTitle("Mark all as read")
  const clear = screen.getByTitle("Clear")
  expect(read).toBeDisabled()
  expect(all).toBeDisabled()
  expect(clear).toBeDisabled()
  await user.click(read)
  await user.click(all)
  await user.click(clear)
  const notificationLink = screen.getByText("Welcome").closest("a")!
  expect(notificationLink).toHaveAttribute("aria-disabled", "true")
  await user.click(notificationLink)
  expect(mutations).toEqual([])

  act(() => useAuthStore.setState({ user: { ...testUser } as UserState, loading: false }))
  await waitFor(() => expect(read).toBeEnabled())
  expect(all).toBeEnabled()
  expect(clear).toBeEnabled()
  expect(notificationLink).not.toHaveAttribute("aria-disabled", "true")
  await user.click(read)
  await waitFor(() => expect(mutations).toEqual(["read"]))
})

it("disables loaded actions for a pending replacement identity and restores them when confirmed", async () => {
  installListHandlers()
  const user = userEvent.setup()
  renderBell()
  await openBell(user)
  const read = screen.getByTitle("Mark as read")
  const all = screen.getByTitle("Mark all as read")
  const clear = screen.getByTitle("Clear")
  expect(read).toBeEnabled()

  // Same-account step-up loading retains the established owner by design.
  act(() => useAuthStore.setState({ loading: true }))
  expect(read).toBeEnabled()
  expect(all).toBeEnabled()
  expect(clear).toBeEnabled()

  act(() => useAuthStore.setState({ user: { ...testUser, id: "replacement-owner" } as UserState }))
  expect(read).toBeDisabled()
  expect(all).toBeDisabled()
  expect(clear).toBeDisabled()

  act(() => useAuthStore.setState({ loading: false }))
  expect(read).toBeEnabled()
  expect(all).toBeEnabled()
  expect(clear).toBeEnabled()
})
