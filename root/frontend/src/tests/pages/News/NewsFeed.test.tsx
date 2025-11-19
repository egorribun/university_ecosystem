import { act, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"
import type { ContextType } from "react"

import type { User } from "@/types/User"
import { server } from "../../mocks/server"

type CacheEntry = { key: string; response: Response }

const buildCacheKey = (language: string) => {
  const origin = window.location.origin
  const url = new URL("/api/news", origin).toString()
  return `${url}::${language}`
}

const createNewsItem = (id: number, title: string) => ({
  id,
  title,
  content: `${title} content`,
  created_at: new Date(Date.UTC(2024, 0, id)).toISOString(),
  title_en: title,
  content_en: `${title} content`,
  image_url: null,
})

const createNewsResponse = (items: ReturnType<typeof createNewsItem>[], etag?: string) => {
  const headers = new Headers({ "Content-Type": "application/json" })
  if (etag) headers.set("ETag", etag)
  return new Response(JSON.stringify(items), { status: 200, headers })
}

const createMockCaches = (initialEntries: CacheEntry[] = []) => {
  const entries = new Map<string, Response>()
  for (const entry of initialEntries) {
    entries.set(entry.key, entry.response)
  }

  const resolveKey = (request: RequestInfo | URL) => {
    if (typeof request === "string") {
      const url = new URL(request, window.location.origin).toString()
      return `${url}::`
    }
    if (request instanceof Request) {
      const language = request.headers.get("accept-language") ?? ""
      return `${request.url}::${language}`
    }
    if (request instanceof URL) {
      return `${request.toString()}::`
    }
    return `${String(request)}::`
  }

  const match = vi.fn(async (request: RequestInfo | URL) => {
    const key = resolveKey(request)
    const value = entries.get(key)
    return value ? value.clone() : undefined
  })

  const put = vi.fn(async (request: RequestInfo | URL, response: Response) => {
    const key = resolveKey(request)
    entries.set(key, response.clone())
  })

  const cache = {
    match,
    put,
    delete: vi.fn(async () => false),
    add: vi.fn(),
    addAll: vi.fn(),
    keys: vi.fn(async () =>
      Array.from(entries.keys()).map((key) => new Request(key.split("::")[0]!))
    ),
  } as unknown as Cache

  const cachesStorage = {
    open: vi.fn(async () => cache),
    match: vi.fn(),
    has: vi.fn(),
    delete: vi.fn(),
    keys: vi.fn(),
  } as unknown as CacheStorage

  return { cachesStorage, cache, match, put, entries }
}

const baseUser: User = {
  id: 1,
  email: "user@example.com",
  full_name: "Test User",
  role: "student",
  group_id: null,
  avatar_url: null,
  cover_url: null,
  about: null,
  record_book_number: null,
  status: null,
  institute: null,
  course: null,
  education_level: null,
  track: null,
  program: null,
  telegram: null,
  achievements: null,
  department: null,
  position: null,
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: null,
  dnd_enabled: false,
  dnd_start: null,
  dnd_end: null,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  totp_enrollments: [],
  mfa_challenges: [],
}

const renderNewsPage = async (queryClient?: QueryClient) => {
  const [{ AuthContext }, { LanguageProvider }] = await Promise.all([
    import("@/contexts/AuthContext"),
    import("@/contexts/LanguageContext"),
  ])

  type AuthContextValue = ContextType<typeof AuthContext>

  const authValue: AuthContextValue = {
    isAuth: true,
    login: vi.fn().mockResolvedValue(null),
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

describe("News page feed integration", () => {
  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
    delete (window as unknown as { caches?: CacheStorage }).caches
    window.localStorage.setItem("ue:language", "ru")
    server.resetHandlers()
  })

  it("persists API responses and revalidates using cached ETags", async () => {
    const { cachesStorage, put } = createMockCaches()
    Object.defineProperty(window, "caches", { value: cachesStorage, configurable: true })

    const stories = [createNewsItem(1, "API headline")]
    let requestCount = 0

    server.use(
      http.get("*/news", ({ request }) => {
        requestCount += 1
        if (requestCount === 1) {
          return HttpResponse.json(stories, { headers: { ETag: '"api-tag"' } })
        }
        expect(request.headers.get("if-none-match")).toBe('"api-tag"')
        return new HttpResponse(null, { status: 304, headers: { ETag: '"api-tag"' } })
      })
    )

    const { queryClient } = await renderNewsPage()

    expect(await screen.findByText("API headline")).toBeInTheDocument()
    await waitFor(() => expect(requestCount).toBe(1))
    expect(put).toHaveBeenCalledTimes(1)

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["news", "feed", "ru"] })
    })

    await waitFor(() => expect(requestCount).toBe(2))
    expect(screen.getByText("API headline")).toBeInTheDocument()
    expect(put).toHaveBeenCalledTimes(1)

    queryClient.clear()
  })

  it("hydrates from service worker caches during network failures and clears legacy storage", async () => {
    const cachedItems = [createNewsItem(2, "Cached bulletin")]
    const cacheKey = buildCacheKey("ru")
    const cachedResponse = createNewsResponse(cachedItems, '"cached-tag"')
    const { cachesStorage, match } = createMockCaches([{ key: cacheKey, response: cachedResponse }])
    Object.defineProperty(window, "caches", { value: cachesStorage, configurable: true })

    window.localStorage.setItem("news:list", "legacy")
    window.localStorage.setItem("news:etag", "legacy")
    window.localStorage.setItem("news:list:ru", "legacy")
    window.localStorage.setItem("news:etag:ru", "legacy")

    server.use(http.get("*/news", () => HttpResponse.json({ detail: "offline" }, { status: 503 })))

    const { queryClient } = await renderNewsPage()

    expect(await screen.findByText("Cached bulletin")).toBeInTheDocument()
    expect(match).toHaveBeenCalled()
    expect(window.localStorage.getItem("news:list")).toBeNull()
    expect(window.localStorage.getItem("news:etag")).toBeNull()
    expect(window.localStorage.getItem("news:list:ru")).toBeNull()
    expect(window.localStorage.getItem("news:etag:ru")).toBeNull()

    const cached = queryClient.getQueryData(["news", "feed", "ru"])
    expect(cached).toBeDefined()

    queryClient.clear()
  })
})
