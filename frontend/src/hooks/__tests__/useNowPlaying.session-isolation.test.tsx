import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { useLayoutEffect, type PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders, type AxiosResponse } from "axios"
import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import {
  fetchNowPlaying,
  nowPlayingQueryKey,
  SPOTIFY_REAUTH_EVENT,
  useNowPlaying,
  __testing as nowPlayingTesting,
} from "@/hooks/useNowPlaying"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { withExpectedConsole } from "@/tests/strictConsole"
import type { UserState } from "@/types/Auth"
import type { NowPlaying } from "@/types/spotify"

vi.mock("@/hooks/auth/useProfileSync", () => ({ fetchCurrentUser: vi.fn() }))
vi.mock("@/push/subscribe", () => ({
  hasPushConsent: () => false,
  releasePushServerBinding: async () => undefined,
  setPushConsent: vi.fn(),
  syncPushForConfirmedIdentity: vi.fn(),
}))

const legacyKey = "spotify:now-playing:last"
const storageKey = (owner: string) => `${legacyKey}:account:${encodeURIComponent(owner)}`
const setIdentity = (id: string | null, loading = false) => {
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  useAuthStore.setState({ user: id === null ? null : ({ id } as UserState), loading })
}
const track = (owner: string): NowPlaying => ({
  track_id: `private-${owner}`,
  track_name: `${owner}'s song`,
  artists: [owner],
  is_playing: true,
  album_name: null,
  album_image_url: null,
  track_url: null,
  duration_ms: 1000,
  progress_ms: 100,
  fetched_at: "2026-10-02T20:00:00Z",
})
const response = (owner: string): AxiosResponse<NowPlaying> => ({
  status: 200,
  statusText: "OK",
  headers: {},
  config: { headers: new AxiosHeaders() },
  data: track(owner),
})
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((accept, fail) => {
    resolve = accept
    reject = fail
  })
  return { promise, resolve, reject }
}
const createWrapper = () => {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retryDelay: 0, gcTime: 0 } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}
const rotateOtherTab = () =>
  window.localStorage.setItem(
    "ecosystem.session.generation.v1",
    JSON.stringify({ nonce: "other-tab", hash: null })
  )

beforeEach(() => {
  localStorage.clear()
  setIdentity("account-a")
})
afterEach(() => {
  cleanup()
  setIdentity(null)
  localStorage.clear()
  acceptBrowserSessionGeneration()
  vi.restoreAllMocks()
})

describe("now-playing account isolation", () => {
  it.each([null, "account-a"])(
    "rejects a persistence request from unconfirmed or stale owner %s without changing either account's snapshot",
    (owner) => {
      localStorage.setItem(storageKey("account-a"), JSON.stringify(track("a")))
      localStorage.setItem(storageKey("account-b"), JSON.stringify(track("b")))
      setIdentity("account-b")
      const keyCount = localStorage.length

      nowPlayingTesting.persistNowPlaying(owner, track("stale"))

      expect(JSON.parse(localStorage.getItem(storageKey("account-a"))!)).toEqual(track("a"))
      expect(JSON.parse(localStorage.getItem(storageKey("account-b"))!)).toEqual(track("b"))
      expect(localStorage.getItem(legacyKey)).toBeNull()
      expect(localStorage.length).toBe(keyCount)
    }
  )

  it("persists each confirmed account's track separately and restores its offline snapshot", async () => {
    const get = vi
      .spyOn(api, "get")
      .mockResolvedValueOnce(response("a"))
      .mockResolvedValueOnce(response("b"))
    const { result, unmount } = renderHook(() => useNowPlaying(true), createWrapper())
    await waitFor(() => expect(result.current.data).toEqual(track("a")))
    expect(JSON.parse(localStorage.getItem(storageKey("account-a"))!)).toEqual(track("a"))
    expect(localStorage.getItem(legacyKey)).toBeNull()
    act(() => setIdentity("account-b"))
    expect(result.current.data).toBeNull()
    await waitFor(() => expect(result.current.data).toEqual(track("b")))
    expect(JSON.parse(localStorage.getItem(storageKey("account-b"))!)).toEqual(track("b"))
    unmount()
    setIdentity("account-a")
    get.mockRejectedValue(new Error("offline"))
    const offline = renderHook(() => useNowPlaying(false), createWrapper())
    expect(offline.result.current.data).toEqual(track("a"))
    await act(async () => {
      await offline.result.current.refetch()
    })
    expect(offline.result.current.data).toEqual(track("a"))
    expect(JSON.parse(localStorage.getItem(storageKey("account-b"))!)).toEqual(track("b"))
  })

  it("replaces a mounted offline fallback when the confirmed owner changes", () => {
    localStorage.setItem(storageKey("account-a"), JSON.stringify(track("a")))
    localStorage.setItem(storageKey("account-b"), JSON.stringify(track("b")))
    const { result } = renderHook(() => useNowPlaying(false), createWrapper())
    expect(result.current.data).toEqual(track("a"))
    act(() => setIdentity("account-b"))
    expect(result.current.data).toEqual(track("b"))
    act(() => setIdentity(null))
    expect(result.current.data).toBeNull()
  })

  it("does not adopt an ownerless legacy snapshot", () => {
    localStorage.setItem(legacyKey, JSON.stringify(track("legacy-a")))
    const { result } = renderHook(() => useNowPlaying(false), createWrapper())
    expect(result.current.data).toBeNull()
    expect(localStorage.getItem(storageKey("account-a"))).not.toBe(
      JSON.stringify(track("legacy-a"))
    )
  })

  it.each<[string | null, boolean]>([
    [null, false],
    ["ssr-stub", false],
    ["-1", false],
    ["lhci-audit", false],
    ["account-a", true],
  ])(
    "rejects cache and imperative requests for unconfirmed identity %s / loading %s",
    async (id, loading) => {
      localStorage.setItem(legacyKey, JSON.stringify(track("legacy-a")))
      localStorage.setItem(storageKey("account-a"), JSON.stringify(track("a")))
      setIdentity(id, loading)
      const get = vi.spyOn(api, "get").mockResolvedValue(response("network"))
      const { result } = renderHook(() => useNowPlaying(true), createWrapper())
      expect(result.current.data).toBeNull()
      expect(result.current.isPlaceholderData).toBe(true)
      await act(async () => {
        await result.current.refetch()
      })
      await expect(fetchNowPlaying()).rejects.toMatchObject({ name: "AbortError" })
      // The refetch promise can settle before React Query notifies the hook.
      // Its pending null placeholder is removed once the error is rendered.
      await waitFor(() => expect(result.current.isError).toBe(true))
      expect(result.current.error).toMatchObject({ name: "AbortError" })
      expect(result.current.data).toBeUndefined()
      expect(result.current.isPlaceholderData).toBe(false)
      expect(get).not.toHaveBeenCalled()
      expect(JSON.parse(localStorage.getItem(storageKey("account-a"))!)).toEqual(track("a"))
    }
  )

  it("rejects a delayed prior-account response before it reaches the caller", async () => {
    const pending = deferred<ReturnType<typeof response>>()
    vi.spyOn(api, "get").mockReturnValue(pending.promise)
    const request = fetchNowPlaying()
    const outcome = expect(request).rejects.toMatchObject({ name: "AbortError" })
    setIdentity("account-b")
    pending.resolve(response("a"))
    await outcome
  })

  it("does not dispatch a prior account's delayed reauthorization event", async () => {
    const pending = deferred<ReturnType<typeof response>>()
    vi.spyOn(api, "get").mockReturnValue(pending.promise)
    const reauth = vi.fn()
    window.addEventListener(SPOTIFY_REAUTH_EVENT, reauth)
    try {
      const request = fetchNowPlaying()
      const outcome = expect(request).rejects.toMatchObject({ name: "AbortError" })
      setIdentity("account-b")
      pending.reject(
        Object.assign(new Error("A expired"), { isAxiosError: true, response: { status: 401 } })
      )
      await outcome
      expect(reauth).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener(SPOTIFY_REAUTH_EVENT, reauth)
    }
  })

  it("discards late network data after the mounted hook changes accounts", async () => {
    const pending = deferred<ReturnType<typeof response>>()
    const get = vi
      .spyOn(api, "get")
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValue(response("b"))
    const { result } = renderHook(() => useNowPlaying(true), createWrapper())
    await waitFor(() => expect(get).toHaveBeenCalledOnce())
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(result.current.data).toEqual(track("b")))
    await act(async () => pending.resolve(response("a")))
    expect(result.current.data).toEqual(track("b"))
    expect(JSON.parse(localStorage.getItem(storageKey("account-b"))!)).toEqual(track("b"))
  })

  it("hides warm query and storage data before a remote session broadcast arrives", () => {
    const { client, wrapper } = createWrapper()
    client.setQueryData(nowPlayingQueryKey, track("a"))
    localStorage.setItem(storageKey("account-a"), JSON.stringify(track("a")))
    rotateOtherTab()
    const get = vi.spyOn(api, "get")
    const { result } = renderHook(() => useNowPlaying(true), { wrapper })
    expect(result.current.data).toBeNull()
    expect(get).not.toHaveBeenCalled()
    expect(JSON.parse(localStorage.getItem(storageKey("account-a"))!)).toEqual(track("a"))
  })

  it("fences persistence when the origin generation changes between render and passive effects", () => {
    const { client, wrapper } = createWrapper()
    client.setQueryData(nowPlayingQueryKey, track("a"))
    renderHook(
      () => {
        const query = useNowPlaying(false)
        useLayoutEffect(rotateOtherTab, [])
        return query
      },
      { wrapper }
    )
    expect(localStorage.getItem(storageKey("account-a"))).toBeNull()
    expect(localStorage.getItem(legacyKey)).toBeNull()
  })

  it("discards a delayed response when the same account's session expires", async () => {
    const pending = deferred<ReturnType<typeof response>>()
    vi.spyOn(api, "get").mockReturnValue(pending.promise)
    const request = fetchNowPlaying()
    const outcome = expect(request).rejects.toMatchObject({ name: "AbortError" })
    invalidateSessionEpoch()
    pending.resolve(response("a"))
    await outcome
  })

  it("does not expose A's track after production logout fails and B later confirms", async () => {
    vi.spyOn(api, "get")
      .mockResolvedValueOnce(response("a"))
      .mockRejectedValue(new Error("offline"))
    vi.spyOn(api, "post").mockRejectedValue(new Error("offline logout"))
    const { result } = renderHook(() => {
      const state = useAuthStore()
      const auth = useAuthApi(
        state.user,
        state.setUser,
        vi.fn(),
        () => setIdentity(null),
        vi.fn(),
        false,
        vi.fn(),
        vi.fn()
      )
      return { auth, playing: useNowPlaying(true) }
    }, createWrapper())
    await waitFor(() => expect(result.current.playing.data).toEqual(track("a")))
    await withExpectedConsole("error", "Logout failed", async () => {
      await act(async () => result.current.auth.logout())
    })
    expect(result.current.playing.data).toBeNull()
    act(() => setIdentity("account-b"))
    await waitFor(() => expect(result.current.playing.isError).toBe(true))
    expect(result.current.playing.data ?? null).toBeNull()
  })
})
