import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders, isCancel } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"

// Stable module-level mock for the trace-context sink. The traceContext
// interceptor imports setTraceContext as a direct binding, so we must mock the
// module (a namespace spy wouldn't intercept the live ESM binding). The spy is
// hoisted + stable across vi.resetModules() so re-imported client graphs share it.
const setTraceContextMock = vi.hoisted(() => vi.fn((..._a: unknown[]) => undefined))
vi.mock("@/app/logger", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/app/logger")>()
  return { ...actual, setTraceContext: setTraceContextMock }
})

/**
 * Build a 429 error matching what axios surfaces to the response interceptor.
 */
const SESSION_GENERATION_KEY = "ecosystem.session.generation.v1"

const make429 = (config: InternalAxiosRequestConfig, headers: Record<string, string> = {}) =>
  Object.assign(new Error("Too Many Requests"), {
    config,
    response: {
      status: 429,
      statusText: "Too Many Requests",
      headers: AxiosHeaders.from(headers),
      data: { detail: "slow down" },
      config,
    },
  })

describe("API client 429 retry loop", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetModules()
    localStorage.removeItem(SESSION_GENERATION_KEY)
    vi.unstubAllEnvs()
    // Generous client-side queue so the queue logic never interferes with the
    // server-side 429 retry path we are exercising here.
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "100")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
  })

  afterEach(() => {
    localStorage.removeItem(SESSION_GENERATION_KEY)
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("retries after a 429 and resolves once the backoff window elapses and a 200 returns", async () => {
    const { default: api } = await import("@/api/client")

    let calls = 0
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      calls += 1
      if (calls === 1) {
        // First attempt: 429 with a 1s retry-after window.
        throw make429(config, { "retry-after": "1" })
      }
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      } as AxiosResponse
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news")

    // Let the first attempt run + reject, scheduling the rate-limit window.
    await vi.advanceTimersByTimeAsync(0)
    // Retry-after "1" => 1000ms backoff. Advance past it to release the wait.
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(0)

    await expect(pending).resolves.toMatchObject({ status: 200, data: { ok: true } })
    expect(adapter).toHaveBeenCalledTimes(2)
  })

  it("reuses one idempotency key when a logical chat send retries after a 429", async () => {
    const { default: api } = await import("@/api/client")
    const { chatApi } = await import("@/api/chat")
    const operationKey = "logical-chat-send-operation"
    const sentKeys: Array<string | undefined> = []
    let calls = 0

    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      calls += 1
      sentKeys.push(AxiosHeaders.from(config.headers).get("Idempotency-Key") as string | undefined)
      if (calls === 1) {
        throw make429(config, { "retry-after": "1" })
      }
      return {
        config,
        data: { id: "server-message" },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      } as AxiosResponse
    })
    api.defaults.adapter = adapter

    const sendMessageWithOperationKey = chatApi.sendMessage as unknown as (
      chatId: string,
      content: string,
      files: File[] | undefined,
      replyToMessageId: string | undefined,
      operationId: string
    ) => Promise<unknown>
    const pending = sendMessageWithOperationKey(
      "chat-1",
      "hello",
      undefined,
      undefined,
      operationKey
    )
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(1_000)
    await vi.advanceTimersByTimeAsync(0)

    await expect(pending).resolves.toMatchObject({ id: "server-message" })
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(sentKeys).toEqual([operationKey, operationKey])
  })

  it("cancels a 429 retry when another tab rotates the browser session", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: api } = await import("@/api/client")

    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      throw make429(config, { "retry-after": "1" })
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news")
    const settled = pending.catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(0)

    // A storage write models the origin-wide generation update from another tab.
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    await vi.advanceTimersByTimeAsync(1_000)
    await vi.advanceTimersByTimeAsync(0)

    const result = await settled
    expect(isCancel(result)).toBe(true)
    expect(adapter).toHaveBeenCalledOnce()
  })

  it("does not dispatch or enter retry handling when a request starts in a stale tab", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: api } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )

    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      throw make429(config, { "retry-after": "1" })
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news").catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(0)
    const result = await pending

    expect(isCancel(result)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it("rejects with the 429 once the retry count reaches RATE_LIMIT_MAX_RETRY", async () => {
    const { default: api } = await import("@/api/client")
    const { RATE_LIMIT_MAX_RETRY } = await import("@/api/interceptors/rateLimit")

    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      // Always 429 — the loop should give up after MAX_RETRY retries.
      throw make429(config, { "retry-after": "1" })
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news")
    // Surface as a rejection rather than an unhandled rejection.
    const settled = pending.catch((e: unknown) => e)

    // Drive the backoff windows: initial attempt + RATE_LIMIT_MAX_RETRY retries.
    for (let i = 0; i <= RATE_LIMIT_MAX_RETRY + 1; i += 1) {
      await vi.advanceTimersByTimeAsync(1000)
      await vi.advanceTimersByTimeAsync(0)
    }

    const result = await settled
    expect(result).toMatchObject({ response: { status: 429 } })
    // 1 initial attempt + RATE_LIMIT_MAX_RETRY retries.
    expect(adapter).toHaveBeenCalledTimes(RATE_LIMIT_MAX_RETRY + 1)
  })

  it("aborts during the rate-limit backoff wait and rejects with an AbortError", async () => {
    const { default: api } = await import("@/api/client")

    const controller = new AbortController()
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      // Always 429 with a long backoff so the abort wins the race.
      throw make429(config, { "retry-after": "30" })
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news", { signal: controller.signal } as never)
    const settled = pending.catch((e: unknown) => e)

    // Let the first attempt run + reject, entering waitForRateLimitWindow.
    await vi.advanceTimersByTimeAsync(0)
    // Abort mid-wait — waitForRateLimitWindow's abort listener rejects.
    controller.abort()
    await vi.advanceTimersByTimeAsync(0)

    const result = await settled
    expect(result).toBeInstanceOf(DOMException)
    expect((result as DOMException).name).toBe("AbortError")
    // Only the initial attempt fired; the retry never reissued the request.
    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it("does not retry a 429 when skipRateLimitQueue bypasses the queue", async () => {
    const { default: api } = await import("@/api/client")

    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      throw make429(config, { "retry-after": "1" })
    })
    api.defaults.adapter = adapter

    // /users/me is on the rate-limit skip allowlist, so skipRateLimitQueue stays true
    // and the 429 retry branch (gated on !config.skipRateLimitQueue) is skipped.
    const pending = api.get("/users/me", { skipRateLimitQueue: true } as never)
    const settled = pending.catch((e: unknown) => e)

    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(0)

    const result = await settled
    expect(result).toMatchObject({ response: { status: 429 } })
    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it("waits for an already active rate-limit window before sending a request", async () => {
    const { default: api } = await import("@/api/client")
    const { scheduleRateLimitWindow } = await import("@/api/interceptors/rateLimit")
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    api.defaults.adapter = adapter
    scheduleRateLimitWindow(1_000)

    const pending = api.get("/news")
    await vi.advanceTimersByTimeAsync(0)
    expect(adapter).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1_000)
    await expect(pending).resolves.toMatchObject({ status: 200 })
    expect(adapter).toHaveBeenCalledOnce()
  })

  it("treats a nameless 429 payload as non-abort and retries it", async () => {
    const { default: api } = await import("@/api/client")
    let calls = 0
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      calls += 1
      if (calls === 1) {
        throw {
          config,
          response: {
            status: 429,
            statusText: "Too Many Requests",
            headers: AxiosHeaders.from({ "retry-after": "1" }),
            data: { detail: "slow down" },
            config,
          },
        }
      }
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news")
    await vi.advanceTimersByTimeAsync(1_000)
    await vi.advanceTimersByTimeAsync(0)

    await expect(pending).resolves.toMatchObject({ status: 200 })
    expect(adapter).toHaveBeenCalledTimes(2)
  })

  it("uses the default retry delay when the 429 response has no headers", async () => {
    const { default: api } = await import("@/api/client")
    let calls = 0
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      calls += 1
      if (calls === 1) {
        throw Object.assign(new Error("Too Many Requests"), {
          config,
          response: {
            status: 429,
            statusText: "Too Many Requests",
            headers: undefined,
            data: { detail: "slow down" },
            config,
          },
        })
      }
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news")
    await vi.advanceTimersByTimeAsync(2_000)
    await vi.advanceTimersByTimeAsync(0)

    await expect(pending).resolves.toMatchObject({ status: 200 })
    expect(adapter).toHaveBeenCalledTimes(2)
  })

  it("uses the default retry delay when Retry-After is not a string", async () => {
    const { default: api } = await import("@/api/client")
    let calls = 0
    const adapter = vi.fn(async (config): Promise<AxiosResponse> => {
      calls += 1
      if (calls === 1) {
        throw Object.assign(new Error("Too Many Requests"), {
          config,
          response: {
            status: 429,
            statusText: "Too Many Requests",
            headers: { "retry-after": 1 },
            data: { detail: "slow down" },
            config,
          },
        })
      }
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    })
    api.defaults.adapter = adapter

    const pending = api.get("/news")
    await vi.advanceTimersByTimeAsync(2_000)
    await vi.advanceTimersByTimeAsync(0)

    await expect(pending).resolves.toMatchObject({ status: 200 })
    expect(adapter).toHaveBeenCalledTimes(2)
  })
})

describe("API client trace-context response interceptor", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllEnvs()
    setTraceContextMock.mockClear()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("forwards the x-trace-id response header into setTraceContext on success", async () => {
    const { default: api } = await import("@/api/client")

    api.defaults.adapter = async (config): Promise<AxiosResponse> =>
      ({
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: AxiosHeaders.from({ "x-trace-id": "trace-abc-123" }),
        request: {},
      }) as AxiosResponse

    await api.get("/news")

    expect(setTraceContextMock).toHaveBeenCalledWith("trace-abc-123")
  })

  it("clears the trace context (null) when the response carries no trace header", async () => {
    const { default: api } = await import("@/api/client")

    api.defaults.adapter = async (config): Promise<AxiosResponse> =>
      ({
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: AxiosHeaders.from({ "content-type": "application/json" }),
        request: {},
      }) as AxiosResponse

    await api.get("/news")

    expect(setTraceContextMock).toHaveBeenCalledWith(null)
  })

  it("forwards the trace header from an error response too", async () => {
    const { default: api } = await import("@/api/client")

    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      throw Object.assign(new Error("Server error"), {
        config,
        response: {
          status: 500,
          statusText: "Internal Server Error",
          headers: AxiosHeaders.from({ "x-trace-id": "trace-err-999" }),
          data: { detail: "boom" },
          config,
        },
      })
    }

    await expect(api.get("/news")).rejects.toMatchObject({ response: { status: 500 } })
    expect(setTraceContextMock).toHaveBeenCalledWith("trace-err-999")
  })
})
