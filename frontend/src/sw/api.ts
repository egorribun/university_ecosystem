/// <reference lib="webworker" />
// No global self declaration needed with webworker lib
export {}
import { CacheableResponsePlugin } from "workbox-cacheable-response"
import { ExpirationPlugin } from "workbox-expiration"
import { registerRoute } from "workbox-routing"
import { NetworkFirst, StaleWhileRevalidate } from "workbox-strategies"

import { log } from "./logger"

const API_CACHE = "api-cache"
const API_CACHE_SESSION_PREFIX = `${API_CACHE}:`

let currentSessionHash: string | null = null

export function setSessionHash(hash: string | null) {
  currentSessionHash = hash
}

export function getSessionHash() {
  return currentSessionHash
}

export function isOnline(): boolean {
  return navigator.onLine
}

/**
 * Initialize API caching strategies.
 *
 * Strategy breakdown:
 * - NetworkFirst for interactions (likes, comments) - always fresh data
 * - StaleWhileRevalidate for news/events lists - instant display + background update
 * - NetworkFirst for private/session-aware APIs
 */
export function initApiCaching() {
  // News interactions (likes, comments) - always try network first
  // These endpoints need fresh data to show accurate counts
  registerRoute(
    ({ url, request }) =>
      url.pathname.startsWith("/api/") &&
      url.pathname.includes("/news") &&
      (url.pathname.includes("/like") ||
        url.pathname.includes("/comment") ||
        url.pathname.includes("/interactions") ||
        request.method !== "GET"),
    new NetworkFirst({
      cacheName: "api-news-interactions",
      networkTimeoutSeconds: 5,
      plugins: [
        new CacheableResponsePlugin({
          statuses: [0, 200],
        }),
        new ExpirationPlugin({
          maxEntries: 50,
          maxAgeSeconds: 60, // 1 minute cache for offline fallback only
        }),
      ],
    })
  )

  // News list and detail - StaleWhileRevalidate for instant display + background update
  // Shows cached data immediately, then updates cache in background for next request
  registerRoute(
    ({ url, request }) =>
      url.pathname.startsWith("/api/") &&
      url.pathname.includes("/news") &&
      request.method === "GET" &&
      !url.pathname.includes("/like") &&
      !url.pathname.includes("/comment") &&
      !url.pathname.includes("/interactions"),
    new StaleWhileRevalidate({
      cacheName: "api-news-cache",
      plugins: [
        new CacheableResponsePlugin({
          statuses: [0, 200],
        }),
        new ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 5 * 60, // 5 minutes
        }),
      ],
    })
  )

  // Events API - StaleWhileRevalidate for same behavior as news
  registerRoute(
    ({ url, request }) =>
      url.pathname.startsWith("/api/") &&
      url.pathname.includes("/events") &&
      request.method === "GET",
    new StaleWhileRevalidate({
      cacheName: "api-events-cache",
      plugins: [
        new CacheableResponsePlugin({
          statuses: [0, 200],
        }),
        new ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 5 * 60, // 5 minutes
        }),
      ],
    })
  )

  // Private/Session-aware API Caching (NetworkFirst with session-based cache keys)
  registerRoute(
    ({ url, request }) =>
      url.pathname.startsWith("/api/") &&
      !url.pathname.includes("/public/") &&
      !url.pathname.includes("/news") &&
      !url.pathname.includes("/events") &&
      // W150 polish-followup-v2 — auth-state-critical paths bypass SW.
      // /users/me, /auth/*, /csrf MUST never be cached (security: a stale
      // 200 could let an unauthenticated user appear authenticated) AND
      // must never be intercepted (workbox NetworkFirst's
      // networkTimeoutSeconds:5 empirically does NOT fire here, leaving
      // requests pending indefinitely → blocks AuthProvider's
      // useProfileSync from resolving → blank page until tab closes).
      // Verified via chrome-devtools-mcp + user real Chrome 2026-05-14.
      // Closes W150 §Honesty caveat #16.
      !url.pathname.includes("/users/me") &&
      !url.pathname.includes("/auth/") &&
      !url.pathname.includes("/csrf") &&
      request.method === "GET",
    async ({ request, event }) => {
      const sessionId = await getSessionIdFromRequest(request)
      const cacheName = sessionId ? `${API_CACHE_SESSION_PREFIX}${sessionId}` : API_CACHE

      const strategy = new NetworkFirst({
        cacheName,
        networkTimeoutSeconds: 5,
        plugins: [
          new CacheableResponsePlugin({
            statuses: [0, 200],
          }),
          new ExpirationPlugin({
            maxEntries: 50,
            maxAgeSeconds: 60 * 60, // 1 hour
          }),
        ],
      })

      // W150 polish-followup-v2 — hard 6s timeout wrapper as defense-in-depth
      // for the remaining /api/* paths still under NetworkFirst. Workbox's
      // networkTimeoutSeconds doesn't fire reliably under specific cache+plugin
      // interactions (verified 2026-05-14 against /users/me before route
      // exclusion above). Promise.race guarantees the browser request resolves
      // within 6s regardless — returning a synthetic 504 axios can surface as a
      // network error instead of an indefinite pending state. Adds anti-pattern
      // #16 candidate: workbox NetworkFirst on critical endpoints — fix is
      // route exclusion, not strategy tuning.
      return Promise.race([
        strategy.handle({ request, event }),
        new Promise<Response>((resolve) =>
          setTimeout(
            () =>
              resolve(
                new Response(JSON.stringify({ error: "sw_timeout" }), {
                  status: 504,
                  statusText: "Service Worker Timeout",
                  headers: { "Content-Type": "application/json" },
                })
              ),
            6000
          )
        ),
      ])
    }
  )
}

/**
 * Extract session identifier from request (e.g., from cookies or auth header).
 */
async function getSessionIdFromRequest(request: Request): Promise<string | null> {
  const cookieHeader = request.headers.get("Cookie") || ""
  const match = cookieHeader.match(/session=([^;]+)/)
  return match?.[1] ?? null
}

/**
 * Clear all session-specific caches on logout.
 */
export async function clearSessionCaches() {
  const cacheNames = await caches.keys()
  const sessionCaches = cacheNames.filter(
    (name) =>
      name.startsWith(API_CACHE_SESSION_PREFIX) ||
      name === "api-news-cache" ||
      name === "api-news-interactions" ||
      name === "api-events-cache"
  )
  log("Clearing session caches", sessionCaches)
  await Promise.all(sessionCaches.map((name) => caches.delete(name)))
}
