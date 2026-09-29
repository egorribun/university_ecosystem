import { AxiosHeaders, isCancel, type InternalAxiosRequestConfig } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Deterministic contract for the request interceptor. The waits are spies so
// every branch is observed directly instead of through timing: a mutant that
// wrongly waits fails an assertion rather than hanging a test.
const rateLimit = vi.hoisted(() => ({
  waitForClientQueueSlot: vi.fn(async () => undefined),
  waitForRateLimitWindow: vi.fn(async () => undefined),
  isRateLimited: vi.fn(() => false),
}))

vi.mock("../interceptors/rateLimit", async () => {
  const actual = await vi.importActual<typeof import("../interceptors/rateLimit")>(
    "../interceptors/rateLimit"
  )
  return { ...actual, ...rateLimit }
})

import api from "../client"

type RequestHandler = (config: InternalAxiosRequestConfig) => Promise<InternalAxiosRequestConfig>

const requestHandler = (): RequestHandler =>
  (
    api.interceptors.request as unknown as {
      handlers: Array<{ fulfilled?: RequestHandler } | null>
    }
  ).handlers.find((handler) => typeof handler?.fulfilled === "function")!.fulfilled!

const requestConfig = (overrides: Partial<InternalAxiosRequestConfig>) =>
  ({ headers: new AxiosHeaders(), method: "get", ...overrides }) as InternalAxiosRequestConfig

let keySequence = 0
const uniqueKey = () => `interceptor-contract-${Date.now()}-${keySequence++}`

beforeEach(() => {
  vi.clearAllMocks()
  rateLimit.isRateLimited.mockReturnValue(false)
})

afterEach(() => {
  delete (globalThis as { __ssrCookieGetter__?: unknown }).__ssrCookieGetter__
})

describe("request URL normalization", () => {
  it.each([
    ["/api/v1/api/v1/users/me", undefined, "/api/v1/users/me"],
    [
      "https://api.example.test/api/v1/api/v1/news?page=2",
      undefined,
      "https://api.example.test/api/v1/news?page=2",
    ],
    [
      "http://api.example.test/api/v1/api/v1/events",
      undefined,
      "http://api.example.test/api/v1/events",
    ],
    ["/api/v1/users", "/api/v1", "/users"],
    ["/users/me", "/api/v1", "/users/me"],
    ["/api/v1/users", "", "/api/v1/users"],
    ["https://api.example.test/news", "/api/v1", "https://api.example.test/news"],
    ["http://", undefined, "http://"],
  ])("maps %s (base %s) to %s", async (url, baseURL, expected) => {
    const config = requestConfig({ url, baseURL })
    await requestHandler()(config)
    expect(config.url).toBe(expected)
  })

  it("keeps a request without a URL untouched", async () => {
    const config = requestConfig({ url: undefined, baseURL: "/api/v1" })
    await requestHandler()(config)
    expect(config.url).toBeUndefined()
  })
})

describe("mutation idempotency deduplication", () => {
  it.each(["post", "put", "patch", "delete"])(
    "suppresses a duplicate in-flight %s with the same key",
    async (method) => {
      const key = uniqueKey()
      const headers = () => AxiosHeaders.from({ "Idempotency-Key": key })

      await requestHandler()(requestConfig({ method, url: "/events", headers: headers() }))
      const duplicate = requestHandler()(
        requestConfig({ method, url: "/events", headers: headers() })
      )

      await expect(duplicate).rejects.toSatisfy(isCancel)
    }
  )

  it("never deduplicates safe reads, even with a key", async () => {
    const key = uniqueKey()
    const config = () =>
      requestConfig({
        method: "get",
        url: "/events",
        headers: AxiosHeaders.from({ "Idempotency-Key": key }),
      })

    await requestHandler()(config())
    await expect(requestHandler()(config())).resolves.toBeDefined()
  })

  it("does not deduplicate a request without a method", async () => {
    const key = uniqueKey()
    const config = () =>
      requestConfig({
        method: undefined,
        url: "/events",
        headers: AxiosHeaders.from({ "Idempotency-Key": key }),
      })

    await requestHandler()(config())
    await expect(requestHandler()(config())).resolves.toBeDefined()
  })
})

describe("rate-limit waits in the browser runtime", () => {
  it("queues the request but skips the window wait while not rate limited", async () => {
    const config = requestConfig({ url: "/events" })
    await requestHandler()(config)

    expect(rateLimit.waitForClientQueueSlot).toHaveBeenCalledOnce()
    expect(rateLimit.isRateLimited).toHaveBeenCalledOnce()
    expect(rateLimit.waitForRateLimitWindow).not.toHaveBeenCalled()
  })

  it("lets only allowlisted auth endpoints bypass the client queue", async () => {
    const allowlisted = requestConfig({ url: "/auth/login" }) as InternalAxiosRequestConfig & {
      skipRateLimitQueue?: boolean
    }
    allowlisted.skipRateLimitQueue = true
    await requestHandler()(allowlisted)
    expect(rateLimit.waitForClientQueueSlot).not.toHaveBeenCalled()

    const demoted = requestConfig({ url: "/events" }) as InternalAxiosRequestConfig & {
      skipRateLimitQueue?: boolean
    }
    demoted.skipRateLimitQueue = true
    const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    await requestHandler()(demoted)
    expect(warning).toHaveBeenCalledWith(
      "[rateLimit] skipRateLimitQueue=true for non-allowlisted URL: /events"
    )
    warning.mockRestore()
    expect(demoted.skipRateLimitQueue).toBe(false)
    expect(rateLimit.waitForClientQueueSlot).toHaveBeenCalledOnce()
  })

  it("waits for the rate-limit window with the request signal while limited", async () => {
    rateLimit.isRateLimited.mockReturnValue(true)
    const signal = new AbortController().signal
    await requestHandler()(requestConfig({ url: "/events", signal }))

    expect(rateLimit.waitForRateLimitWindow).toHaveBeenCalledExactlyOnceWith(signal)
  })
})

describe("SSR header forwarding", () => {
  it("never forwards SSR cookies from a browser runtime", async () => {
    ;(globalThis as { __ssrCookieGetter__?: () => string }).__ssrCookieGetter__ = () =>
      "access_token_v2=secret"
    const config = requestConfig({ url: "/users/me" })

    await requestHandler()(config)

    expect(AxiosHeaders.from(config.headers).get("Cookie")).toBeUndefined()
  })
})
