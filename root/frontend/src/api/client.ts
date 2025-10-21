import axios, {
  AxiosHeaders,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
} from "axios"
import i18n, { fallbackLng, supportedLngs } from "@/i18n/config"

export const API_UNAUTHORIZED_EVENT = "auth:unauthorized"
export const SKIP_UNAUTHORIZED_HEADER = "X-Client-Skip-Unauthorized"

const devBase = "/api"
const prodBase = import.meta.env.VITE_BACKEND_ORIGIN || "/api"

export type ApiRequestConfig<D = unknown> = AxiosRequestConfig<D> & {
  signal?: AbortSignal
  /**
   * Skip the client-side rate-limit queue. Only use for requests that must not
   * be throttled.
   */
  skipRateLimitQueue?: boolean
  /**
   * Internal retry counter used by the rate-limit middleware.
   */
  __rateLimitRetryCount?: number
}

type ApiInstance = Omit<AxiosInstance, "get" | "delete" | "post" | "patch" | "put"> & {
  get<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    config?: ApiRequestConfig<D>
  ): Promise<R>
  delete<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    config?: ApiRequestConfig<D>
  ): Promise<R>
  post<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    data?: D,
    config?: ApiRequestConfig<D>
  ): Promise<R>
  patch<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    data?: D,
    config?: ApiRequestConfig<D>
  ): Promise<R>
  put<T = unknown, R = AxiosResponse<T>, D = unknown>(
    url: string,
    data?: D,
    config?: ApiRequestConfig<D>
  ): Promise<R>
}

const api: ApiInstance = axios.create({
  baseURL: import.meta.env.DEV ? devBase : prodBase,
  withCredentials: true,
  timeout: 8000,
  xsrfCookieName: "XSRF-TOKEN",
  xsrfHeaderName: "X-XSRF-TOKEN",
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
}) as ApiInstance

const acceptLanguageHeader = "Accept-Language"

const RATE_LIMIT_DEFAULT_DELAY_MS = 2000
const RATE_LIMIT_MAX_RETRY = 2

let rateLimitResetAt = 0
let rateLimitTimer: ReturnType<typeof setTimeout> | null = null
const rateLimitWaiters: Array<() => void> = []

const isAbortError = (error: unknown) => {
  if (!error) return false
  if (error instanceof DOMException) {
    return error.name === "AbortError"
  }
  if (typeof error === "object" && "name" in error) {
    const name = (error as { name?: string }).name
    return name === "CanceledError" || name === "AbortError"
  }
  return false
}

const scheduleRateLimitWindow = (delayMs: number) => {
  const target = Date.now() + Math.max(delayMs, 0)
  if (rateLimitTimer && target <= rateLimitResetAt) {
    return
  }

  rateLimitResetAt = target

  if (rateLimitTimer) {
    clearTimeout(rateLimitTimer)
    rateLimitTimer = null
  }

  rateLimitTimer = setTimeout(
    () => {
      rateLimitTimer = null
      rateLimitResetAt = 0
      while (rateLimitWaiters.length > 0) {
        const resolve = rateLimitWaiters.shift()
        resolve?.()
      }
    },
    Math.max(0, target - Date.now())
  )
}

const waitForRateLimitWindow = async () => {
  if (rateLimitResetAt <= Date.now()) {
    return
  }

  await new Promise<void>((resolve) => {
    rateLimitWaiters.push(resolve)
  })
}

const parseRetryAfterHeader = (raw: unknown): number | null => {
  if (typeof raw !== "string") return null
  const trimmed = raw.trim()
  if (!trimmed) return null

  const numeric = Number.parseFloat(trimmed)
  if (Number.isFinite(numeric) && numeric >= 0) {
    return Math.max(0, numeric * 1000)
  }

  const parsedDate = Date.parse(trimmed)
  if (!Number.isNaN(parsedDate)) {
    const diff = parsedDate - Date.now()
    if (diff > 0) {
      return diff
    }
  }

  return null
}

const getRetryDelay = (headers: Record<string, unknown> | undefined) => {
  if (!headers) return RATE_LIMIT_DEFAULT_DELAY_MS
  const header = headers["retry-after"] ?? headers["Retry-After"]
  const parsed = parseRetryAfterHeader(header)
  return parsed ?? RATE_LIMIT_DEFAULT_DELAY_MS
}

const normalizeLanguageCandidate = (candidate: string) =>
  candidate.toLowerCase().replace(/_/g, "-").split(",", 1)[0]?.trim() ?? ""

const resolveAcceptLanguage = (language?: string) => {
  const fallbackLanguage = fallbackLng
  if (!language) return fallbackLanguage

  const normalized = normalizeLanguageCandidate(language)
  if (!normalized) return fallbackLanguage

  const supportedMatch = supportedLngs.find((locale) => {
    const normalizedLocale = locale.toLowerCase()
    return normalized === normalizedLocale || normalized.startsWith(`${normalizedLocale}-`)
  })

  return supportedMatch ?? fallbackLanguage
}

api.interceptors.request.use((config) => {
  const candidate = config as ApiRequestConfig
  if (!candidate.skipRateLimitQueue && rateLimitResetAt > Date.now()) {
    return waitForRateLimitWindow().then(() => config)
  }

  const currentLanguage = i18n.language || i18n.resolvedLanguage || fallbackLng
  const headerValue = resolveAcceptLanguage(currentLanguage)

  const headers = AxiosHeaders.from(config.headers ?? {})

  if (!headers.has(acceptLanguageHeader) && !headers.has(acceptLanguageHeader.toLowerCase())) {
    headers.set(acceptLanguageHeader, headerValue)
  }

  config.headers = headers

  return config
})

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    if (err?.response?.status === 429 && err.config) {
      const config = err.config as ApiRequestConfig
      if (!config.skipRateLimitQueue) {
        const delay = getRetryDelay(err.response?.headers)
        scheduleRateLimitWindow(delay)

        const retryCount = config.__rateLimitRetryCount ?? 0
        if (retryCount < RATE_LIMIT_MAX_RETRY && !config.signal?.aborted && !isAbortError(err)) {
          config.__rateLimitRetryCount = retryCount + 1
          await waitForRateLimitWindow()
          return api.request(config)
        }
      }
    }

    if (err?.response?.status === 401) {
      const headers = (err.config?.headers ?? {}) as Record<string, unknown>
      if (headers[SKIP_UNAUTHORIZED_HEADER]) {
        delete headers[SKIP_UNAUTHORIZED_HEADER]
        return Promise.reject(err)
      }
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(API_UNAUTHORIZED_EVENT))
      }
    }
    return Promise.reject(err)
  }
)

export default api
