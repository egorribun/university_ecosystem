import { PropsWithChildren } from "react"
import { renderHook, act, waitFor } from "@testing-library/react"
import { QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createQueryClient } from "@/app/queryClient"
import {
  AuthProvider,
  PROFILE_CACHE_STORAGE_KEY,
  currentUserQueryKey,
  useAuth,
} from "@/contexts/AuthContext"
import { testUser } from "@/tests/mocks/handlers"
import api from "@/api/client"

describe("AuthProvider caching", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, "post").mockResolvedValue({ data: {} } as any)
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

  it("stores the current user in the query cache and local storage", async () => {
    localStorage.setItem("token", "token-123")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.user).toBeTruthy())

    expect(queryClient.getQueryData(currentUserQueryKey)).toEqual(testUser)
    expect(queryClient.getQueryState(currentUserQueryKey)?.dataUpdatedAt).toBeGreaterThan(0)

    queryClient.clear()
  })

  it("removes cached profile information on logout", async () => {
    localStorage.setItem("token", "token-456")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.user).toBeTruthy())

    await act(async () => {
      await result.current.logout()
    })

    await waitFor(() => expect(result.current.user).toBeNull())

    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })

  it("synchronizes cached profile state when storage changes", async () => {
    localStorage.setItem("token", "token-789")
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.user).toBeTruthy())

    const cachedEnvelope = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)

    act(() => {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: PROFILE_CACHE_STORAGE_KEY,
          oldValue: cachedEnvelope,
          newValue: null,
          storageArea: localStorage,
        })
      )
    })

    await waitFor(() => expect(result.current.user).toBeNull())
    expect(queryClient.getQueryData(currentUserQueryKey)).toBeNull()

    queryClient.clear()
  })
})
