import axios, { AxiosHeaders, type AxiosRequestConfig } from "axios"
import { client as generatedClient } from "@/api/generated/client.gen"
import { resolveSsrBackendOrigin } from "./backendOrigin"
import { applyLanguageHeader } from "./interceptors/language"
import { updateTraceContext } from "./interceptors/traceContext"
import {
  applyEtagHeader,
  handleEtagResponse,
  etagCache,
  responseCache,
  registerSigningKeyAccessor,
} from "./interceptors/etagCache"

export { registerSigningKeyAccessor }
import {
  waitForClientQueueSlot,
  releaseClientQueueSlot,
  isRateLimited,
  waitForRateLimitWindow,
  scheduleRateLimitWindow,
  RATE_LIMIT_MAX_RETRY,
} from "./interceptors/rateLimit"

export const API_UNAUTHORIZED_EVENT = "auth:unauthorized"
export const SKIP_UNAUTHORIZED_HEADER = "X-Client-Skip-Unauthorized"
const API_TIMEOUT_MS = 8000

/**
 * Endpoints that are allowed to bypass the client-side rate-limit queue.
 * Only add paths whose latency is directly user-visible during auth flows.
 * Any other endpoint with skipRateLimitQueue=true will be demoted to the queue.
 */
const RATE_LIMIT_SKIP_ALLOWLIST = new Set([
  "/auth/session/signing-key",
  "/users/me",
  "/auth/refresh",
  "/auth/token",
])

const devBase = ""
// Split SSR vs client base URL. SSR (Node, inside the deployment network) uses
// runtime BACKEND_ORIGIN with a build-time fallback. The browser uses a relative
// URL so requests flow through the edge gateway; internal service DNS is never
// exposed to clients.
const isSsrRuntime = typeof window === "undefined"
const prodBase = isSsrRuntime ? `${resolveSsrBackendOrigin()}/api/v1` : "/api/v1"

export type ApiRequestConfig<D = unknown> = AxiosRequestConfig<D> & {
  signal?: AbortSignal
  skipRateLimitQueue?: boolean
  __rateLimitRetryCount?: number
  __clientRateLimitAcquired?: boolean
  etagCacheKey?: string
}

export type TypedRequestOptions<_T extends string, _M extends string = "get"> = ApiRequestConfig

const api = axios.create({
  baseURL: import.meta.env.DEV ? devBase : prodBase,
  withCredentials: true,
  timeout: API_TIMEOUT_MS,
  xsrfCookieName: "csrf_token",
  xsrfHeaderName: "X-CSRF-Token",
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
})

if (import.meta.env.VITE_LHCI === "true") {
  const networkAdapter = axios.getAdapter(api.defaults.adapter)
  const resolveRequestPath = (config: AxiosRequestConfig): string => {
    const rawUrl = config.url ?? ""
    const rawBaseUrl = config.baseURL ?? ""
    const isAbsoluteUrl = rawUrl.includes("://") || rawUrl.startsWith("//")
    const combinedUrl = isAbsoluteUrl
      ? rawUrl
      : `${rawBaseUrl.replace(/\/+$/u, "")}/${rawUrl.replace(/^\/+/u, "")}`
    const baseOrigin = window.location.origin
    return new URL(combinedUrl, baseOrigin).pathname
  }
  const shouldUseE2ENetworkMocks = (config: AxiosRequestConfig) => {
    if (typeof window === "undefined") return false
    const e2eWindow = window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }
    if (e2eWindow.__E2E_NETWORK_API_MOCKS__ !== true) return false
    const path = resolveRequestPath(config)
    return path.startsWith("/api/v1/chats") || path === "/api/v1/users"
  }

  api.defaults.adapter = async (config) => {
    if (shouldUseE2ENetworkMocks(config)) {
      return networkAdapter(config)
    }
    return {
      data: { items: [] }, // Provide a safe default object/array combo
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
      request: {},
    }
  }
}

// Hook the generated client to our customized axios instance
generatedClient.setConfig({
  axios: api,
  // The generated singleton starts with baseURL="/". Keeping that value
  // makes its URL builder concatenate "/" + "/api/v1/..." into the
  // protocol-relative "//api/v1/...", which browsers interpret as host
  // "api". An empty override delegates base URL ownership to our configured
  // Axios instance; the interceptor below then normalizes the duplicated API
  // prefix while preserving a same-origin path.
  baseURL: "",
})

export const resetEtagCache = () => {
  etagCache.clear()
  responseCache.clear()
}

const isAbortError = (error: unknown) => {
  if (error instanceof DOMException) return error.name === "AbortError"
  if (error !== null && typeof error === "object" && "name" in error) {
    const { name } = error
    return name === "CanceledError" || name === "AbortError"
  }
  return false
}

// TD-14-04 (audit Wave 14): Extracted — was hardcoded as 2000 in three places.
const DEFAULT_RETRY_AFTER_MS = 2000

const getRetryDelay = (headers: Record<string, unknown> | undefined) => {
  if (!headers) return DEFAULT_RETRY_AFTER_MS
  const header = headers["retry-after"] ?? headers["Retry-After"]
  if (typeof header !== "string") return DEFAULT_RETRY_AFTER_MS
  const numeric = Number.parseFloat(header)
  return Number.isFinite(numeric) ? Math.max(0, numeric * 1000) : DEFAULT_RETRY_AFTER_MS
}

// PERF-14-05 (audit Wave 14): Client-side mutation deduplication.
// TanStack Query deduplicates queries but not mutations.  If a user double-clicks
// before UI debounce fires, two identical POST requests go out.  The backend
// idempotency key handles this server-side, but the duplicate still wastes bandwidth.
// We suppress the duplicate on the client by tracking in-flight Idempotency-Keys.
const _inflightIdempotencyKeys = new Set<string>()

// TD-31-04: Synchronize in-flight idempotency keys across tabs via BroadcastChannel.
// Prevents duplicate mutations when two tabs submit the same form simultaneously.
// Server-side idempotency key is the authoritative check — this is defense-in-depth.
let _dedupeChannel: BroadcastChannel | null = null
try {
  if (typeof BroadcastChannel !== "undefined") {
    _dedupeChannel = new BroadcastChannel("ecosystem.idempotency.dedup")
    _dedupeChannel.addEventListener(
      "message",
      (e: MessageEvent<{ key: string; action: "add" | "delete" }>) => {
        if (e.data.action === "add") _inflightIdempotencyKeys.add(e.data.key)
        else _inflightIdempotencyKeys.delete(e.data.key)
      }
    )
  }
} catch {
  // BroadcastChannel not available (SSR, old browsers, Web Workers).
}

// Wave 174 SW2 — CSRF cookie auto-acquisition.
//
// Axios's built-in XSRF mechanism (xsrfCookieName + xsrfHeaderName above)
// reads the `csrf_token` cookie and sets `X-CSRF-Token` header on outgoing
// requests. If the cookie is MISSING (first-time visitor OR cookie expired
// per the backend's 30-min Max-Age) axios sends NO header, and the
// CSRFMiddleware (`app/core/csrf.py` + `middleware/setup.py:47-60`) rejects
// the request with 403 "Несоответствие CSRF-токена". Pre-W174 SW2 the
// frontend had no proactive CSRF acquisition — real users only succeeded
// because they had a `csrf_token` cookie persisted from a prior session.
// After 30+ min idle the cookie expires and login would fail with 403.
//
// Backend exposes GET `/api/v1/auth/csrf-cookie` which idempotently sets
// the cookie (no body, just `Set-Cookie: csrf_token=...; Max-Age=1800;`).
// This helper fetches that endpoint at most ONCE per page session — the
// singleton Promise dedupes concurrent unsafe requests so the helper
// makes one network call even when many POSTs fire simultaneously.
let _csrfBootstrapPromise: Promise<void> | null = null
// Wave 175 SW9 — exported for regression tests in
// frontend/src/api/__tests__/ensureCsrfCookie.test.ts. The interceptor
// uses this function directly (no API surface change for callers).
export const ensureCsrfCookie = (): Promise<void> => {
  // SSR guard — server has no document.cookie, and outgoing axios on the
  // Node runtime gets the Cookie header via W133 SW1 globalThis.__ssrCookieGetter__
  // (the SSR caller already has the cookie chain from the incoming request).
  if (typeof document === "undefined") return Promise.resolve()
  // LHCI builds use a deterministic, side-effect-free Axios adapter and do
  // not have a backend service behind the preview server.  Do not bypass that
  // contract with a real browser `fetch` which can wait for the network
  // timeout on every audited route; production builds never set this flag.
  if (import.meta.env.VITE_LHCI === "true") return Promise.resolve()
  // Test env skip — vitest sets `import.meta.env.MODE === "test"` and tests
  // mount AuthContext.Provider with real auth (mocked). Hitting the CSRF
  // endpoint in tests would trip MSW unhandled-request warnings + risk
  // cross-test singleton pollution. Vite literal-substitutes `MODE` at
  // build time, so this branch tree-shakes from prod (verifiable via
  // `grep -l "MODE === \"test\"" dist/client/assets/*.js` returning empty).
  if (import.meta.env.MODE === "test") return Promise.resolve()
  if (document.cookie.includes("csrf_token=")) return Promise.resolve()
  if (_csrfBootstrapPromise) return _csrfBootstrapPromise
  _csrfBootstrapPromise = fetch("/api/v1/auth/csrf-cookie", {
    method: "GET",
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(() => undefined)
    .catch(() => undefined) // best-effort — backend will still 403 if cookie fails to set
    .finally(() => {
      _csrfBootstrapPromise = null
    })
  return _csrfBootstrapPromise
}

api.interceptors.request.use(async (config) => {
  const candidate = config as ApiRequestConfig

  // FIX-44-01: Normalize doubled /api/v1 prefix.
  // The @hey-api/client-axios `buildUrl()` reads our axios instance's baseURL ("/api/v1")
  // and prepends it to the SDK URL (also "/api/v1/..."), producing "/api/v1/api/v1/...".
  // It then passes `baseURL: ""` to axios, so we detect the doubled prefix in the URL itself.
  const _url = config.url ?? ""
  const isAbsolute = _url.startsWith("http://") || _url.startsWith("https://")
  let urlPath = _url
  let urlOrigin = ""
  if (isAbsolute) {
    try {
      const parsed = new URL(_url)
      urlPath = parsed.pathname + parsed.search
      urlOrigin = parsed.origin
    } catch {
      // fallback if URL parsing fails
    }
  }

  if (urlPath.startsWith("/api/v1/api/v1/")) {
    urlPath = urlPath.slice("/api/v1".length)
    config.url = urlOrigin + urlPath
  } else if (urlPath.startsWith("/api/v1/") && config.baseURL?.includes("/api/v1")) {
    urlPath = urlPath.slice("/api/v1".length)
    config.url = urlOrigin + urlPath
  }

  // Mutation dedup: reject duplicate in-flight requests with the same Idempotency-Key.
  if (config.method && ["post", "put", "patch", "delete"].includes(config.method)) {
    const requestHeaders = AxiosHeaders.from(config.headers ?? {})
    const idempotencyKey = requestHeaders.get("Idempotency-Key") as string | undefined
    if (idempotencyKey && _inflightIdempotencyKeys.has(idempotencyKey)) {
      return Promise.reject(new axios.Cancel("Duplicate mutation suppressed (client-side dedup)"))
    }
    if (idempotencyKey) {
      _inflightIdempotencyKeys.add(idempotencyKey)
      _dedupeChannel?.postMessage({ key: idempotencyKey, action: "add" })
    }

    // Wave 174 SW2 — ensure CSRF cookie BEFORE unsafe-method request goes
    // out. Skip the /auth/csrf-cookie endpoint itself to avoid recursion
    // (it's a GET anyway, so this branch wouldn't fire — guard is defensive).
    const urlForCsrf = config.url ?? ""
    if (!urlForCsrf.includes("/auth/csrf-cookie")) {
      await ensureCsrfCookie()
    }
  }

  // Guard the bypass flag: only allowlisted URLs may skip the rate-limit queue.
  if (candidate.skipRateLimitQueue) {
    const url = candidate.url ?? ""
    if (!RATE_LIMIT_SKIP_ALLOWLIST.has(url)) {
      if (import.meta.env.DEV) {
        console.warn(`[rateLimit] skipRateLimitQueue=true for non-allowlisted URL: ${url}`)
      }
      candidate.skipRateLimitQueue = false
    }
  }

  // The queue is process-global. Applying it during SSR combines requests
  // from independent visitors and can delay the HTML response past its timeout.
  if (!isSsrRuntime && !candidate.skipRateLimitQueue) {
    // @ts-expect-error - axios config bridge
    await waitForClientQueueSlot(candidate)
  }

  if (!isSsrRuntime && isRateLimited()) {
    await waitForRateLimitWindow(config.signal as AbortSignal | undefined)
  }

  applyLanguageHeader(config)

  if (candidate.etagCacheKey) {
    applyEtagHeader(config, candidate.etagCacheKey)
  }

  // Wave 133 SW1 — SSR cookie forwarding. On Node SSR runtime, the
  // `access_token_v2` HttpOnly cookie isn't auto-forwarded by axios
  // (`withCredentials: true` only applies in browsers). `frontend/src/server.ts`
  // stashes the raw incoming `Cookie` header in `requestCookieStorage` per-
  // request; we read it via the globalThis getter and set it on the outgoing
  // config. Browser path is provably unaffected: `typeof window === "undefined"`
  // is statically false in client bundles, so the branch dead-codes out of
  // browser tree-shake (Vite environments build keeps cookie-forwarding logic
  // in the server chunk only). NEVER log or surface the raw cookie value — it
  // contains the access_token_v2 HttpOnly cookie.
  if (typeof window === "undefined") {
    const cookie = globalThis.__ssrCookieGetter__?.()
    const fingerprintHeaders = globalThis.__ssrFingerprintHeadersGetter__?.()
    if (cookie || fingerprintHeaders) {
      const headers = AxiosHeaders.from(config.headers)
      if (cookie && cookie.length > 0) {
        headers.set("Cookie", cookie)
      }
      if (fingerprintHeaders?.userAgent) {
        headers.set("User-Agent", fingerprintHeaders.userAgent)
      }
      if (fingerprintHeaders?.acceptLanguage) {
        headers.set("Accept-Language", fingerprintHeaders.acceptLanguage)
      }
      config.headers = headers
    }
  }

  if (config.data instanceof FormData) {
    const headers = AxiosHeaders.from(config.headers)
    headers.delete("Content-Type")
    config.headers = headers
  }

  return config
})

// PERF-14-05: Helper to clean up in-flight idempotency key tracking.
const _cleanupIdempotencyKey = (config: ApiRequestConfig | undefined) => {
  if (!config?.headers) return
  const key =
    config.headers instanceof AxiosHeaders
      ? (config.headers.get("Idempotency-Key") as string | undefined)
      : undefined
  if (key) {
    _inflightIdempotencyKeys.delete(key)
    _dedupeChannel?.postMessage({ key, action: "delete" })
  }
}

api.interceptors.response.use(
  async (response) => {
    const config = response.config as ApiRequestConfig | undefined
    _cleanupIdempotencyKey(config)
    if (config?.etagCacheKey) {
      await handleEtagResponse(response, config.etagCacheKey)
    }
    updateTraceContext(response.headers as AxiosHeaders)
    // @ts-expect-error - axios config bridge
    releaseClientQueueSlot(config)
    return response
  },
  async (error) => {
    const config = error?.config as ApiRequestConfig | undefined
    const responseStatus = error?.response?.status
    _cleanupIdempotencyKey(config)
    // @ts-expect-error - axios config bridge
    releaseClientQueueSlot(config)

    if (error?.response?.headers) {
      updateTraceContext(error.response.headers as AxiosHeaders)
    }

    if (config?.etagCacheKey && responseStatus >= 400) {
      etagCache.delete(config.etagCacheKey)
    }

    if (responseStatus === 429 && config && !config.skipRateLimitQueue) {
      const delay = getRetryDelay(error.response.headers)
      scheduleRateLimitWindow(delay)

      const retryCount = config.__rateLimitRetryCount ?? 0
      if (retryCount < RATE_LIMIT_MAX_RETRY && !config.signal?.aborted && !isAbortError(error)) {
        config.__rateLimitRetryCount = retryCount + 1
        // RZ-31-04: Propagate AbortSignal so navigation cancels the wait.
        await waitForRateLimitWindow(config.signal)
        return api.request(config)
      }
    }

    if (responseStatus === 401) {
      const headers = (config?.headers ?? {}) as Record<string, unknown>
      if (headers[SKIP_UNAUTHORIZED_HEADER]) {
        delete headers[SKIP_UNAUTHORIZED_HEADER]
        return Promise.reject(error)
      }
      // DEBT-02: Removed legacy `window.dispatchEvent` workaround.
      // 401s are now handled via declarative error boundaries and React Query conventions.
    }
    return Promise.reject(error)
  }
)

export default api
