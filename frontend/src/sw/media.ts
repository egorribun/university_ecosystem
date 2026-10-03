/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { CacheableResponsePlugin } from "workbox-cacheable-response"
import { ExpirationPlugin } from "workbox-expiration"
import { registerRoute } from "workbox-routing"
import { CacheFirst, StaleWhileRevalidate } from "workbox-strategies"

import { allowsStorage, getSessionCacheScope, ensureSessionIdentity } from "./api"

const MEDIA_PRIVATE_PREFIX = "media-private:"
const MEDIA_PUBLIC = "media-public"

/**
 * World-class media request handler with session isolation and signed URL support.
 */
export async function handleMediaRequest(
  input: RequestInfo | URL,
  event?: Event
): Promise<Response> {
  const confirmed = await ensureSessionIdentity(event)
  const request = input instanceof Request ? input : new Request(input)
  const scope = confirmed ? getSessionCacheScope() : null
  const noStore =
    request.cache === "no-store" || /\bno-store\b/i.test(request.headers.get("Cache-Control") ?? "")
  const ownsSession = () => scope === null || getSessionCacheScope() === scope
  // v2 excludes legacy signed/private responses incorrectly stored as public.
  const publicCache = await self.caches.open(`${MEDIA_PUBLIC}:v2`)
  if (!noStore) {
    const publicMatch = await publicCache.match(request)
    if (publicMatch && allowsStorage(publicMatch)) return publicMatch
    if (scope) {
      const privateCache = await self.caches.open(`${MEDIA_PRIVATE_PREFIX}${scope}`)
      const privateMatch = await privateCache.match(request)
      if (privateMatch && ownsSession() && allowsStorage(privateMatch)) return privateMatch
    }
  }

  const response = await fetch(request)
  if (!ownsSession()) return Response.error()
  if (noStore || !allowsStorage(response)) return response

  const cacheControl = response.headers.get("Cache-Control") ?? ""
  // A signed URL grants access; it does not make the response public.
  if (/\bpublic\b/i.test(cacheControl) && !/\bprivate\b/i.test(cacheControl)) {
    await publicCache.put(request, response.clone())
  } else if (scope) {
    const cacheName = `${MEDIA_PRIVATE_PREFIX}${scope}`
    const privateCache = await self.caches.open(cacheName)
    if (!ownsSession()) return Response.error()
    await privateCache.put(request, response.clone())
    if (!ownsSession()) {
      await self.caches.delete(cacheName)
      return Response.error()
    }
  }

  return response
}

/**
 * Initialize Media caching (images, avatars, static assets).
 */
export function initMediaCaching() {
  // Static assets from backend
  registerRoute(
    ({ url }) => url.pathname.startsWith("/static/"),
    new StaleWhileRevalidate({
      cacheName: "backend-static-cache",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
        }),
      ],
    })
  )

  // Explicit media requests must precede the generic image route because
  // Workbox resolves the first matching route. This preserves session isolation.
  registerRoute(
    ({ url }) => url.pathname.includes("/media/"),
    ({ request, event }) => handleMediaRequest(request, event)
  )

  // App images and icons
  registerRoute(
    ({ request }) => request.destination === "image",
    new CacheFirst({
      cacheName: "image-cache",
      plugins: [
        new CacheableResponsePlugin({
          statuses: [0, 200],
        }),
        new ExpirationPlugin({
          maxEntries: 200,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        }),
      ],
    })
  )
}
