/// <reference lib="webworker" />
import { ExpirationPlugin } from "workbox-expiration";
import { registerRoute } from "workbox-routing";
import { CacheFirst, NetworkFirst } from "workbox-strategies";

/// <reference lib="webworker" />
import { log } from "./logger";

const API_CACHE = "api-cache";
const API_CACHE_SESSION_PREFIX = `${API_CACHE}:`;

/// <reference lib="webworker" />
export function isOnline(): boolean {
  return navigator.onLine;
}

/**
 * Initialize API caching strategies.
 */
export function initApiCaching() {
  // Public API Caching (CacheFirst for static data)
  registerRoute(
    ({ url }) =>
      url.pathname.startsWith("/api/") &&
      (url.pathname.includes("/public/") || url.pathname.includes("/news")),
    new CacheFirst({
      cacheName: "api-public-cache",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 24 * 60 * 60, // 24 hours
        }),
      ],
    })
  );

  // Private/Session-aware API Caching (NetworkFirst with manual cache key management)
  registerRoute(
    ({ url }) =>
      url.pathname.startsWith("/api/") && !url.pathname.includes("/public/"),
    async ({ request, event }) => {
      const sessionId = await getSessionIdFromRequest(request);
      const cacheName = sessionId
        ? `${API_CACHE_SESSION_PREFIX}${sessionId}`
        : API_CACHE;

      const strategy = new NetworkFirst({
        cacheName,
        plugins: [
          new ExpirationPlugin({
            maxEntries: 50,
            maxAgeSeconds: 12 * 60 * 60, // 12 hours
          }),
        ],
      });

      return strategy.handle({ request, event });
    }
  );
}

/**
 * Extract session identifier from request (e.g., from cookies or auth header).
 * In a real SW, it's often better to use a BroadcastChannel or PostMessage to sync session state.
 */
async function getSessionIdFromRequest(request: Request): Promise<string | null> {
  // Logic to determine session from request headers/cookies
  // This is a placeholder for the complex logic in the original sw.ts
  const cookieHeader = request.headers.get("Cookie") || "";
  const match = cookieHeader.match(/session=([^;]+)/);
  return match ? match[1] : null;
}

/**
 * Clear all session-specific caches on logout.
 */
export async function clearSessionCaches() {
  const cacheNames = await caches.keys();
  const sessionCaches = cacheNames.filter((name) =>
    name.startsWith(API_CACHE_SESSION_PREFIX)
  );
  log("Clearing session caches", sessionCaches);
  await Promise.all(sessionCaches.map((name) => caches.delete(name)));
}
