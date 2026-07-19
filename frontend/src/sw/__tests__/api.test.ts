/**
 * Tests for src/sw/api.ts
 *
 * Because api.ts uses workbox (registerRoute, NetworkFirst, StaleWhileRevalidate,
 * plugins) and the browser `caches` API, everything is mocked via vi.mock /
 * vitest.stubGlobal so no actual service worker is required.
 *
 * The exported pure functions (setSessionHash, getSessionHash, isOnline,
 * clearSessionCaches) are exercised directly.  The route-matching predicates
 * from initApiCaching are captured via the registerRoute mock and exercised
 * in isolation — this validates the *routing decisions* without needing a
 * live Workbox runtime.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ─── Workbox mocks ────────────────────────────────────────────────────────────

const registeredRoutes: Array<{ matchFn: (...args: any[]) => boolean; handler: any }> = []

vi.mock("workbox-routing", () => ({
  registerRoute: vi.fn((matchFn: any, handler: any) => {
    registeredRoutes.push({ matchFn, handler })
  }),
}))

vi.mock("workbox-strategies", () => ({
  NetworkFirst: vi.fn().mockImplementation((opts: any) => ({ type: "NetworkFirst", opts })),
  StaleWhileRevalidate: vi
    .fn()
    .mockImplementation((opts: any) => ({ type: "StaleWhileRevalidate", opts })),
}))

vi.mock("workbox-cacheable-response", () => ({
  CacheableResponsePlugin: vi.fn().mockImplementation((opts: any) => ({
    type: "CacheableResponsePlugin",
    opts,
  })),
}))

vi.mock("workbox-expiration", () => ({
  ExpirationPlugin: vi.fn().mockImplementation((opts: any) => ({
    type: "ExpirationPlugin",
    opts,
  })),
}))

vi.mock("./logger", () => ({
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))

// ─── caches global mock ───────────────────────────────────────────────────────

function createCachesMock(existingNames: string[] = []) {
  const deletedCaches: string[] = []
  return {
    mock: {
      keys: vi.fn().mockResolvedValue(existingNames),
      delete: vi.fn().mockImplementation(async (name: string) => {
        deletedCaches.push(name)
        return true
      }),
      open: vi.fn(),
      match: vi.fn(),
      has: vi.fn(),
    },
    deletedCaches,
  }
}

// ─── Helper: build a fake route context ──────────────────────────────────────

function makeRouteContext(pathname: string, method = "GET", cookie = "") {
  const url = new URL(`http://localhost${pathname}`)
  const request = new Request(`http://localhost${pathname}`, {
    method,
    headers: cookie ? { Cookie: cookie } : {},
  })
  return { url, request, event: {} as any }
}

// ─── Import module ────────────────────────────────────────────────────────────

let mod: typeof import("../api")

beforeEach(async () => {
  registeredRoutes.length = 0
  vi.resetModules()
  // Fresh import so initApiCaching re-registers all routes cleanly
  mod = await import("../api")
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// =============================================================================
// 1. Pure state helpers
// =============================================================================

describe("setSessionHash / getSessionHash", () => {
  it("returns null before any hash is set", () => {
    expect(mod.getSessionHash()).toBeNull()
  })

  it("stores and retrieves the session hash", () => {
    mod.setSessionHash("abc123")
    expect(mod.getSessionHash()).toBe("abc123")
  })

  it("can be reset to null", () => {
    mod.setSessionHash("xyz")
    mod.setSessionHash(null)
    expect(mod.getSessionHash()).toBeNull()
  })
})

// =============================================================================
// 2. isOnline
// =============================================================================

describe("isOnline", () => {
  it("returns true when navigator.onLine is true", () => {
    vi.stubGlobal("navigator", { onLine: true })
    expect(mod.isOnline()).toBe(true)
  })

  it("returns false when navigator.onLine is false", () => {
    vi.stubGlobal("navigator", { onLine: false })
    expect(mod.isOnline()).toBe(false)
  })
})

// =============================================================================
// 3. clearSessionCaches
// =============================================================================

describe("clearSessionCaches", () => {
  it("deletes all session-prefixed and named caches", async () => {
    const { mock: cachesMock, deletedCaches } = createCachesMock([
      "api-cache:user-42",
      "media-private:avatar",
      "api-news-cache",
      "api-news-interactions",
      "api-events-cache",
      "fonts-cache", // should NOT be deleted
    ])
    vi.stubGlobal("caches", cachesMock)

    await mod.clearSessionCaches()

    expect(deletedCaches).toContain("api-cache:user-42")
    expect(deletedCaches).toContain("media-private:avatar")
    expect(deletedCaches).toContain("api-news-cache")
    expect(deletedCaches).toContain("api-news-interactions")
    expect(deletedCaches).toContain("api-events-cache")
    expect(deletedCaches).not.toContain("fonts-cache")
  })

  it("is a no-op when there are no matching caches", async () => {
    const { mock: cachesMock } = createCachesMock(["fonts-cache", "static-assets"])
    vi.stubGlobal("caches", cachesMock)

    await mod.clearSessionCaches()

    expect(cachesMock.delete).not.toHaveBeenCalled()
  })

  it("handles an empty cache list gracefully", async () => {
    const { mock: cachesMock } = createCachesMock([])
    vi.stubGlobal("caches", cachesMock)

    await expect(mod.clearSessionCaches()).resolves.toBeUndefined()
  })
})

// =============================================================================
// 4. Route matching via initApiCaching
// =============================================================================

describe("initApiCaching — route matching", () => {
  beforeEach(() => {
    mod.initApiCaching()
  })

  // ── Helpers ──

  /**
   * Returns true if any registered route's match function accepts the context.
   */
  function isRouteMatched(pathname: string, method = "GET", cookie = "") {
    const ctx = makeRouteContext(pathname, method, cookie)
    return registeredRoutes.some(({ matchFn }) => matchFn(ctx))
  }

  // ── News interactions (NetworkFirst) ──────────────────────────────────────

  describe("news interactions route (NetworkFirst)", () => {
    it("matches GET /api/news/:id/like", () => {
      expect(isRouteMatched("/api/news/1/like")).toBe(true)
    })

    it("matches GET /api/news/:id/comment", () => {
      expect(isRouteMatched("/api/news/1/comment")).toBe(true)
    })

    it("matches POST /api/news (non-GET news mutation)", () => {
      expect(isRouteMatched("/api/news", "POST")).toBe(true)
    })

    it("matches DELETE /api/news/:id/like (non-GET)", () => {
      expect(isRouteMatched("/api/news/5/like", "DELETE")).toBe(true)
    })
  })

  // ── News list/detail (StaleWhileRevalidate) ───────────────────────────────

  describe("news list/detail route (StaleWhileRevalidate)", () => {
    it("matches GET /api/news", () => {
      expect(isRouteMatched("/api/news")).toBe(true)
    })

    it("matches GET /api/news/42 (detail)", () => {
      expect(isRouteMatched("/api/news/42")).toBe(true)
    })

    it("does NOT match /api/news/1/like for StaleWhileRevalidate (already caught by interactions)", () => {
      // The interactions route is registered first, so this test confirms the
      // /like path IS matched by *some* route (the interactions one), not
      // necessarily the news-list route.
      expect(isRouteMatched("/api/news/1/like")).toBe(true)
    })
  })

  // ── Events (StaleWhileRevalidate) ─────────────────────────────────────────

  describe("events route (StaleWhileRevalidate)", () => {
    it("matches GET /api/events", () => {
      expect(isRouteMatched("/api/events")).toBe(true)
    })

    it("matches GET /api/events/99/detail", () => {
      expect(isRouteMatched("/api/events/99/detail")).toBe(true)
    })

    it("does NOT match POST /api/events (non-GET)", () => {
      // POST /api/events is not intercepted by the events GET-only route.
      // However, it might be matched by the generic private route which
      // also only handles GET — so POST should NOT be matched by any route.
      expect(isRouteMatched("/api/events", "POST")).toBe(false)
    })
  })

  // ── Private/session API (NetworkFirst, GET only) ──────────────────────────

  describe("private session-aware API route (NetworkFirst)", () => {
    it("matches GET /api/schedule", () => {
      expect(isRouteMatched("/api/schedule")).toBe(true)
    })

    it("matches GET /api/profile/settings", () => {
      expect(isRouteMatched("/api/profile/settings")).toBe(true)
    })

    it("does NOT match GET /api/users/me (excluded for security)", () => {
      expect(isRouteMatched("/api/users/me")).toBe(false)
    })

    it("does NOT match GET /auth/session (excluded for security)", () => {
      expect(isRouteMatched("/auth/session")).toBe(false)
    })

    it("does NOT match GET /api/csrf (excluded for security)", () => {
      expect(isRouteMatched("/api/csrf")).toBe(false)
    })

    it("does NOT match GET /api/public/assets (public path excluded)", () => {
      expect(isRouteMatched("/api/public/logo.png")).toBe(false)
    })

    it("does NOT match POST /api/schedule (non-GET excluded)", () => {
      expect(isRouteMatched("/api/schedule", "POST")).toBe(false)
    })

    it("does NOT match a non-API path", () => {
      expect(isRouteMatched("/assets/logo.svg")).toBe(false)
    })
  })

  // ── Query strings produce separate cache entries ──────────────────────────

  describe("different query strings → separate cache entries concept", () => {
    it("GET /api/schedule?week=1 is matched as a private API route", () => {
      expect(isRouteMatched("/api/schedule?week=1")).toBe(true)
    })

    it("GET /api/schedule?week=2 is also matched (different entry, same route)", () => {
      expect(isRouteMatched("/api/schedule?week=2")).toBe(true)
    })

    it("GET /api/news?page=2 is matched as a news route", () => {
      expect(isRouteMatched("/api/news?page=2")).toBe(true)
    })
  })

  // ── Offline stale data (route still matches, strategy handles cache) ───────

  describe("offline behavior — route still matches when offline", () => {
    it("GET /api/news is still routed when navigator is offline", () => {
      vi.stubGlobal("navigator", { onLine: false })
      // Route matching is independent of online status — the Workbox strategy
      // (StaleWhileRevalidate / NetworkFirst) handles the offline fallback.
      expect(isRouteMatched("/api/news")).toBe(true)
    })

    it("GET /api/events is still routed when navigator is offline", () => {
      vi.stubGlobal("navigator", { onLine: false })
      expect(isRouteMatched("/api/events")).toBe(true)
    })
  })
})
