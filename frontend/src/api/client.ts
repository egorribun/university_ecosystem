import axios, { AxiosHeaders, type AxiosRequestConfig } from "axios"
import { client as generatedClient } from "@/api/generated/client.gen"
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
const prodBase = `${import.meta.env.VITE_BACKEND_ORIGIN || ""}/api/v1`

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

// Hook the generated client to our customized axios instance
generatedClient.setConfig({
  axios: api,
})

export const resetEtagCache = () => {
  etagCache.clear()
  responseCache.clear()
}

const isAbortError = (error: unknown) => {
  if (!error) return false
  if (error instanceof DOMException) return error.name === "AbortError"
  if (typeof error === "object" && "name" in error) {
    const name = (error as { name?: string }).name
    return name === "CanceledError" || name === "AbortError"
  }
  return false
}

const getRetryDelay = (headers: Record<string, unknown> | undefined) => {
  if (!headers) return 2000
  const header = headers["retry-after"] ?? headers["Retry-After"]
  if (typeof header !== "string") return 2000
  const numeric = Number.parseFloat(header)
  return Number.isFinite(numeric) ? Math.max(0, numeric * 1000) : 2000
}

api.interceptors.request.use(async (config) => {
  const candidate = config as ApiRequestConfig

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

  if (!candidate.skipRateLimitQueue) {
    // @ts-expect-error - axios config bridge
    await waitForClientQueueSlot(candidate)
  }

  if (isRateLimited()) {
    await waitForRateLimitWindow()
  }

  applyLanguageHeader(config)

  if (candidate.etagCacheKey) {
    applyEtagHeader(config, candidate.etagCacheKey)
  }

  if (config.data instanceof FormData) {
    const headers = AxiosHeaders.from(config.headers ?? {})
    headers.delete("Content-Type")
    config.headers = headers
  }

  return config
})

api.interceptors.response.use(
  async (response) => {
    const config = response.config as ApiRequestConfig | undefined
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
    // @ts-expect-error - axios config bridge
    releaseClientQueueSlot(config)

    if (error?.response?.headers) {
      updateTraceContext(error.response.headers as AxiosHeaders)
    }

    if (config?.etagCacheKey && error?.response?.status >= 400 && error.response.status !== 304) {
      etagCache.delete(config.etagCacheKey)
    }

    if (error?.response?.status === 429 && config && !config.skipRateLimitQueue) {
      const delay = getRetryDelay(error.response?.headers)
      scheduleRateLimitWindow(delay)

      const retryCount = config.__rateLimitRetryCount ?? 0
      if (retryCount < RATE_LIMIT_MAX_RETRY && !config.signal?.aborted && !isAbortError(error)) {
        config.__rateLimitRetryCount = retryCount + 1
        await waitForRateLimitWindow()
        return api.request(config)
      }
    }

    if (error?.response?.status === 401) {
      const headers = (config?.headers ?? {}) as Record<string, unknown>
      if (headers[SKIP_UNAUTHORIZED_HEADER]) {
        delete headers[SKIP_UNAUTHORIZED_HEADER]
        return Promise.reject(error)
      }
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(API_UNAUTHORIZED_EVENT))
      }
    }
    return Promise.reject(error)
  }
)

/**
 * DEPRECATED: Use the generated SDK from @/api/generated instead.
 * This manual TypedApiClient is kept for backward compatibility during migration.
 */
export const apiClient = {
  get: <T = unknown>(url: string, config?: AxiosRequestConfig) => api.get<T>(url, config),
  post: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    api.post<T>(url, data, config),
  put: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    api.put<T>(url, data, config),
  patch: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    api.patch<T>(url, data, config),
  delete: (url: string, config?: AxiosRequestConfig) => api.delete(url, config),
  request: (config: AxiosRequestConfig) => api.request(config),
}

export default api
