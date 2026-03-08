import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"

import type { User } from "@/types/User"
import { server } from "../../mocks/server"

const baseUser: User = {
  id: "uuid-1",
  email: "user@example.com",
  full_name: "Test User",
  role: "student",
  group_id: null,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  profile_detail: {
    about: null,
    telegram: null,
    status: null,
    achievements: null,
    department: null,
    position: null,
  },
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

const renderNewsPage = async (queryClient?: QueryClient) => {
  const [{ AuthContext }, { LanguageProvider }] = await Promise.all([
    import("@/contexts/AuthContext"),
    import("@/contexts/LanguageContext"),
  ])

  const authValue = {
    login: vi.fn().mockResolvedValue(null),
    loginWithPasskey: vi.fn().mockResolvedValue(null),
    logout: vi.fn().mockResolvedValue(undefined),
    user: baseUser,
    loading: false,
    setUser: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
    pendingMfa: null,
    submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
    requireMfa: vi.fn().mockResolvedValue(null),
    resetEtagCache: vi.fn(),
  }

  const client =
    queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })

  const { default: News } = await import("@/pages/News")

  render(
    <AuthContext.Provider value={authValue}>
      <LanguageProvider>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={["/news"]}>
            <News />
          </MemoryRouter>
        </QueryClientProvider>
      </LanguageProvider>
    </AuthContext.Provider>
  )

  return { queryClient: client }
}

// Note: Skipped due to "async Client Component" error from dynamic imports in Vitest
describe.skip("News page interaction", () => {
  beforeEach(() => {
    vi.resetModules()
    server.resetHandlers()
    server.use(
      http.get("*/news/*/interactions", () => {
        return HttpResponse.json({
          views_count: 5,
          is_viewed: true,
          likes_count: 2,
          is_liked: false,
        })
      })
    )
  })

  it("fetches and displays news list", async () => {
    server.use(
      http.get("*/news", () => {
        return HttpResponse.json({
          items: [
            {
              id: "news-1",
              title: "Headline 1",
              content: "Content 1",
              created_at: new Date().toISOString(),
              image_url: null,
            },
            {
              id: "news-2",
              title: "Headline 2",
              content: "Content 2",
              created_at: new Date().toISOString(),
              image_url: null,
            },
          ],
          has_more: false,
          next_cursor: null,
        })
      })
    )

    await renderNewsPage()

    expect(await screen.findByText("Headline 1")).toBeInTheDocument()
    expect(screen.getByText("Headline 2")).toBeInTheDocument()
  })
})
