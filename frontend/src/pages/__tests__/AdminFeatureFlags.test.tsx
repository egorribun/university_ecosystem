import { screen, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"
import { QueryClient } from "@tanstack/react-query"
import { server } from "@/tests/mocks/server"

import AdminFeatureFlags from "@/pages/AdminFeatureFlags"
import { AuthContext } from "@/contexts/AuthContext"
import type { User } from "@/types/User"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const mockFlags = [
  {
    name: "new_dashboard_v2",
    description: "Enable new dashboard layout",
    enabled: true,
    default: false,
    provider: "flagd Provider",
    evaluation_reason: "TARGETING_MATCH",
    management: "gitops" as const,
    config_path: "k8s/flagd/flags.json",
  },
  {
    name: "ai_summaries",
    description: "AI-powered news summaries (experimental)",
    enabled: false,
    default: false,
    provider: "flagd Provider",
    evaluation_reason: "DEFAULT",
    management: "gitops" as const,
    config_path: "k8s/flagd/flags.json",
  },
  {
    name: "legacy_messenger",
    description: "Legacy messenger UI fallback",
    enabled: false,
    default: true,
    provider: "flagd Provider",
    evaluation_reason: "ERROR",
    management: "gitops" as const,
    config_path: "k8s/flagd/flags.json",
  },
]

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
  submitMfaChallenge: vi.fn(),
  requireMfa: vi.fn(),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

const renderPage = async () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  const WrappedPage = () => (
    <AuthContext.Provider value={authValue}>
      <AdminFeatureFlags />
    </AuthContext.Provider>
  )

  return renderWithRouter({
    ui: WrappedPage,
    queryClient,
    // Test mounts its own AuthContext.Provider with admin user.
    authProvider: false,
  })
}

describe("AdminFeatureFlags page", () => {
  beforeEach(() => {
    server.use(http.get("*/admin/feature-flags", () => HttpResponse.json(mockFlags)))
  })

  it("renders feature flag heading + column headers", async () => {
    await renderPage()

    expect(await screen.findByText(/Feature Flag Diagnostics/i)).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: /Feature Flag/i })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: /Effective value/i })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: /Fallback/i })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: /Management/i })).toBeInTheDocument()
  })

  it("renders feature flags from the API", async () => {
    await renderPage()

    expect(await screen.findByText("new_dashboard_v2")).toBeInTheDocument()
    expect(screen.getByText(/Enable new dashboard layout/)).toBeInTheDocument()
    expect(screen.getByText("ai_summaries")).toBeInTheDocument()
    expect(screen.getByText("legacy_messenger")).toBeInTheDocument()
  })

  it("renders ARIA-compliant table semantics", async () => {
    await renderPage()
    await screen.findByText("new_dashboard_v2")

    const table = screen.getByRole("table", { name: /Feature flags/i })
    expect(table).toBeInTheDocument()

    // All <th> have scope="col" (W150 SW2 a11y batch)
    const columnHeaders = within(table).getAllByRole("columnheader")
    expect(columnHeaders.length).toBe(4)
    for (const header of columnHeaders) {
      expect(header.getAttribute("scope")).toBe("col")
    }
  })

  it("renders provider diagnostics and the canonical GitOps path", async () => {
    await renderPage()
    await screen.findByText("new_dashboard_v2")

    expect(screen.getAllByText("flagd Provider")).toHaveLength(3)
    expect(screen.getByText("TARGETING_MATCH")).toBeInTheDocument()
    expect(screen.getByText("ERROR")).toBeInTheDocument()
  })

  it("is an honest read-only GitOps surface", async () => {
    await renderPage()
    await screen.findByText("ai_summaries")

    expect(screen.getByText(/read-only/i)).toBeInTheDocument()
    expect(screen.getAllByText("k8s/flagd/flags.json")).toHaveLength(3)
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
    expect(screen.queryByRole("slider")).not.toBeInTheDocument()
  })
})
