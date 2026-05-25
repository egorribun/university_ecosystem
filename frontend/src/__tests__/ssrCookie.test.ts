/**
 * @vitest-environment node
 *
 * Wave 133 SW1 — unit tests for SSR cookie forwarding infrastructure.
 *
 * The vitest jsdom default exposes `window`, which would short-circuit
 * the SSR-only branch in the axios interceptor (`typeof window ===
 * "undefined"` evaluates false). Switch this file to the node
 * environment so:
 *   - `typeof window === "undefined"` is true
 *   - `node:async_hooks` is available natively
 *   - `globalThis` getters behave as on the production Node SSR runtime
 *
 * What we test:
 *   1. `globalThis.__ssrCookieGetter__` typing + roundtrip behaviour
 *      (server.ts wires this up; we verify by manually setting the
 *      property and reading it back via the same access pattern the
 *      axios interceptor uses).
 *   2. The axios interceptor (`frontend/src/api/client.ts`) sets the
 *      outgoing `Cookie` header when the getter returns a non-empty
 *      value, and DOES NOT set it otherwise.
 *   3. Existing headers (Authorization, X-CSRF-Token) are preserved
 *      alongside the injected Cookie.
 *
 * Out of scope:
 *   - server.ts's AsyncLocalStorage `.run()` chain itself — that's an
 *     integration concern; the unit tests assume the chain populates
 *     the getter correctly (verified end-to-end by curl + chrome-
 *     devtools-mcp visual smoke at SW6 verification).
 */
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { AsyncLocalStorage } from "node:async_hooks"
import type { AxiosRequestConfig, AxiosResponse } from "axios"
import { AxiosHeaders } from "axios"

import api, { type ApiRequestConfig } from "../api/client"

declare global {
  // Mirror server.ts:61-67 declare-global block so this test file
  // type-checks the access pattern. `var` is required to augment
  // globalThis from a `declare global` block.
  var __ssrCookieGetter__: (() => string | undefined) | undefined
}

interface RecordingAdapterRecord {
  config: AxiosRequestConfig | null
}

const installRecordingAdapter = (record: RecordingAdapterRecord) => {
  const adapter = async (config: AxiosRequestConfig): Promise<AxiosResponse> => {
    record.config = config
    return {
      data: {},
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
      request: {},
    } as AxiosResponse
  }
  api.defaults.adapter = adapter
}

describe("Wave 133 SW1 — typeof window in node environment", () => {
  it("is undefined (precondition for SSR cookie-forwarding branch)", () => {
    expect(typeof window).toBe("undefined")
  })
})

describe("Wave 133 SW1 — globalThis.__ssrCookieGetter__ typing + roundtrip", () => {
  let originalGetter: typeof globalThis.__ssrCookieGetter__

  beforeEach(() => {
    originalGetter = globalThis.__ssrCookieGetter__
  })

  afterEach(() => {
    globalThis.__ssrCookieGetter__ = originalGetter
  })

  it("is undefined by default in this test process", () => {
    globalThis.__ssrCookieGetter__ = undefined
    expect(globalThis.__ssrCookieGetter__).toBeUndefined()
  })

  it("returns a string when wired to an AsyncLocalStorage store", () => {
    const storage = new AsyncLocalStorage<string>()
    globalThis.__ssrCookieGetter__ = () => storage.getStore()
    storage.run("access_token_v2=jwt.value.here; ue-mode=dark", () => {
      expect(globalThis.__ssrCookieGetter__?.()).toBe(
        "access_token_v2=jwt.value.here; ue-mode=dark"
      )
    })
  })

  it("returns undefined outside an active AsyncLocalStorage scope", () => {
    const storage = new AsyncLocalStorage<string>()
    globalThis.__ssrCookieGetter__ = () => storage.getStore()
    expect(globalThis.__ssrCookieGetter__?.()).toBeUndefined()
  })
})

describe("Wave 133 SW1 — axios interceptor SSR cookie forwarding", () => {
  const record: RecordingAdapterRecord = { config: null }
  let originalAdapter: typeof api.defaults.adapter
  let originalGetter: typeof globalThis.__ssrCookieGetter__

  beforeEach(() => {
    originalAdapter = api.defaults.adapter
    originalGetter = globalThis.__ssrCookieGetter__
    record.config = null
    installRecordingAdapter(record)
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
    globalThis.__ssrCookieGetter__ = originalGetter
  })

  it("sets Cookie header when getter returns a non-empty string", async () => {
    globalThis.__ssrCookieGetter__ = () =>
      "access_token_v2=jwt.value.here; csrf_token=tok; ue-mode=dark"
    await api.get("/users/me", { skipRateLimitQueue: true } as ApiRequestConfig)
    const headers = record.config?.headers
    expect(headers).toBeTruthy()
    const cookieHeader =
      headers instanceof AxiosHeaders
        ? headers.get("Cookie")
        : (headers as Record<string, string>)?.Cookie
    expect(cookieHeader).toBe("access_token_v2=jwt.value.here; csrf_token=tok; ue-mode=dark")
  })

  it("does NOT set Cookie header when getter returns empty string", async () => {
    globalThis.__ssrCookieGetter__ = () => ""
    await api.get("/users/me", { skipRateLimitQueue: true } as ApiRequestConfig)
    const headers = record.config?.headers
    const cookieHeader =
      headers instanceof AxiosHeaders
        ? headers.get("Cookie")
        : (headers as Record<string, string>)?.Cookie
    expect(cookieHeader).toBeFalsy()
  })

  it("does NOT set Cookie header when getter returns undefined", async () => {
    globalThis.__ssrCookieGetter__ = () => undefined
    await api.get("/users/me", { skipRateLimitQueue: true } as ApiRequestConfig)
    const headers = record.config?.headers
    const cookieHeader =
      headers instanceof AxiosHeaders
        ? headers.get("Cookie")
        : (headers as Record<string, string>)?.Cookie
    expect(cookieHeader).toBeFalsy()
  })

  it("does NOT set Cookie header when getter is not registered", async () => {
    globalThis.__ssrCookieGetter__ = undefined
    await api.get("/users/me", { skipRateLimitQueue: true } as ApiRequestConfig)
    const headers = record.config?.headers
    const cookieHeader =
      headers instanceof AxiosHeaders
        ? headers.get("Cookie")
        : (headers as Record<string, string>)?.Cookie
    expect(cookieHeader).toBeFalsy()
  })

  it("preserves caller-supplied Authorization + X-CSRF-Token headers alongside injected Cookie", async () => {
    globalThis.__ssrCookieGetter__ = () => "access_token_v2=jwt.value.here"
    await api.get("/users/me", {
      skipRateLimitQueue: true,
      headers: {
        Authorization: "Bearer caller-supplied-token",
        "X-CSRF-Token": "caller-csrf-token",
      },
    } as ApiRequestConfig)
    const headers = record.config?.headers
    expect(headers).toBeTruthy()
    const cookieHeader =
      headers instanceof AxiosHeaders
        ? headers.get("Cookie")
        : (headers as Record<string, string>)?.Cookie
    const authHeader =
      headers instanceof AxiosHeaders
        ? headers.get("Authorization")
        : (headers as Record<string, string>)?.Authorization
    const csrfHeader =
      headers instanceof AxiosHeaders
        ? headers.get("X-CSRF-Token")
        : (headers as Record<string, string>)?.["X-CSRF-Token"]
    expect(cookieHeader).toBe("access_token_v2=jwt.value.here")
    expect(authHeader).toBe("Bearer caller-supplied-token")
    expect(csrfHeader).toBe("caller-csrf-token")
  })

  it("uses fresh getter value per request (not cached at module load)", async () => {
    // First request: getter A
    globalThis.__ssrCookieGetter__ = () => "access_token_v2=first_request"
    await api.get("/users/me", { skipRateLimitQueue: true } as ApiRequestConfig)
    const firstHeaders = record.config?.headers
    const firstCookie =
      firstHeaders instanceof AxiosHeaders
        ? firstHeaders.get("Cookie")
        : (firstHeaders as Record<string, string>)?.Cookie
    expect(firstCookie).toBe("access_token_v2=first_request")

    // Second request: getter B (simulates new request scope per AsyncLocalStorage)
    globalThis.__ssrCookieGetter__ = () => "access_token_v2=second_request"
    await api.get("/users/me", { skipRateLimitQueue: true } as ApiRequestConfig)
    const secondHeaders = (record.config as AxiosRequestConfig | null)?.headers
    const secondCookie =
      secondHeaders instanceof AxiosHeaders
        ? secondHeaders.get("Cookie")
        : (secondHeaders as Record<string, string>)?.Cookie
    expect(secondCookie).toBe("access_token_v2=second_request")
  })
})
