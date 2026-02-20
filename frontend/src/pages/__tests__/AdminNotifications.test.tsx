import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import AdminNotifications from "@/pages/AdminNotifications"
import { AuthContext } from "@/contexts/AuthContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import type { User } from "@/types/User"
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
}

type RenderResult = { queryClient: QueryClient }

const renderPage = (): RenderResult => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  render(
    <AuthContext.Provider value={authValue}>
      <LanguageProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <AdminNotifications />
          </MemoryRouter>
        </QueryClientProvider>
      </LanguageProvider>
    </AuthContext.Provider>
  )

  return { queryClient }
}

describe("AdminNotifications page", () => {
  beforeEach(() => {
    resetAdminDeadLetterJobs()
  })

  it("lists dead-letter jobs and supports selection", async () => {
    const { queryClient } = renderPage()

    expect(await screen.findByText(/Notification queue/i)).toBeInTheDocument()
    expect(await screen.findByText("Timeout")).toBeInTheDocument()
    expect(await screen.findByText("Webhook failed")).toBeInTheDocument()
    expect(screen.getByText("Total jobs: 2")).toBeInTheDocument()

    const checkbox = await screen.findByRole("checkbox", { name: /Select job uuid-1/i })
    await userEvent.click(checkbox)
    expect(checkbox).toBeChecked()

    queryClient.clear()
  })

  it("retries and purges selected jobs", async () => {
    const { queryClient } = renderPage()

    const firstJobCheckbox = await screen.findByRole("checkbox", { name: /Select job uuid-1/i })
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

    const { queryClient } = renderPage()

    expect(await screen.findByText("nope")).toBeInTheDocument()

    queryClient.clear()
  })
})

