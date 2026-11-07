import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

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
const failureBody = {
  detail: [{ loc: ["body"], msg: "invalid action", type: "value_error" }],
}

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

function installFailOnce(method: "PATCH" | "POST" | "DELETE", path: string) {
  const list = installListHandlers()
  let mutationRequests = 0
  server.use(
    http.all(`*${path}`, ({ request }) => {
      if (request.method !== method) return
      mutationRequests += 1
      if (mutationRequests === 1) return HttpResponse.json(failureBody, { status: 503 })
      return HttpResponse.json({ read: true })
    })
  )
  return {
    mutationRequests: () => mutationRequests,
    listRequests: list.listRequests,
  }
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

const retryFor = (alert: HTMLElement, action: RegExp) =>
  within(alert).getByRole("button", { name: action })

describe("NotificationsBell mutation failure feedback and retry", () => {
  it("shows a failed mark-read request and retries that notification", async () => {
    const requests = installFailOnce("PATCH", readPath)
    const user = userEvent.setup()
    renderBell()
    await openBell(user)

    await user.click(screen.getByTitle("Mark as read"))
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Something went wrong: Mark as read: Welcome")
    expect(requests.mutationRequests()).toBe(1)

    await user.click(retryFor(alert, /Try again: Mark as read: Welcome/))
    await waitFor(() => expect(requests.mutationRequests()).toBe(2))
    await waitFor(() => expect(requests.listRequests()).toBe(2))
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument())
  })

  it("shows a failed mark-all request and retries without invalidating on failure", async () => {
    const requests = installFailOnce("POST", "/api/v1/notifications/read-all")
    const user = userEvent.setup()
    renderBell()
    await openBell(user)

    await user.click(screen.getByTitle("Mark all as read"))
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Something went wrong: Mark all as read")
    expect(requests.mutationRequests()).toBe(1)
    expect(requests.listRequests()).toBe(1)

    await user.click(retryFor(alert, /Try again: Mark all as read/))
    await waitFor(() => expect(requests.mutationRequests()).toBe(2))
    await waitFor(() => expect(requests.listRequests()).toBe(2))
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument())
  })

  it("keeps the dropdown open after a failed clear and closes only after retry succeeds", async () => {
    const requests = installFailOnce("DELETE", "/api/v1/notifications")
    const user = userEvent.setup()
    renderBell()
    await openBell(user)

    await user.click(screen.getByTitle("Clear"))
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Something went wrong: Clear")
    expect(requests.mutationRequests()).toBe(1)
    expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument()

    await user.click(retryFor(alert, /Try again: Clear/))
    await waitFor(() => expect(requests.mutationRequests()).toBe(2))
    await waitFor(() => expect(requests.listRequests()).toBe(2))
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()
    )
  })

  it("keeps overlapping mark-read and mark-all failures separate and retries only the selected action", async () => {
    const requests = installListHandlers()
    let markReadRequests = 0
    let markAllRequests = 0
    server.use(
      http.patch(`*${readPath}`, () => {
        markReadRequests += 1
        return markReadRequests === 1
          ? HttpResponse.json(failureBody, { status: 503 })
          : HttpResponse.json({ read: true })
      }),
      http.post("*api/v1/notifications/read-all", () => {
        markAllRequests += 1
        return markAllRequests === 1
          ? HttpResponse.json(failureBody, { status: 503 })
          : HttpResponse.json({ read: true })
      })
    )
    const user = userEvent.setup()
    renderBell()
    await openBell(user)

    await user.click(screen.getByTitle("Mark as read"))
    const readAlert = await screen.findByRole("alert")
    await user.click(screen.getByTitle("Mark all as read"))
    await screen.findByText("Something went wrong: Mark all as read")

    const alerts = screen.getAllByRole("alert")
    expect(alerts).toHaveLength(2)
    const currentReadAlert = alerts.find((alert) =>
      within(alert).queryByRole("button", { name: /Mark as read: Welcome/ })
    )
    const currentMarkAllAlert = alerts.find((alert) =>
      within(alert).queryByRole("button", {
        name: /Try again: Mark all as read/,
      })
    )
    expect(currentReadAlert).toBeDefined()
    expect(currentMarkAllAlert).toBeDefined()

    await user.click(retryFor(currentReadAlert ?? readAlert, /Try again: Mark as read: Welcome/))
    await waitFor(() => expect(markReadRequests).toBe(2))
    expect(markAllRequests).toBe(1)
    expect(screen.getByRole("alert")).toHaveTextContent("Mark all as read")

    await user.click(retryFor(currentMarkAllAlert!, /Try again: Mark all as read/))
    await waitFor(() => expect(markAllRequests).toBe(2))
    await waitFor(() => expect(requests.listRequests()).toBe(3))
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument())
  })

  it("keeps an unread link in place when marking it read fails", async () => {
    const requests = installFailOnce("PATCH", readPath)
    const user = userEvent.setup()
    renderBell()
    await openBell(user)
    const link = screen.getByRole("link", { name: /Welcome/ })
    const currentPath = window.location.pathname
    const click = new MouseEvent("click", { bubbles: true, cancelable: true })

    fireEvent(link, click)
    expect(click.defaultPrevented).toBe(true)
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Mark as read: Welcome")
    expect(requests.mutationRequests()).toBe(1)
    expect(window.location.pathname).toBe(currentPath)
  })

  it("does not expose a pending account A failure after the mounted bell switches to account B", async () => {
    installListHandlers()
    let releaseFailure!: () => void
    let requestStarted!: () => void
    let mutationRequests = 0
    const failureGate = new Promise<void>((resolve) => {
      releaseFailure = resolve
    })
    const started = new Promise<void>((resolve) => {
      requestStarted = resolve
    })
    server.use(
      http.patch(`*${readPath}`, async () => {
        mutationRequests += 1
        requestStarted()
        await failureGate
        return HttpResponse.json(failureBody, { status: 503 })
      })
    )
    const queryClient = renderBell()
    const user = userEvent.setup()
    await openBell(user)
    await user.click(screen.getByTitle("Mark as read"))
    await started

    act(() => {
      useAuthStore.setState({
        user: { ...testUser, id: "account-B" } as UserState,
        loading: false,
      })
    })
    releaseFailure()
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))

    expect(mutationRequests).toBe(1)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Try again/ })).not.toBeInTheDocument()
  })
})
