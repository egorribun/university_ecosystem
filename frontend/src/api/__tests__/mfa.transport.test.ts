import { afterEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"

import type { MfaVerifyPayload } from "@/types/Mfa"

type CapturedRequest = {
  data: unknown
  effectiveUri: string
  method: string | undefined
  skipRateLimitQueue: boolean | undefined
}

type ApiClient = (typeof import("@/api/client"))["default"]
let apiClient: ApiClient | undefined
let originalAdapter: ApiClient["defaults"]["adapter"] | undefined

afterEach(() => {
  if (apiClient) apiClient.defaults.adapter = originalAdapter
  apiClient = undefined
  originalAdapter = undefined
  vi.restoreAllMocks()
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe("MFA verification transport", () => {
  it("keeps the MFA route and payload and rejects one 429 without retrying", async () => {
    vi.useFakeTimers()
    vi.stubEnv("DEV", false)
    vi.stubEnv("VITE_API_RATE_LIMIT_PER_MINUTE", "100")
    vi.stubEnv("VITE_API_RATE_LIMIT_MAX_CONCURRENT", "10")
    vi.resetModules()

    const [{ default: api }, { verifyMfaChallenge }] = await Promise.all([
      import("@/api/client"),
      import("@/api/mfa"),
    ])
    apiClient = api
    originalAdapter = api.defaults.adapter
    expect(api.defaults.baseURL).toBe("/api/v1")

    const payload: MfaVerifyPayload = {
      challenge_token: "transport-test-challenge",
      code: "123456",
      method: "totp",
    }
    const captured: CapturedRequest[] = []
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
      const body =
        typeof config.data === "string" ? (JSON.parse(config.data) as unknown) : config.data
      captured.push({
        data: body,
        effectiveUri: api.getUri(config),
        method: config.method,
        skipRateLimitQueue: (
          config as InternalAxiosRequestConfig & {
            skipRateLimitQueue?: boolean
          }
        ).skipRateLimitQueue,
      })

      const response = {
        config,
        data: { detail: "synthetic rate limit" },
        headers: AxiosHeaders.from({ "retry-after": "0" }),
        status: 429,
        statusText: "Too Many Requests",
      }
      throw Object.assign(new Error("synthetic 429"), { config, response })
    })
    api.defaults.adapter = adapter
    const fetchSpy = vi.spyOn(globalThis, "fetch")

    const pending = verifyMfaChallenge(payload)
    const rejected = expect(pending).rejects.toMatchObject({ response: { status: 429 } })
    await vi.advanceTimersByTimeAsync(0)
    await rejected

    expect(captured[0]).toMatchObject({
      data: payload,
      effectiveUri: "/api/v1/auth/mfa/verify",
      method: "post",
      skipRateLimitQueue: true,
    })
    expect(adapter).toHaveBeenCalledOnce()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
