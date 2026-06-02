import { screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { QueryClient } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"

import type { User } from "@/types/User"
import { server } from "../../mocks/server"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { AuthContext } from "@/contexts/AuthContext"
import News from "@/pages/News"

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
    authOperation: false,
  }

  const client =
    queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })

  const WrappedNews = () => (
    <AuthContext.Provider value={authValue}>
      <News />
    </AuthContext.Provider>
  )

  await renderWithRouter({
    ui: WrappedNews,
    path: "/news",
    initialPath: "/news",
    queryClient: client,
    authProvider: false,
  })

  return { queryClient: client }
}

// Wave 115 SW2 closed SW1-remainder: the original test used an async factory with
// `await import("@/pages/News")` + `await import("@/contexts/AuthContext")` inside
// `renderNewsPage`. Under Vitest, that pattern intermittently surfaces the "async
// Client Component" diagnostic and leaves the tested render in a half-mounted
// state. Moving both imports to the module top-level (standard pattern for vitest
// + `vi.resetModules()` is no longer required here because neither AuthContext
// nor the News page mutate module state between runs) fixes the flake.
describe("News page interaction", () => {
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
              image_url_optimized: null,
            },
            {
              id: "news-2",
              title: "Headline 2",
              content: "Content 2",
              created_at: new Date().toISOString(),
              image_url: null,
              image_url_optimized: null,
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
