import { PropsWithChildren } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { AxiosError, AxiosHeaders } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import {
  AuthProvider,
  PROFILE_CACHE_STORAGE_KEY,
  fetchCurrentUser,
  useAuth,
} from "@/contexts/AuthContext"
import { testUser } from "@/tests/mocks/handlers"

describe("fetchCurrentUser request configuration", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("passes skipRateLimitQueue when loading the current user", async () => {
    const controller = new AbortController()
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    await fetchCurrentUser({ signal: controller.signal })

    expect(getSpy).toHaveBeenCalledWith(
      "/users/me",
      expect.objectContaining({ signal: controller.signal, skipRateLimitQueue: true })
    )
  })

  it("includes the cached profile header while still skipping the rate limit queue", async () => {
    const cachedEnvelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, cachedEnvelope)
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as any)

    await fetchCurrentUser()

    expect(getSpy).toHaveBeenCalledWith(
      "/users/me",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Profile-Cache-Envelope": cachedEnvelope }),
        skipRateLimitQueue: true,
      })
    )
  })

  it("continues to skip the rate limit queue when retrying without a cached header", async () => {
    const cachedEnvelope = JSON.stringify({ id: testUser.id })
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, cachedEnvelope)
    const axiosError = new AxiosError(
      "Bad Request",
      AxiosError.ERR_BAD_REQUEST,
      undefined,
      undefined,
      {
        status: 400,
        statusText: "Bad Request",
        headers: {},
        config: {
          headers: new AxiosHeaders(),
        },
        data: {},
      }
    )
    const getSpy = vi
      .spyOn(api, "get")
      .mockRejectedValueOnce(axiosError)
      .mockResolvedValueOnce({ data: testUser } as any)

    await fetchCurrentUser()

    expect(getSpy).toHaveBeenNthCalledWith(
      1,
      "/users/me",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Profile-Cache-Envelope": cachedEnvelope }),
        skipRateLimitQueue: true,
      })
    )
    expect(getSpy).toHaveBeenNthCalledWith(
      2,
      "/users/me",
      expect.objectContaining({ skipRateLimitQueue: true })
    )
    expect(getSpy.mock.calls[1]?.[1]?.headers).toBeUndefined()
  })
})

describe("ensureSessionSigningKey request configuration", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  const setup = () => {
    const queryClient = createQueryClient()
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )
    return { queryClient, wrapper }
  }

  it("passes skipRateLimitQueue when requesting the session signing key", async () => {
    const { queryClient, wrapper } = setup()
    const getSpy = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/users/me") {
        return Promise.resolve({ data: testUser } as any)
      }
      if (url === "/auth/session/signing-key") {
        return Promise.resolve({ data: { signing_key: "session-key" } })
      }
      throw new Error(`Unexpected url: ${url}`)
    })

    localStorage.setItem("token", "token-123")

    renderHook(() => useAuth(), { wrapper })

    await waitFor(() =>
      expect(getSpy).toHaveBeenCalledWith(
        "/auth/session/signing-key",
        expect.objectContaining({ skipRateLimitQueue: true })
      )
    )

    queryClient.clear()
  })
})
