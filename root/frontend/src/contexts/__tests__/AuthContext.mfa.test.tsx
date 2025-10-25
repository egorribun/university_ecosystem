import type { PropsWithChildren } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it } from "vitest"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { createQueryClient } from "@/app/queryClient"

const createWrapper = () => {
  const queryClient = createQueryClient()
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  )

  return { wrapper, queryClient }
}

describe("AuthProvider MFA state machine", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it("surfaces login MFA challenges and clears them after successful verification", async () => {
    const { wrapper, queryClient } = createWrapper()
    const { result, unmount } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))

    let challenge = null as Awaited<ReturnType<typeof result.current.login>>
    await act(async () => {
      challenge = await result.current.login("mfa@example.com", "Password123")
    })

    expect(challenge).not.toBeNull()
    expect(challenge?.reason).toBe("login")

    await waitFor(() => expect(result.current.pendingMfa?.reason).toBe("login"))

    await act(async () => {
      await result.current.submitMfaChallenge({ method: "totp", code: "123456" })
    })

    await waitFor(() => expect(result.current.pendingMfa).toBeNull())
    await waitFor(() => expect(result.current.user).not.toBeNull())
    expect(result.current.isAuth).toBe(true)

    unmount()
    queryClient.clear()
  })

  it("provides step-up challenges and resets state on verification", async () => {
    const { wrapper, queryClient } = createWrapper()
    const { result, unmount } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))

    let challenge = null as Awaited<ReturnType<typeof result.current.requireMfa>>
    await act(async () => {
      challenge = await result.current.requireMfa()
    })

    expect(challenge).not.toBeNull()
    expect(challenge?.reason).toBe("step-up")

    await waitFor(() => expect(result.current.pendingMfa?.reason).toBe("step-up"))

    await act(async () => {
      await result.current.submitMfaChallenge({ method: "totp", code: "123456" })
    })

    await waitFor(() => expect(result.current.pendingMfa).toBeNull())

    unmount()
    queryClient.clear()
  })

  it("surfaces verification errors when the wrong OTP is provided", async () => {
    const { wrapper, queryClient } = createWrapper()
    const { result, unmount } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.login("mfa@example.com", "Password123")
    })

    await waitFor(() => expect(result.current.pendingMfa?.reason).toBe("login"))

    await expect(
      act(async () => {
        await result.current.submitMfaChallenge({ method: "totp", code: "000000" })
      })
    ).rejects.toThrow()

    expect(result.current.pendingMfa?.reason).toBe("login")

    unmount()
    queryClient.clear()
  })
})
