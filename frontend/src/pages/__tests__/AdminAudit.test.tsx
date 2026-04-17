import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { server } from "@/tests/mocks/server"

import AdminAudit from "@/pages/AdminAudit"
import { AuthContext } from "@/contexts/AuthContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import type { User } from "@/types/User"

const mockLogs = {
  items: [
    {
      id: "1",
      action: "user.login",
      resource_type: "user",
      resource_id: "u1",
      actor_user_id: "u1",
      actor_name: "John Doe",
      subject_user_id: null,
      subject_name: null,
      created_at: "2026-02-06T12:00:00Z",
      ip_address: "127.0.0.1",
      user_agent: "Mozilla/5.0",
      is_valid: true,
      context: { foo: "bar" },
    },
    {
      id: "2",
      action: "user.delete",
      resource_type: "user",
      resource_id: "u2",
      actor_user_id: "admin-id",
      actor_name: "Admin",
      subject_user_id: "u2",
      subject_name: "Jane Smith",
      created_at: "2026-02-06T12:05:00Z",
      ip_address: "127.0.0.1",
      user_agent: "Mozilla/5.0",
      is_valid: false,
      context: {},
    },
  ],
  total: 2,
}

const adminUser: User = {
  id: "admin-id",
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
  submitMfaChallenge: vi.fn(),
  requireMfa: vi.fn(),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <AuthContext.Provider value={authValue}>
      <LanguageProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <AdminAudit />
          </MemoryRouter>
        </QueryClientProvider>
      </LanguageProvider>
    </AuthContext.Provider>
  )
}

describe("AdminAudit page", () => {
  beforeEach(() => {
    server.use(http.get("*/admin/audit", () => HttpResponse.json(mockLogs)))
  })

  it("renders audit logs", async () => {
    renderPage()

    expect(await screen.findByText(/Secure Audit Logs/i)).toBeInTheDocument()
    expect(await screen.findByText("John Doe")).toBeInTheDocument()
    expect(await screen.findByText("USER LOGIN")).toBeInTheDocument()
    expect(await screen.findByText("Admin")).toBeInTheDocument()
    expect(await screen.findByText("USER DELETE")).toBeInTheDocument()
  })

  it("expands log details", async () => {
    renderPage()

    const expandButtons = await screen.findAllByRole("button")
    // Second log row expand button
    await userEvent.click(expandButtons[1]!)

    expect(await screen.findByText(/Details/)).toBeInTheDocument()
    expect(await screen.findByText(/Jane Smith/)).toBeInTheDocument()
    expect(screen.getByText(/127\.0\.0\.1/)).toBeInTheDocument()
  })

  it("filters logs by resource type", async () => {
    renderPage()

    const resourceFilter = screen.getByLabelText(/Resource Type/i)
    await userEvent.type(resourceFilter, "user")

    // fetchLogs is called on filter change
    // Since we mock the same data, we just check if things are still there
    expect(await screen.findByText("John Doe")).toBeInTheDocument()
  })
})
