import { act, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest"
import { HttpResponse, http } from "msw"
import { notifyManager, QueryClient } from "@tanstack/react-query"

import AdminNotifications from "@/pages/AdminNotifications"
import * as notificationsApi from "@/api/notifications"
import { adminDeadLetterQueueQueryKey } from "@/api/hooks/adminNotifications"
import { AuthContext } from "@/contexts/AuthContext"
import type { User } from "@/types/User"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { resetAdminDeadLetterJobs } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"

const adminUser: User = {
  id: "uuid-1",
  email: "admin@example.com",
  full_name: "Admin User",
  role: "admin",
  group_id: null,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  profile_detail: undefined,
  education_path: undefined,
  preferences: undefined,
  spotify_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
}

const authValue = {
  isAuth: true,
  login: vi.fn(),
  logout: vi.fn(),
  user: adminUser,
  loading: false,
  setUser: vi.fn(),
  refresh: vi.fn(),
  pendingMfa: null,
  submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
  requireMfa: vi.fn().mockResolvedValue(null),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

type RenderResult = { queryClient: QueryClient }

let loadTopicsSpy: MockInstance<typeof notificationsApi.fetchAdminUserTopics>
let saveTopicsSpy: MockInstance<typeof notificationsApi.updateAdminUserTopics>

async function settleQueue(queryClient: QueryClient) {
  // Wait for the request lifecycle, then flush Query's scheduled observer notifications.
  await waitFor(() => {
    expect(queryClient.isMutating()).toBe(0)
    expect(queryClient.isFetching({ queryKey: adminDeadLetterQueueQueryKey })).toBe(0)
  })
  await act(async () => {
    await new Promise<void>((resolve) => notifyManager.schedule(resolve))
  })
}

async function settleTopicRequest(request: Promise<unknown>) {
  await act(async () => {
    try {
      await request
    } catch {
      // The caller checks the feature's error state after the real request rejects.
    }
  })
}

const renderPage = async (): Promise<RenderResult> => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  const WrappedPage = () => (
    <AuthContext.Provider value={authValue}>
      <AdminNotifications />
    </AuthContext.Provider>
  )

  await renderWithRouter({
    ui: WrappedPage,
    queryClient,
    authProvider: false,
  })

  await settleQueue(queryClient)
  return { queryClient }
}

describe("AdminNotifications page", () => {
  beforeEach(() => {
    resetAdminDeadLetterJobs()
    loadTopicsSpy = vi.spyOn(notificationsApi, "fetchAdminUserTopics")
    saveTopicsSpy = vi.spyOn(notificationsApi, "updateAdminUserTopics")
  })

  afterEach(() => {
    loadTopicsSpy.mockRestore()
    saveTopicsSpy.mockRestore()
  })

  it("lists dead-letter jobs and supports selection", async () => {
    const { queryClient } = await renderPage()

    expect(screen.getByText(/Notification queue/i)).toBeInTheDocument()
    expect(screen.getByText("Timeout")).toBeInTheDocument()
    expect(screen.getByText("Webhook failed")).toBeInTheDocument()
    expect(screen.getByText("Total jobs: 2")).toBeInTheDocument()

    const checkbox = screen.getByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(checkbox)
    expect(checkbox).toBeChecked()

    queryClient.clear()
  })

  it("retries and purges selected jobs", async () => {
    const { queryClient } = await renderPage()

    const firstJobCheckbox = screen.getByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(firstJobCheckbox)

    const retryButton = screen.getByRole("button", { name: /Retry selected/i })
    await userEvent.click(retryButton)
    await settleQueue(queryClient)

    expect(screen.queryByText("Timeout")).not.toBeInTheDocument()
    expect(screen.getByText("Total jobs: 1")).toBeInTheDocument()

    const secondJobCheckbox = screen.getByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440002/i,
    })
    await userEvent.click(secondJobCheckbox)

    const purgeButton = screen.getByRole("button", { name: /Delete selected/i })
    await userEvent.click(purgeButton)
    await settleQueue(queryClient)

    expect(screen.queryByText("Webhook failed")).not.toBeInTheDocument()
    expect(screen.getByText(/No dead-lettered jobs/)).toBeInTheDocument()

    queryClient.clear()
  })

  it("shows an error when the queue cannot be loaded", async () => {
    server.use(
      http.get("*/notifications/admin/dead-letter", () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 })
      )
    )

    const { queryClient } = await renderPage()

    expect(screen.getByText("nope")).toBeInTheDocument()

    queryClient.clear()
  })

  // ── Testing session 9 — coverage extension ──────────────────────────────
  // Select-all toggle, per-row actions, action-error surface and the entire
  // user-topics management section (load / toggle / save + error paths).

  it("select-all toggles every row and back", async () => {
    const { queryClient } = await renderPage()

    const selectAll = screen.getByRole("checkbox", { name: /Select all/i })
    const rowCheckbox = screen.getByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })

    await userEvent.click(selectAll)
    expect(rowCheckbox).toBeChecked()

    await userEvent.click(selectAll)
    expect(rowCheckbox).not.toBeChecked()

    queryClient.clear()
  })

  it("toggles an individual row off after selecting it", async () => {
    const { queryClient } = await renderPage()

    const rowCheckbox = screen.getByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(rowCheckbox)
    expect(rowCheckbox).toBeChecked()
    await userEvent.click(rowCheckbox)
    expect(rowCheckbox).not.toBeChecked()

    queryClient.clear()
  })

  it("renders unknown job kinds and defensive nullable cells", async () => {
    server.use(
      http.get("*/notifications/admin/dead-letter", () =>
        HttpResponse.json({
          items: [
            {
              id: "unknown-job",
              kind: "maintenance",
              record_id: "record-unknown",
              locale: null,
              enqueued_at: new Date().toISOString(),
              claimed_at: null,
              attempts: 1,
              last_error: null,
              next_retry_at: null,
            },
          ],
          total: 1,
        })
      )
    )
    const { queryClient } = await renderPage()

    expect(screen.getByText("maintenance")).toBeInTheDocument()
    expect(screen.getByText("Any")).toBeInTheDocument()
    expect(screen.getByText("No error recorded")).toBeInTheDocument()

    queryClient.clear()
  })

  it("retries a single job via the row action button", async () => {
    const { queryClient } = await renderPage()

    expect(screen.getByText("Timeout")).toBeInTheDocument()
    const retryButtons = screen.getAllByRole("button", { name: "Retry" })
    await userEvent.click(retryButtons[0]!)
    await settleQueue(queryClient)

    expect(screen.queryByText("Timeout")).not.toBeInTheDocument()
    expect(screen.getByText("Total jobs: 1")).toBeInTheDocument()

    queryClient.clear()
  })

  it("purges a single job via the row action button", async () => {
    const { queryClient } = await renderPage()

    expect(screen.getByText("Timeout")).toBeInTheDocument()
    const purgeButtons = screen.getAllByRole("button", { name: "Delete" })
    await userEvent.click(purgeButtons[0]!)
    await settleQueue(queryClient)

    expect(screen.queryByText("Timeout")).not.toBeInTheDocument()
    expect(screen.getByText("Total jobs: 1")).toBeInTheDocument()
    queryClient.clear()
  })

  it("surfaces an action error when retry fails", async () => {
    server.use(
      http.post("*/notifications/admin/dead-letter/retry", () =>
        HttpResponse.json({ detail: "retry exploded" }, { status: 500 })
      )
    )
    const { queryClient } = await renderPage()

    const firstJobCheckbox = screen.getByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(firstJobCheckbox)
    await userEvent.click(screen.getByRole("button", { name: /Retry selected/i }))
    await settleQueue(queryClient)

    expect(screen.getByText("retry exploded")).toBeInTheDocument()

    queryClient.clear()
  })

  it("rejects an empty user id in the topics loader", async () => {
    const { queryClient } = await renderPage()

    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(loadTopicsSpy).not.toHaveBeenCalled()
    expect(screen.getByText(/Please enter a valid user ID/i)).toBeInTheDocument()

    queryClient.clear()
  })

  it("loads, toggles and saves user topics", async () => {
    const topicsResponse = {
      user_id: "11111111-1111-1111-1111-111111111111",
      email: "student@example.com",
      allowed_topics: ["news", "events"],
      topics: ["news"],
    }
    let savedTopics: string[] | null = null
    server.use(
      http.get("*/push/admin/topics/:userId", () => HttpResponse.json(topicsResponse)),
      http.put("*/push/admin/topics/:userId", async ({ request }) => {
        const body = (await request.json()) as { topics: string[] }
        savedTopics = body.topics
        return HttpResponse.json({ ...topicsResponse, topics: body.topics })
      })
    )

    const { queryClient } = await renderPage()

    // The user-topics ID field is the first textbox; the release form follows it.
    await userEvent.type(screen.getAllByRole("textbox")[0]!, topicsResponse.user_id)
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(loadTopicsSpy).toHaveBeenCalledTimes(1)
    await settleTopicRequest(loadTopicsSpy.mock.results[0]!.value)

    expect(screen.getByText(/Topics loaded for student@example.com/i)).toBeInTheDocument()

    const newsTopic = screen.getByRole("checkbox", { name: /news/i })
    const eventsTopic = screen.getByRole("checkbox", { name: /events/i })
    expect(newsTopic).toBeChecked()
    expect(eventsTopic).not.toBeChecked()

    await userEvent.click(eventsTopic)
    await userEvent.click(screen.getByRole("button", { name: /Save topics/i }))
    expect(saveTopicsSpy).toHaveBeenCalledTimes(1)
    await settleTopicRequest(saveTopicsSpy.mock.results[0]!.value)

    expect(screen.getByText(/Topics updated successfully/i)).toBeInTheDocument()
    expect(savedTopics).toEqual(["news", "events"])

    queryClient.clear()
  })

  it("shows the empty state when the user has no allowed topics", async () => {
    server.use(
      http.get("*/push/admin/topics/:userId", () =>
        HttpResponse.json({
          user_id: "33333333-3333-3333-3333-333333333333",
          email: "empty@example.com",
          allowed_topics: [],
          topics: [],
        })
      )
    )
    const { queryClient } = await renderPage()

    await userEvent.type(screen.getAllByRole("textbox")[0]!, "empty-user-id")
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(loadTopicsSpy).toHaveBeenCalledTimes(1)
    await settleTopicRequest(loadTopicsSpy.mock.results[0]!.value)

    expect(screen.getByText("No topics are currently available.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Save topics/i })).toBeDisabled()

    queryClient.clear()
  })

  it("keeps an unknown topic readable when no translation exists", async () => {
    server.use(
      http.get("*/push/admin/topics/:userId", () =>
        HttpResponse.json({
          user_id: "44444444-4444-4444-4444-444444444444",
          email: "unknown-topic@example.com",
          allowed_topics: ["experimental"],
          topics: [],
        })
      )
    )
    const { queryClient } = await renderPage()

    await userEvent.type(screen.getAllByRole("textbox")[0]!, "unknown-topic-user-id")
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(loadTopicsSpy).toHaveBeenCalledTimes(1)
    await settleTopicRequest(loadTopicsSpy.mock.results[0]!.value)

    expect(screen.getByText(/experimental/)).toBeInTheDocument()

    queryClient.clear()
  })

  it("surfaces topics load and save errors", async () => {
    const topicsResponse = {
      user_id: "22222222-2222-2222-2222-222222222222",
      email: "broken@example.com",
      allowed_topics: ["news"],
      topics: [],
    }
    // NOTE: topics API calls flow through the generated client +
    // ensureValidResponse — a 500 surfaces as ApiResponseValidationError
    // (NOT the axios detail), so assert the error alert rather than the
    // backend detail text.
    server.use(
      http.get("*/push/admin/topics/:userId", () =>
        HttpResponse.json({ detail: "load boom" }, { status: 500 })
      )
    )

    const { queryClient } = await renderPage()

    await userEvent.type(screen.getAllByRole("textbox")[0]!, "some-user-id")
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(loadTopicsSpy).toHaveBeenCalledTimes(1)
    await settleTopicRequest(loadTopicsSpy.mock.results[0]!.value)
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0)
    expect(screen.queryByText(/Topics loaded for/i)).not.toBeInTheDocument()

    // Now make load succeed but save fail.
    server.use(
      http.get("*/push/admin/topics/:userId", () => HttpResponse.json(topicsResponse)),
      http.put("*/push/admin/topics/:userId", () =>
        HttpResponse.json({ detail: "save boom" }, { status: 500 })
      )
    )
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(loadTopicsSpy).toHaveBeenCalledTimes(2)
    await settleTopicRequest(loadTopicsSpy.mock.results[1]!.value)
    expect(screen.getByText(/Managing topics for broken@example.com/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /Save topics/i }))
    expect(saveTopicsSpy).toHaveBeenCalledTimes(1)
    await settleTopicRequest(saveTopicsSpy.mock.results[0]!.value)
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0)
    expect(screen.queryByText(/Topics updated successfully/i)).not.toBeInTheDocument()

    queryClient.clear()
  })
})
