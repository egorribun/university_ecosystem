/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope
import { SERVICE_WORKER_MESSAGE_TYPES } from "../constants/serviceWorkerMessages"
import type { WorkboxPlugin } from "workbox-core"
import { ExpirationPlugin } from "workbox-expiration"
import { registerRoute } from "workbox-routing"
import { NetworkFirst } from "workbox-strategies"

const API_CACHE = "api-cache"
let currentSessionHash: string | null = null
let currentSessionScope: string | null = null
let sessionEpoch = 0

/** A fresh scope on every identity transition fences writes from an older session,
 * including a logout/login to the same account and a cold worker restart. */
export function setSessionHash(hash: string | null, restoredScope?: string) {
  const next = typeof hash === "string" && hash.trim() && hash.length <= 128 ? hash : null
  const scope =
    restoredScope && next && restoredScope.startsWith(`${next}:`) && restoredScope.length <= 256
      ? restoredScope
      : undefined
  if (next === currentSessionHash && (!scope || scope === currentSessionScope)) return
  sessionEpoch += 1
  currentSessionHash = next
  currentSessionScope = next ? (scope ?? `${next}:${crypto.randomUUID()}`) : null
}

/** A restarted worker has no trusted identity. Ask the requesting, controlled
 * window for its still-live in-memory session; never restore identity from disk. */
export async function ensureSessionIdentity(event?: Event): Promise<boolean> {
  const clientId = (event as FetchEvent | undefined)?.clientId
  if (!clientId || typeof self.clients?.get !== "function") return false
  const epoch = sessionEpoch
  const client = await self.clients.get(clientId)
  if (!client || client.type !== "window" || epoch !== sessionEpoch) return false
  const channel = new MessageChannel()
  let timer: ReturnType<typeof setTimeout> | undefined
  return new Promise<boolean>((resolve) => {
    timer = setTimeout(() => resolve(false), 1000)
    channel.port1.onmessage = ({ data }) => {
      clearTimeout(timer)
      if (
        epoch === sessionEpoch &&
        data &&
        typeof data.sessionHash === "string" &&
        typeof data.sessionScope === "string" &&
        data.sessionScope.startsWith(`${data.sessionHash}:`)
      ) {
        setSessionHash(data.sessionHash, data.sessionScope)
        resolve(currentSessionScope === data.sessionScope)
      } else resolve(false)
    }
    client.postMessage({ type: SERVICE_WORKER_MESSAGE_TYPES.REQUEST_API_SESSION_CACHE_KEY }, [
      channel.port2,
    ])
  }).finally(() => {
    clearTimeout(timer)
    channel.port1.close()
    channel.port2.close()
  })
}

export async function purgeLegacyCaches() {
  const names = await caches.keys()
  await Promise.all(
    names
      .filter((name) =>
        [
          "api-cache",
          "api-news-cache",
          "api-news-interactions",
          "api-events-cache",
          "media-public",
        ].includes(name)
      )
      .map((name) => caches.delete(name))
  )
}

export function getSessionHash() {
  return currentSessionHash
}

export function getSessionCacheScope() {
  return currentSessionScope
}

export function isOnline(): boolean {
  return navigator.onLine
}

export function allowsStorage(response: Response): boolean {
  return (
    response.status === 200 &&
    !/\b(?:no-store|no-cache)\b/i.test(response.headers.get("Cache-Control") ?? "")
  )
}

/** Applies to every private response, including events, attendance, attachments
 * and news interactions. Cookies (especially HttpOnly cookies) are not identity. */
function sessionCachePlugin(scope: string, cacheName: string): WorkboxPlugin {
  const epoch = sessionEpoch
  const ownsSession = () => currentSessionScope === scope && sessionEpoch === epoch
  return {
    cacheWillUpdate: async ({ response }) =>
      ownsSession() && allowsStorage(response) ? response : null,
    cachedResponseWillBeUsed: async ({ cachedResponse }) =>
      ownsSession() && cachedResponse && allowsStorage(cachedResponse) ? cachedResponse : null,
    cacheDidUpdate: async () => {
      // cache.put is asynchronous: a logout may finish while it is writing.
      if (!ownsSession()) await caches.delete(cacheName)
    },
    fetchDidSucceed: async ({ response, request }) => {
      if (!ownsSession()) return Response.error()
      if (response.status === 401) {
        await clearSessionCaches()
      } else if (!allowsStorage(response)) {
        // A new no-store response also invalidates a previously cacheable copy.
        const cache = await caches.open(cacheName)
        await cache.delete(request)
      }
      return response
    },
  }
}

export function initApiCaching() {
  registerRoute(
    ({ url, request }) =>
      url.pathname.startsWith("/api/") &&
      !url.pathname.includes("/public/") &&
      // Authentication probes must reach the server without SW interception.
      !url.pathname.includes("/users/me") &&
      !url.pathname.includes("/auth/") &&
      !url.pathname.includes("/csrf") &&
      request.method === "GET",
    async ({ request, event }) => {
      const confirmed = await ensureSessionIdentity(event)
      const epoch = sessionEpoch
      const scope = currentSessionScope
      // Fail closed until this worker receives a confirmed session identity.
      if (
        !confirmed ||
        !scope ||
        request.cache === "no-store" ||
        /\bno-store\b/i.test(request.headers.get("Cache-Control") ?? "")
      )
        return fetch(request)
      const cacheName = `${API_CACHE}:${scope}`
      const strategy = new NetworkFirst({
        cacheName,
        networkTimeoutSeconds: 5,
        plugins: [
          sessionCachePlugin(scope, cacheName),
          new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 60 * 60 }),
        ],
      })
      let timer: ReturnType<typeof setTimeout> | undefined
      try {
        const response = await Promise.race([
          strategy.handle({ request, event }),
          new Promise<Response>((resolve) => {
            timer = setTimeout(
              () =>
                resolve(
                  new Response(JSON.stringify({ error: "sw_timeout" }), {
                    status: 504,
                    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
                  })
                ),
              6000
            )
          }),
        ])
        return (currentSessionScope === scope && sessionEpoch === epoch) ||
          (response.status === 401 && currentSessionScope === null)
          ? response
          : Response.error()
      } finally {
        clearTimeout(timer)
      }
    }
  )
}

/** Purge legacy unscoped copies as well as retired session namespaces. Identity
 * is reset synchronously, before the first IndexedDB/CacheStorage await. */
export async function clearSessionCaches() {
  sessionEpoch += 1
  setSessionHash(null)
  const cacheNames = await caches.keys()
  await Promise.all(
    cacheNames
      .filter(
        (name) =>
          (name === API_CACHE ||
            name.startsWith(`${API_CACHE}:`) ||
            name.startsWith("media-private:") ||
            name === "media-public" ||
            name === "api-news-cache" ||
            name === "api-news-interactions" ||
            name === "api-events-cache") &&
          // A newer login may already own a fresh scope while this purge is pending.
          (!currentSessionScope || !name.endsWith(`:${currentSessionScope}`))
      )
      .map((name) => caches.delete(name))
  )
}
