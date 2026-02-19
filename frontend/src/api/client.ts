import axios, {
  AxiosHeaders,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
} from "axios"
import type { paths } from "@/api/generated/schema"
import i18n, { fallbackLng, supportedLngs } from "@/i18n/config"
import { setTraceContext } from "@/app/logger"

export const API_UNAUTHORIZED_EVENT = "auth:unauthorized"
export const SKIP_UNAUTHORIZED_HEADER = "X-Client-Skip-Unauthorized"
const TRACE_HEADER = (import.meta.env.VITE_TRACE_HEADER || "x-trace-id") as string
const API_TIMEOUT_MS = 8000

const devBase = "/api/v1"
const prodBase = `${import.meta.env.VITE_BACKEND_ORIGIN || ""}/api/v1`

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
  /**
   * Internal flag to indicate that the request acquired a client-side queue
   * slot and should release it once finished.
   */
  __clientRateLimitAcquired?: boolean
  /**
   * Unique cache key used by the Axios ETag interceptor to persist the last
   * received tag and automatically revalidate subsequent requests with
   * `If-None-Match`.
   */
  etagCacheKey?: string
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
  timeout: API_TIMEOUT_MS,
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

const RATE_LIMIT_WINDOW_MS = 60_000

const parsePositiveInteger = (value: unknown, fallback: number): number => {
  const parsed = Number.parseInt(String(value ?? ""), 10)
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed
  }
  return fallback
}

const CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW = parsePositiveInteger(
  import.meta.env.VITE_API_RATE_LIMIT_PER_MINUTE,
  90
)

const CLIENT_RATE_LIMIT_MAX_CONCURRENT = parsePositiveInteger(
  import.meta.env.VITE_API_RATE_LIMIT_MAX_CONCURRENT,
  6
)

let clientQueueInFlight = 0
const clientQueueWaiters: Array<() => void> = []
const clientQueueTimestamps: number[] = []
let clientQueueTimer: ReturnType<typeof setTimeout> | null = null
let clientQueueResetAt = 0

// localStorage-backed ETag cache for persistence across page reloads
const ETAG_CACHE_KEY = "ue:etag-cache"
const RESPONSE_CACHE_KEY = "ue:response-cache"
const MAX_CACHE_ENTRIES = 50

const loadEtagCache = (): Map<string, string> => {
  if (typeof window === "undefined") return new Map()
  try {
    const stored = localStorage.getItem(ETAG_CACHE_KEY)
    if (stored) {
      const entries: [string, string][] = JSON.parse(stored)
      return new Map(entries)
    }
  } catch (_error) {
    import("@/app/logger").then(({ logWarning }) => logWarning("Failed to load etag cache", _error))
  }
  return new Map()
}

const saveEtagCache = (cache: Map<string, string>) => {
  if (typeof window === "undefined") return
  try {
    // Enforce LRU/FIFO limit
    if (cache.size > MAX_CACHE_ENTRIES) {
      const deleteCount = cache.size - MAX_CACHE_ENTRIES
      const keys = cache.keys()
      for (let i = 0; i < deleteCount; i++) {
        const key = keys.next().value
        if (key) cache.delete(key)
      }
    }
    const entries = Array.from(cache.entries())
    localStorage.setItem(ETAG_CACHE_KEY, JSON.stringify(entries))
  } catch (_error) {
    import("@/app/logger").then(({ logWarning }) => logWarning("Failed to save etag cache", _error))
  }
}

// Response body cache for 304 handling
const loadResponseCache = (): Map<string, unknown> => {
  if (typeof window === "undefined") return new Map()
  try {
    const stored = localStorage.getItem(RESPONSE_CACHE_KEY)
    if (stored) {
      const entries: [string, unknown][] = JSON.parse(stored)
      return new Map(entries)
    }
  } catch (_error) {
    import("@/app/logger").then(({ logWarning }) => logWarning("Failed to load response cache", _error))
  }
  return new Map()
}

const saveResponseCache = (cache: Map<string, unknown>) => {
  if (typeof window === "undefined") return
  try {
    // Enforce LRU/FIFO limit
    if (cache.size > MAX_CACHE_ENTRIES) {
      const deleteCount = cache.size - MAX_CACHE_ENTRIES
      const keys = cache.keys()
      for (let i = 0; i < deleteCount; i++) {
        const key = keys.next().value
        if (key) cache.delete(key)
      }
    }
    const entries = Array.from(cache.entries())
    localStorage.setItem(RESPONSE_CACHE_KEY, JSON.stringify(entries))
  } catch (_error) {
    import("@/app/logger").then(({ logWarning }) => logWarning("Failed to save response cache", _error))
  }
}

// Create a proxy wrapper that syncs with localStorage
const createEtagCache = () => {
  let cache = loadEtagCache()
  return {
    get(key: string): string | undefined {
      cache = loadEtagCache() // Always read fresh from localStorage
      return cache.get(key)
    },
    set(key: string, value: string) {
      cache = loadEtagCache()
      cache.set(key, value)
      saveEtagCache(cache)
    },
    delete(key: string) {
      cache = loadEtagCache()
      cache.delete(key)
      saveEtagCache(cache)
    },
    clear() {
      cache.clear()
      if (typeof window !== "undefined") {
        try {
          localStorage.removeItem(ETAG_CACHE_KEY)
        } catch (_error) {
          import("@/app/logger").then(({ logWarning }) => logWarning("Failed to remove etag cache", _error))
        }
      }
    },
  }
}

// Response body cache for 304 handling
const createResponseCache = () => {
  // We keep a local reference to avoid constant parsing if possible,
  // but strictly following the original pattern of "load fresh every time"
  // means we must rely on save... to handle pruning.
  // To make it true LRU, we ought to re-insert on GET.
  // However, avoid writing to localStorage on every GET to prevent potential jank.
  // We will accept FIFO behavior for now as a sufficient optimization over unbounded growth.
  let cache = loadResponseCache()
  return {
    get(key: string): unknown | undefined {
      cache = loadResponseCache()
      return cache.get(key)
    },
    set(key: string, value: unknown) {
      cache = loadResponseCache()
      cache.set(key, value)
      saveResponseCache(cache) // Pruning happens here
    },
    delete(key: string) {
      cache = loadResponseCache()
      cache.delete(key)
      saveResponseCache(cache)
    },
    clear() {
      cache.clear()
      if (typeof window !== "undefined") {
        try {
          localStorage.removeItem(RESPONSE_CACHE_KEY)
        } catch (_error) {
          import("@/app/logger").then(({ logWarning }) => logWarning("Failed to remove response cache", _error))
        }
      }
    },
  }
}

const etagCache = createEtagCache()
const responseCache = createResponseCache()

export const resetEtagCache = () => {
  etagCache.clear()
  responseCache.clear()
}

const updateTraceContext = (headers: AxiosHeaders | Record<string, unknown> | undefined) => {
  if (!headers) {
    setTraceContext(null)
    return
  }
  const normalized = AxiosHeaders.from(headers as AxiosHeaders)
  const traceId = normalized.get(TRACE_HEADER) ?? normalized.get(TRACE_HEADER.toLowerCase())
  if (typeof traceId === "string" && traceId.trim()) {
    setTraceContext(traceId)
  } else {
    setTraceContext(null)
  }
}

const pruneClientQueueTimestamps = () => {
  const threshold = Date.now() - RATE_LIMIT_WINDOW_MS
  while (clientQueueTimestamps.length > 0) {
    const oldest = clientQueueTimestamps[0]!
    if (oldest <= threshold) {
      clientQueueTimestamps.shift()
    } else {
      break
    }
  }
}

const notifyClientQueue = () => {
  if (clientQueueWaiters.length === 0) {
    return
  }

  while (clientQueueWaiters.length > 0) {
    pruneClientQueueTimestamps()

    if (clientQueueInFlight >= CLIENT_RATE_LIMIT_MAX_CONCURRENT) {
      return
    }

    if (clientQueueTimestamps.length >= CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
      scheduleClientQueueWindowReset()
      return
    }

    const resolve = clientQueueWaiters.shift()
    if (!resolve) {
      continue
    }
    resolve()
  }
}

const scheduleClientQueueWindowReset = () => {
  pruneClientQueueTimestamps()

  if (clientQueueTimestamps.length < CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
    if (clientQueueTimer) {
      clearTimeout(clientQueueTimer)
      clientQueueTimer = null
      clientQueueResetAt = 0
    }
    return
  }

  const oldest = clientQueueTimestamps[0] ?? Date.now()
  const target = oldest + RATE_LIMIT_WINDOW_MS
  if (clientQueueTimer && target >= clientQueueResetAt) {
    return
  }

  if (clientQueueTimer) {
    clearTimeout(clientQueueTimer)
    clientQueueTimer = null
  }

  clientQueueResetAt = target
  clientQueueTimer = setTimeout(
    () => {
      clientQueueTimer = null
      clientQueueResetAt = 0
      pruneClientQueueTimestamps()
      notifyClientQueue()
    },
    Math.max(0, target - Date.now())
  )
}

const shouldThrottleRequest = (config: ApiRequestConfig) => {
  const method = (config.method ?? "get").toString().toLowerCase()
  return method === "get"
}

const throwIfAborted = (signal?: AbortSignal) => {
  if (!signal?.aborted) {
    return
  }

  const reason = signal.reason
  if (reason instanceof Error) {
    throw reason
  }

  throw new DOMException("Aborted", "AbortError")
}

const tryAcquireClientQueueSlot = (): boolean => {
  pruneClientQueueTimestamps()

  if (clientQueueInFlight >= CLIENT_RATE_LIMIT_MAX_CONCURRENT) {
    return false
  }

  if (clientQueueTimestamps.length >= CLIENT_RATE_LIMIT_REQUESTS_PER_WINDOW) {
    scheduleClientQueueWindowReset()
    return false
  }

  clientQueueInFlight += 1
  clientQueueTimestamps.push(Date.now())
  return true
}

const waitForClientQueueSlot = async (config: ApiRequestConfig) => {
  if (!shouldThrottleRequest(config)) {
    return
  }

  while (true) {
    throwIfAborted(config.signal)
    if (tryAcquireClientQueueSlot()) {
      config.__clientRateLimitAcquired = true
      return
    }

    await new Promise<void>((resolve) => {
      clientQueueWaiters.push(resolve)
    })
  }
}

const releaseClientQueueSlot = (config?: ApiRequestConfig) => {
  if (!config?.__clientRateLimitAcquired) {
    return
  }

  config.__clientRateLimitAcquired = false

  if (!shouldThrottleRequest(config)) {
    return
  }

  if (clientQueueInFlight > 0) {
    clientQueueInFlight -= 1
  }

  pruneClientQueueTimestamps()
  notifyClientQueue()
}

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

api.interceptors.request.use(async (config) => {
  const candidate = config as ApiRequestConfig

  if (!candidate.skipRateLimitQueue) {
    await waitForClientQueueSlot(candidate)
  }

  if (rateLimitResetAt > Date.now()) {
    await waitForRateLimitWindow()
  }

  const currentLanguage = i18n.language || i18n.resolvedLanguage || fallbackLng
  const headerValue = resolveAcceptLanguage(currentLanguage)

  const headers = AxiosHeaders.from(config.headers ?? {})

  if (!headers.has(acceptLanguageHeader) && !headers.has(acceptLanguageHeader.toLowerCase())) {
    headers.set(acceptLanguageHeader, headerValue)
  }

  const etagKey = candidate.etagCacheKey
  if (etagKey && !headers.has("if-none-match")) {
    const cachedTag = etagCache.get(etagKey)
    if (cachedTag) {
      headers.set("If-None-Match", cachedTag)
    }
  }

  // Automatically remove Content-Type for FormData to let the browser set the boundary
  if (config.data instanceof FormData) {
    headers.delete("Content-Type")
  }

  config.headers = headers

  return config
})

api.interceptors.response.use(
  (response) => {
    const config = response.config as ApiRequestConfig | undefined
    const etagKey = config?.etagCacheKey
    if (etagKey) {
      const responseHeaders = AxiosHeaders.from(
        (response.headers ?? undefined) as AxiosHeaders | string | undefined
      )
      const tag = responseHeaders.get("etag") ?? responseHeaders.get("ETag")
      if (typeof tag === "string" && tag.trim()) {
        etagCache.set(etagKey, tag)
        // Cache response body for 304 handling
        if (response.status === 200 && response.data) {
          responseCache.set(etagKey, response.data)
        }
      } else {
        etagCache.delete(etagKey)
        responseCache.delete(etagKey)
      }

      // Handle 304 Not Modified - return cached data
      if (response.status === 304) {
        const cachedData = responseCache.get(etagKey)
        if (cachedData) {
          response.data = cachedData
          // Change status to 200 so the app treats it as success
          response.status = 200
        }
      }
    }
    updateTraceContext(response.headers as AxiosHeaders)
    releaseClientQueueSlot(response.config as ApiRequestConfig | undefined)
    return response
  },
  async (error) => {
    releaseClientQueueSlot(error?.config as ApiRequestConfig | undefined)

    if (error?.response?.headers) {
      updateTraceContext(error.response.headers as AxiosHeaders)
    }

    const config = error?.config as ApiRequestConfig | undefined
    const etagKey = config?.etagCacheKey
    if (
      etagKey &&
      error?.response?.status &&
      error.response.status >= 400 &&
      error.response.status !== 304
    ) {
      etagCache.delete(etagKey)
    }

    if (error?.response?.status === 429 && error.config) {
      const retryConfig = error.config as ApiRequestConfig
      if (!retryConfig.skipRateLimitQueue) {
        const delay = getRetryDelay(error.response?.headers)
        scheduleRateLimitWindow(delay)

        const retryCount = retryConfig.__rateLimitRetryCount ?? 0
        if (
          retryCount < RATE_LIMIT_MAX_RETRY &&
          !retryConfig.signal?.aborted &&
          !isAbortError(error)
        ) {
          retryConfig.__rateLimitRetryCount = retryCount + 1
          await waitForRateLimitWindow()
          return api.request(retryConfig)
        }
      }
    }

    if (error?.response?.status === 401) {
      const headers = (error.config?.headers ?? {}) as Record<string, unknown>
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

type ApiMethod = "get" | "post" | "put" | "patch" | "delete"

type ApiPath = keyof paths

type OperationFor<P extends ApiPath, M extends ApiMethod> = paths[P][M]

type EmptyObject = Record<never, never>

type ExtractPathParams<Op> = Op extends unknown
  ? Op extends { parameters?: { path: infer Params } }
    ? Params extends Record<string, unknown>
      ? Params
      : never
    : never
  : never

type MethodsForPath<P extends ApiPath> = {
  [M in ApiMethod]: paths[P][M]
}[ApiMethod]

type PathParamsOf<P extends ApiPath> = [ExtractPathParams<MethodsForPath<P>>] extends [never]
  ? EmptyObject
  : ExtractPathParams<MethodsForPath<P>>

type QueryParamsOf<P extends ApiPath, M extends ApiMethod> =
  OperationFor<P, M> extends never
    ? EmptyObject
    : OperationFor<P, M> extends { parameters?: { query?: infer Query } }
      ? Query extends Record<string, unknown>
        ? Query
        : EmptyObject
      : EmptyObject

type HeaderParamsOf<P extends ApiPath, M extends ApiMethod> =
  OperationFor<P, M> extends never
    ? EmptyObject
    : OperationFor<P, M> extends { parameters?: { header?: infer Header } }
      ? Header extends Record<string, unknown>
        ? Header
        : EmptyObject
      : EmptyObject

type NormalizeContent<Content> =
  Content extends Record<string, unknown>
    ? {
        [K in keyof Content]: K extends "application/json"
          ? Content[K]
          : K extends "multipart/form-data"
            ? Content[K] | FormData
            : K extends "application/x-www-form-urlencoded"
              ? Content[K] | URLSearchParams
              : Content[K]
      }[keyof Content]
    : never

type RequestBodyOf<P extends ApiPath, M extends ApiMethod> =
  OperationFor<P, M> extends never
    ? undefined
    : OperationFor<P, M> extends { requestBody?: { content: infer Content } }
      ? NormalizeContent<Content>
      : OperationFor<P, M> extends { requestBody: { content: infer Content } }
        ? NormalizeContent<Content>
        : undefined

type SuccessStatus = 200 | 201 | 202 | 203 | 204 | 205 | 206

type ResponseContent<Response> = Response extends { content: infer Content }
  ? Content extends Record<string, unknown>
    ? "application/json" extends keyof Content
      ? Content["application/json"]
      : Content[keyof Content]
    : unknown
  : unknown

type ResponseDataOf<P extends ApiPath, M extends ApiMethod> =
  OperationFor<P, M> extends never
    ? unknown
    : OperationFor<P, M> extends { responses: infer Responses }
      ? {
          [S in keyof Responses & (SuccessStatus | "default")]: ResponseContent<Responses[S]>
        }[keyof Responses & (SuccessStatus | "default")] extends infer Result
        ? Result extends never
          ? unknown
          : Result
        : unknown
      : unknown

type ApiRequestHeaders<P extends ApiPath, M extends ApiMethod> = HeaderParamsOf<P, M> &
  Partial<Record<string, string | number | boolean | null | undefined>>

type PathParamsOption<P extends ApiPath> = keyof PathParamsOf<P> extends never
  ? { pathParams?: undefined }
  : { pathParams: PathParamsOf<P> }

type ApiRequestOptions<P extends ApiPath, M extends ApiMethod> = Omit<
  ApiRequestConfig<RequestBodyOf<P, M>>,
  "url" | "method" | "data" | "params" | "headers"
> &
  PathParamsOption<P> & {
    params?: QueryParamsOf<P, M>
    headers?: ApiRequestHeaders<P, M>
  }

type ApiResponseFor<P extends ApiPath, M extends ApiMethod> = AxiosResponse<ResponseDataOf<P, M>>

const buildPathWithParams = <P extends ApiPath>(path: P, params: PathParamsOf<P> | undefined) => {
  // Strip /api/v1 prefix since the base URL already includes it
  let normalizedPath = path as string
  if (normalizedPath.startsWith("/api/v1")) {
    normalizedPath = normalizedPath.slice(7) // Remove "/api/v1"
  }

  if (!params || Object.keys(params).length === 0) {
    return normalizedPath
  }

  return normalizedPath.replace(/\{([^{}]+)\}/g, (_segment, key: string) => {
    const value = params[key as keyof typeof params]
    if (value == null) {
      throw new Error(`Missing value for path parameter "${key}"`)
    }
    return encodeURIComponent(String(value))
  })
}

const normalizeHeaders = <P extends ApiPath, M extends ApiMethod>(
  headers: ApiRequestHeaders<P, M> | undefined
): ApiRequestHeaders<P, M> | undefined => {
  if (!headers) {
    return headers
  }

  const normalizedEntries = Object.entries(headers).filter(
    ([, value]) => value !== undefined && value !== null
  )

  if (normalizedEntries.length === 0) {
    return undefined
  }

  return Object.fromEntries(normalizedEntries) as ApiRequestHeaders<P, M>
}

const createTypedClient = (instance: ApiInstance) => {
  const request = async <P extends ApiPath, M extends ApiMethod>(
    method: M,
    path: P,
    options?: ApiRequestOptions<P, M>,
    body?: RequestBodyOf<P, M>
  ): Promise<ApiResponseFor<P, M>> => {
    const { pathParams, headers, params, ...rest } = options ?? {}
    const url = buildPathWithParams(path, pathParams)
    const config = rest as ApiRequestConfig<RequestBodyOf<P, M>>
    const finalHeaders = normalizeHeaders(headers)
    const requestConfig: ApiRequestConfig<RequestBodyOf<P, M>> = {
      ...config,
      method,
      url,
      params,
      headers: finalHeaders,
    }
    if (body !== undefined) {
      requestConfig.data = body
    }
    return instance.request<ResponseDataOf<P, M>>(requestConfig)
  }

  return {
    request,
    get: <P extends ApiPath>(path: P, options?: ApiRequestOptions<P, "get">) =>
      request("get", path, options),
    delete: <P extends ApiPath>(path: P, options?: ApiRequestOptions<P, "delete">) =>
      request("delete", path, options),
    post: <P extends ApiPath>(
      path: P,
      data?: RequestBodyOf<P, "post">,
      options?: ApiRequestOptions<P, "post">
    ) => request("post", path, options, data),
    put: <P extends ApiPath>(
      path: P,
      data?: RequestBodyOf<P, "put">,
      options?: ApiRequestOptions<P, "put">
    ) => request("put", path, options, data),
    patch: <P extends ApiPath>(
      path: P,
      data?: RequestBodyOf<P, "patch">,
      options?: ApiRequestOptions<P, "patch">
    ) => request("patch", path, options, data),
  }
}

export type TypedApiClient = ReturnType<typeof createTypedClient>

export type TypedRequestOptions<P extends ApiPath, M extends ApiMethod> = ApiRequestOptions<P, M>

export const apiClient = createTypedClient(api)

export default api
