import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"
import { QueryClient } from "@tanstack/react-query"

import AdminNotifications from "@/pages/AdminNotifications"
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
  mfa_challenges: [],
}

const authValue = {
  isAuth: true,
  login: vi.fn(),
  loginWithPasskey: vi.fn(),
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

  return { queryClient }
}

describe("AdminNotifications page", () => {
  beforeEach(() => {
    resetAdminDeadLetterJobs()
  })

  it("lists dead-letter jobs and supports selection", async () => {
    const { queryClient } = await renderPage()

    expect(await screen.findByText(/Notification queue/i)).toBeInTheDocument()
    expect(await screen.findByText("Timeout")).toBeInTheDocument()
    expect(await screen.findByText("Webhook failed")).toBeInTheDocument()
    expect(screen.getByText("Total jobs: 2")).toBeInTheDocument()

    const checkbox = await screen.findByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(checkbox)
    expect(checkbox).toBeChecked()

    queryClient.clear()
  })

  it("retries and purges selected jobs", async () => {
    const { queryClient } = await renderPage()

    const firstJobCheckbox = await screen.findByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(firstJobCheckbox)

    const retryButton = await screen.findByRole("button", { name: /Retry selected/i })
    await userEvent.click(retryButton)

    await waitFor(() => expect(screen.queryByText("Timeout")).not.toBeInTheDocument())
    expect(screen.getByText("Total jobs: 1")).toBeInTheDocument()

    const secondJobCheckbox = await screen.findByRole("checkbox", { name: /Select job uuid-2/i })
    await userEvent.click(secondJobCheckbox)

    const purgeButton = await screen.findByRole("button", { name: /Delete selected/i })
    await userEvent.click(purgeButton)

    await waitFor(() => expect(screen.queryByText("Webhook failed")).not.toBeInTheDocument())
    expect(await screen.findByText(/No dead-lettered jobs/)).toBeInTheDocument()

    queryClient.clear()
  })

  it("shows an error when the queue cannot be loaded", async () => {
    server.use(
      http.get("*/notifications/admin/dead-letter", () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 })
      )
    )

    const { queryClient } = await renderPage()

    expect(await screen.findByText("nope")).toBeInTheDocument()

    queryClient.clear()
  })

  // ── Testing session 9 — coverage extension ──────────────────────────────
  // Select-all toggle, per-row actions, action-error surface and the entire
  // user-topics management section (load / toggle / save + error paths).

  it("select-all toggles every row and back", async () => {
    const { queryClient } = await renderPage()

    const selectAll = await screen.findByRole("checkbox", { name: /Select all/i })
    const rowCheckbox = await screen.findByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })

    await userEvent.click(selectAll)
    expect(rowCheckbox).toBeChecked()

    await userEvent.click(selectAll)
    expect(rowCheckbox).not.toBeChecked()

    queryClient.clear()
  })

  it("retries a single job via the row action button", async () => {
    const { queryClient } = await renderPage()

    expect(await screen.findByText("Timeout")).toBeInTheDocument()
    const retryButtons = await screen.findAllByRole("button", { name: "Retry" })
    await userEvent.click(retryButtons[0]!)

    await waitFor(() => expect(screen.queryByText("Timeout")).not.toBeInTheDocument())
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

    const firstJobCheckbox = await screen.findByRole("checkbox", {
      name: /Select job 550e8400-e29b-41d4-a716-446655440000/i,
    })
    await userEvent.click(firstJobCheckbox)
    await userEvent.click(screen.getByRole("button", { name: /Retry selected/i }))

    expect(await screen.findByText("retry exploded")).toBeInTheDocument()

    queryClient.clear()
  })

  it("rejects an empty user id in the topics loader", async () => {
    const { queryClient } = await renderPage()

    await userEvent.click(await screen.findByRole("button", { name: /Load topics/i }))
    expect(await screen.findByText(/Please enter a valid user ID/i)).toBeInTheDocument()

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

    await userEvent.type(await screen.findByRole("textbox"), topicsResponse.user_id)
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))

    expect(await screen.findByText(/Topics loaded for student@example.com/i)).toBeInTheDocument()

    const newsTopic = screen.getByRole("checkbox", { name: /news/i })
    const eventsTopic = screen.getByRole("checkbox", { name: /events/i })
    expect(newsTopic).toBeChecked()
    expect(eventsTopic).not.toBeChecked()

    await userEvent.click(eventsTopic)
    await userEvent.click(screen.getByRole("button", { name: /Save topics/i }))

    expect(await screen.findByText(/Topics updated successfully/i)).toBeInTheDocument()
    expect(savedTopics).toEqual(["news", "events"])

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

    await userEvent.type(await screen.findByRole("textbox"), "some-user-id")
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0))
    expect(screen.queryByText(/Topics loaded for/i)).not.toBeInTheDocument()

    // Now make load succeed but save fail.
    server.use(
      http.get("*/push/admin/topics/:userId", () => HttpResponse.json(topicsResponse)),
      http.put("*/push/admin/topics/:userId", () =>
        HttpResponse.json({ detail: "save boom" }, { status: 500 })
      )
    )
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(await screen.findByText(/Managing topics for broken@example.com/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /Save topics/i }))
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0))
    expect(screen.queryByText(/Topics updated successfully/i)).not.toBeInTheDocument()

    queryClient.clear()
  })
})
