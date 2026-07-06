/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { CacheableResponsePlugin } from "workbox-cacheable-response"
import { ExpirationPlugin } from "workbox-expiration"
import { registerRoute } from "workbox-routing"
import { CacheFirst, StaleWhileRevalidate } from "workbox-strategies"

import { getSessionHash } from "./api"

const MEDIA_PRIVATE_PREFIX = "media-private:"
const MEDIA_PUBLIC = "media-public"

/**
 * World-class media request handler with session isolation and signed URL support.
 */
export async function handleMediaRequest(input: RequestInfo | URL): Promise<Response> {
  const request = input instanceof Request ? input : new Request(input)
  const sessionHash = getSessionHash()

  // 1. Try public cache first for everything (shared assets)
  const publicCache = await self.caches.open(MEDIA_PUBLIC)
  const publicMatch = await publicCache.match(request)
  if (publicMatch) return publicMatch

  // 2. Try session-specific cache if authenticated
  if (sessionHash) {
    const privateCacheName = `${MEDIA_PRIVATE_PREFIX}${sessionHash}`
    if (await self.caches.has(privateCacheName)) {
      const privateCache = await self.caches.open(privateCacheName)
      const privateMatch = await privateCache.match(request)
      if (privateMatch) return privateMatch
    }
  }

  // 3. Network fetch
  const response = await fetch(request)
  if (!response.ok) return response

  const isSigned = response.headers.get("x-media-signed-url") === "true"
  const cacheControl = response.headers.get("Cache-Control") || ""
  const isPublic = cacheControl.includes("public") || isSigned

  if (isPublic) {
    await publicCache.put(request, response.clone())
  } else if (sessionHash && cacheControl.includes("private")) {
    const privateCache = await self.caches.open(`${MEDIA_PRIVATE_PREFIX}${sessionHash}`)
    await privateCache.put(request, response.clone())
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

  // Explicit media requests (often used in tests)
  registerRoute(
    ({ url }) => url.pathname.includes("/media/"),
    ({ request }) => handleMediaRequest(request)
  )
}
