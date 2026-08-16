import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"

// Module-mock the api client (NEVER hit MSW for /api/ paths — the contract validator
// rejects off-schema responses, and we need precise error shapes for the resync branches).
const mockGet = vi.fn(async (..._a: unknown[]) => ({ data: {} }) as any)
const mockPost = vi.fn(async (..._a: unknown[]) => ({ data: {} }) as any)
const mockDelete = vi.fn(async (..._a: unknown[]) => ({ data: {} }) as any)
vi.mock("@/api/client", () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

// Control isAxiosError so we can drive the "shouldResync" branch deterministically.
const mockIsAxiosError = vi.fn((_e: unknown) => false)
vi.mock("axios", () => ({
  isAxiosError: (e: unknown) => mockIsAxiosError(e),
}))

// Stable t reference (a fresh `t` per render would re-run effects → loops; cheap insurance).
const stableT = (k: string) => k
const stableTranslation = {
  t: stableT,
  i18n: { language: "en", changeLanguage: () => Promise.resolve() },
}
vi.mock("react-i18next", () => ({
  useTranslation: () => stableTranslation,
}))

import { useEventRegistration } from "../useEventRegistration"

const mockUser = { id: 123, username: "u", email: "u@x.io", is_active: true } as any
const eventId = "event-456"
type HookProps = Parameters<typeof useEventRegistration>[0]

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

describe("useEventRegistration (branches)", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    mockIsAxiosError.mockReturnValue(false)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  // ---- sync() (lines 109-143) ----

  it("sync(): registered + qr token → persists token + sets registered (113-128, 138-139)", async () => {
    mockGet.mockResolvedValue({
      data: { is_registered: true, participant_count: 8, my_qr_token: "qr-99" },
    })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    let outcome: string | null = null
    await act(async () => {
      outcome = await result.current.sync()
    })

    expect(outcome).toBe("registered")
    await waitFor(() => expect(result.current.isRegistered).toBe(true))
    expect(result.current.participantCount).toBe(8)
    expect(result.current.qrToken).toBe("qr-99")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("qr-99")
  })

  it("sync(): unregistered → clears qr + removes from storage (129-139)", async () => {
    localStorage.setItem(`event:qr:${eventId}:123`, "stale")
    mockGet.mockResolvedValue({
      data: { is_registered: false, participant_count: 2 },
    })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true })
    )

    let outcome: string | null = null
    await act(async () => {
      outcome = await result.current.sync()
    })

    expect(outcome).toBe("unregistered")
    await waitFor(() => expect(result.current.isRegistered).toBe(false))
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
  })

  it("sync(): registered but no qr token → registered without persisting (119-121 false)", async () => {
    mockGet.mockResolvedValue({
      data: { is_registered: true, participant_count: 5 },
    })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    let outcome: string | null = null
    await act(async () => {
      outcome = await result.current.sync()
    })

    expect(outcome).toBe("registered")
    await waitFor(() => expect(result.current.isRegistered).toBe(true))
    expect(result.current.qrToken).toBeUndefined()
  })

  it("sync(): request throws → returns null (140-142)", async () => {
    mockGet.mockRejectedValue(new Error("network"))

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    let outcome: string | null = "x"
    await act(async () => {
      outcome = await result.current.sync()
    })

    expect(outcome).toBeNull()
  })

  // ---- register() (lines 145-189) ----

  it("register(): success persists qr token to localStorage (153-163)", async () => {
    mockPost.mockResolvedValue({ data: { qr_code: "code-7" } })
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
        initialParticipantCount: 4,
        onNotify,
      })
    )

    await act(async () => {
      await result.current.register()
    })

    await waitFor(() => expect(result.current.isRegistered).toBe(true))
    expect(result.current.qrToken).toBe("code-7")
    expect(result.current.participantCount).toBe(5)
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("code-7")
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerSuccess")
  })

  it("register(): 500 error → resync to registered → success notify (167-179)", async () => {
    const axiosErr: any = {
      isAxiosError: true,
      code: undefined,
      response: { status: 500, data: {} },
    }
    mockPost.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((e: unknown) => e === axiosErr)
    // After failed POST, the resync GET reports the user is actually registered.
    mockGet.mockResolvedValue({
      data: { is_registered: true, participant_count: 6, my_qr_token: "recovered" },
    })
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false, onNotify })
    )

    await act(async () => {
      await result.current.register()
    })

    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerSuccess")
  })

  it("register(): network error, resync stays unregistered → detail/failure notify (167-187)", async () => {
    const axiosErr: any = {
      isAxiosError: true,
      code: "ERR_NETWORK",
      response: undefined,
    }
    mockPost.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((e: unknown) => e === axiosErr)
    mockGet.mockResolvedValue({ data: { is_registered: false, participant_count: 3 } })
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false, onNotify })
    )

    await act(async () => {
      await result.current.register()
    })

    await waitFor(() => expect(onNotify).toHaveBeenCalled())
    // resync returned "unregistered" (not "registered"), so it falls through to the failure detail.
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerFailure")
  })

  it("register(): non-resync error with server detail string → detail notify (182-186)", async () => {
    const axiosErr: any = {
      isAxiosError: true,
      code: undefined,
      response: { status: 400, data: { detail: "Already full" } },
    }
    mockPost.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((e: unknown) => e === axiosErr)
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false, onNotify })
    )

    await act(async () => {
      await result.current.register()
    })

    await waitFor(() => expect(onNotify).toHaveBeenCalledWith("Already full"))
    // 400 is not a resync case → no GET issued.
    expect(mockGet).not.toHaveBeenCalled()
  })

  // ---- unregister() (lines 191-232) ----

  it("unregister(): success removes qr from localStorage (199-209)", async () => {
    localStorage.setItem(`event:qr:${eventId}:123`, "old")
    mockDelete.mockResolvedValue({ data: null })
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialParticipantCount: 10,
        onNotify,
      })
    )

    await act(async () => {
      await result.current.unregister()
    })

    await waitFor(() => expect(result.current.isRegistered).toBe(false))
    expect(result.current.participantCount).toBe(9)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.unregisterSuccess")
  })

  it("unregister(): 503 error → resync to unregistered → success notify (212-223)", async () => {
    const axiosErr: any = {
      isAxiosError: true,
      code: undefined,
      response: { status: 503, data: {} },
    }
    mockDelete.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((e: unknown) => e === axiosErr)
    mockGet.mockResolvedValue({ data: { is_registered: false, participant_count: 1 } })
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true, onNotify })
    )

    await act(async () => {
      await result.current.unregister()
    })

    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.unregisterSuccess")
  })

  it("unregister(): resync stays registered → falls through to failure detail (212-232)", async () => {
    const axiosErr: any = {
      isAxiosError: true,
      code: "ECONNABORTED",
      response: undefined,
    }
    mockDelete.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((e: unknown) => e === axiosErr)
    // resync says still registered → outcome !== "unregistered" → use failure detail.
    mockGet.mockResolvedValue({ data: { is_registered: true, participant_count: 7 } })
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true, onNotify })
    )

    await act(async () => {
      await result.current.unregister()
    })

    await waitFor(() => expect(onNotify).toHaveBeenCalled())
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.unregisterFailure")
  })

  it("unregister(): non-resync error with detail string → detail notify (227-231)", async () => {
    const axiosErr: any = {
      isAxiosError: true,
      code: undefined,
      response: { status: 409, data: { detail: "Cannot leave now" } },
    }
    mockDelete.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((e: unknown) => e === axiosErr)
    const onNotify = vi.fn()

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true, onNotify })
    )

    await act(async () => {
      await result.current.unregister()
    })

    await waitFor(() => expect(onNotify).toHaveBeenCalledWith("Cannot leave now"))
    expect(mockGet).not.toHaveBeenCalled()
  })

  // ---- register/unregister stopPropagation guard (lines 146, 192) ----

  it("register/unregister call stopPropagation when given an event (146, 192)", async () => {
    mockPost.mockResolvedValue({ data: { qr_code: "c" } })
    mockDelete.mockResolvedValue({ data: null })
    const stop = vi.fn()
    const evt = { stopPropagation: stop } as unknown as React.MouseEvent

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    await act(async () => {
      await result.current.register(evt)
    })
    await act(async () => {
      await result.current.unregister(evt)
    })

    expect(stop).toHaveBeenCalledTimes(2)
  })

  it("ignores storage failures during restore, QR recovery, and sync", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage read failed")
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage write failed")
    })
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage delete failed")
    })
    mockGet
      .mockResolvedValueOnce({
        data: { is_registered: true, participant_count: 4, my_qr_token: "remote-qr" },
      })
      .mockResolvedValueOnce({ data: { is_registered: false, participant_count: 3 } })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true })
    )

    await act(async () => {
      expect(await result.current.sync()).toBe("registered")
      expect(await result.current.sync()).toBe("unregistered")
    })
    expect(result.current.isRegistered).toBe(false)
  })

  it("ignores storage failures for initial QR tokens and attendance success", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage read failed")
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage write failed")
    })
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage delete failed")
    })
    mockPost.mockResolvedValue({ data: { qr_code: "created-qr" } })
    mockDelete.mockResolvedValue({ data: null })

    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
        initialQrToken: "initial-qr",
      })
    )

    await act(async () => {
      await result.current.register()
      await result.current.unregister()
    })
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockDelete).toHaveBeenCalledTimes(1)
  })

  it("skips user registration cache effects for anonymous visitors", () => {
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: null, initialRegistered: false })
    )

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.qrToken).toBeUndefined()
  })

  it("resets registration state before persisting a new event and user scope", async () => {
    const eventA = "event-a"
    const eventB = "event-b"
    const userB = { ...mockUser, id: 456 }
    localStorage.setItem(`event:reg:${eventA}:123`, "1")
    localStorage.setItem(`event:qr:${eventA}:123`, "qr-A")

    type Props = {
      eventId: string
      user: typeof mockUser
      initialRegistered: boolean
      initialParticipantCount: number
      initialQrToken?: string
    }
    const initialProps: Props = {
      eventId: eventA,
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 8,
      initialQrToken: "qr-A",
    }
    const { result, rerender } = renderHook((props: Props) => useEventRegistration(props), {
      initialProps,
    })

    await waitFor(() => expect(result.current.isRegistered).toBe(true))
    await waitFor(() => expect(result.current.qrToken).toBe("qr-A"))
    expect(result.current.participantCount).toBe(8)

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    rerender({
      eventId: eventB,
      user: userB,
      initialRegistered: false,
      initialParticipantCount: 2,
      initialQrToken: undefined,
    })

    await waitFor(() => expect(result.current.isRegistered).toBe(false))
    expect(result.current.participantCount).toBe(2)
    expect(result.current.qrToken).toBeUndefined()
    expect(setItem.mock.calls).not.toContainEqual([`event:reg:${eventB}:456`, "1"])
    expect(setItem.mock.calls).not.toContainEqual([`event:qr:${eventB}:456`, "qr-A"])
  })

  it("ignores a stale sync success after the event scope changes", async () => {
    const request = deferred<{ data: Record<string, unknown> }>()
    mockGet.mockReturnValueOnce(request.promise)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 3,
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    const operation = result.current.sync()
    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 40,
      onNotify,
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(40)
    expect(result.current.qrToken).toBeUndefined()

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    let outcome: string | null = "pending"
    await act(async () => {
      request.resolve({
        data: { is_registered: true, participant_count: 9, my_qr_token: "qr-A" },
      })
      outcome = await operation
    })

    expect(outcome).toBeNull()
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(40)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem("event:reg:event-b:123")).toBeNull()
    expect(localStorage.getItem("event:qr:event-b:123")).toBeNull()
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not leak a pending or completed registration into a new user scope", async () => {
    const request = deferred<{ data: { qr_code: string } }>()
    mockPost.mockReturnValueOnce(request.promise)
    const onNotify = vi.fn()
    const userB = { ...mockUser, id: 456 }
    const initialProps: HookProps = {
      eventId,
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 3,
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.register()
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(4)

    rerender({
      eventId,
      user: userB,
      initialRegistered: false,
      initialParticipantCount: 50,
      onNotify,
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(50)
    expect(result.current.qrToken).toBeUndefined()

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    await act(async () => {
      request.resolve({ data: { qr_code: "qr-A" } })
      await request.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(50)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:reg:${eventId}:456`)).toBeNull()
    expect(localStorage.getItem(`event:qr:${eventId}:456`)).toBeNull()
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not notify for a stale registration error after the event scope changes", async () => {
    const request = deferred<{ data: { qr_code: string } }>()
    mockPost.mockReturnValueOnce(request.promise)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 5,
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.register()
    })
    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 51,
      onNotify,
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(51)

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    await act(async () => {
      request.reject(new Error("registration failed"))
      await request.promise.catch(() => undefined)
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(51)
    expect(result.current.qrToken).toBeUndefined()
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not notify when a registration resync becomes stale", async () => {
    const postRequest = deferred<{ data: { qr_code: string } }>()
    const syncRequest = deferred<{ data: Record<string, unknown> }>()
    mockPost.mockReturnValueOnce(postRequest.promise)
    mockGet.mockReturnValueOnce(syncRequest.promise)
    const networkError = { code: "ERR_NETWORK", response: undefined }
    mockIsAxiosError.mockImplementation((error: unknown) => error === networkError)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 6,
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.register()
    })
    await act(async () => {
      postRequest.reject(networkError)
      await postRequest.promise.catch(() => undefined)
      await Promise.resolve()
    })
    await waitFor(() => expect(mockGet).toHaveBeenCalledOnce())

    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 52,
      onNotify,
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(52)

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    await act(async () => {
      syncRequest.resolve({
        data: { is_registered: true, participant_count: 10, my_qr_token: "qr-A" },
      })
      await syncRequest.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(52)
    expect(result.current.qrToken).toBeUndefined()
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not leak a pending or completed unregistration into a new user scope", async () => {
    const request = deferred<{ data: null }>()
    mockDelete.mockReturnValueOnce(request.promise)
    const onNotify = vi.fn()
    const userB = { ...mockUser, id: 456 }
    const initialProps: HookProps = {
      eventId,
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 8,
      initialQrToken: "qr-A",
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.unregister()
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(7)

    rerender({
      eventId,
      user: userB,
      initialRegistered: true,
      initialParticipantCount: 60,
      initialQrToken: "qr-B",
      onNotify,
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(60)
    expect(result.current.qrToken).toBe("qr-B")

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    await act(async () => {
      request.resolve({ data: null })
      await request.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(60)
    expect(result.current.qrToken).toBe("qr-B")
    expect(localStorage.getItem(`event:reg:${eventId}:456`)).toBe("1")
    expect(localStorage.getItem(`event:qr:${eventId}:456`)).toBe("qr-B")
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not notify for a stale unregistration error after the event scope changes", async () => {
    const request = deferred<{ data: null }>()
    mockDelete.mockReturnValueOnce(request.promise)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 9,
      initialQrToken: "qr-A",
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.unregister()
    })
    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 61,
      initialQrToken: "qr-B",
      onNotify,
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(61)
    expect(result.current.qrToken).toBe("qr-B")

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    await act(async () => {
      request.reject(new Error("unregistration failed"))
      await request.promise.catch(() => undefined)
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(61)
    expect(result.current.qrToken).toBe("qr-B")
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not notify when an unregistration resync becomes stale", async () => {
    const deleteRequest = deferred<{ data: null }>()
    const syncRequest = deferred<{ data: Record<string, unknown> }>()
    mockDelete.mockReturnValueOnce(deleteRequest.promise)
    mockGet.mockReturnValueOnce(syncRequest.promise)
    const networkError = { code: "ERR_NETWORK", response: undefined }
    mockIsAxiosError.mockImplementation((error: unknown) => error === networkError)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 10,
      initialQrToken: "qr-A",
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.unregister()
    })
    await act(async () => {
      deleteRequest.reject(networkError)
      await deleteRequest.promise.catch(() => undefined)
      await Promise.resolve()
    })
    await waitFor(() => expect(mockGet).toHaveBeenCalledOnce())

    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 62,
      initialQrToken: "qr-B",
      onNotify,
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(62)
    expect(result.current.qrToken).toBe("qr-B")

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    await act(async () => {
      syncRequest.resolve({ data: { is_registered: false, participant_count: 2 } })
      await syncRequest.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(62)
    expect(result.current.qrToken).toBe("qr-B")
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("tracks registration loading only for the current scope", async () => {
    const requestA = deferred<{ data: { qr_code: string } }>()
    const requestB = deferred<{ data: { qr_code: string } }>()
    mockPost.mockReturnValueOnce(requestA.promise).mockReturnValueOnce(requestB.promise)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 3,
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.register()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(true))

    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 40,
      onNotify,
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(40)
    expect.soft(result.current.isLoading).toBe(false)

    act(() => {
      void result.current.register()
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(41)
    expect(result.current.isLoading).toBe(true)

    await act(async () => {
      requestB.resolve({ data: { qr_code: "qr-B" } })
      await requestB.promise
      await Promise.resolve()
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(41)
    expect.soft(result.current.isLoading).toBe(false)

    await act(async () => {
      requestA.resolve({ data: { qr_code: "qr-A" } })
      await requestA.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(41)
    expect(result.current.qrToken).toBe("qr-B")
  })

  it("tracks unregistration loading only for the current scope", async () => {
    const requestA = deferred<{ data: null }>()
    const requestB = deferred<{ data: null }>()
    mockDelete.mockReturnValueOnce(requestA.promise).mockReturnValueOnce(requestB.promise)
    const onNotify = vi.fn()
    const initialProps: HookProps = {
      eventId: "event-a",
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 10,
      initialQrToken: "qr-A",
      onNotify,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    act(() => {
      void result.current.unregister()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(true))

    rerender({
      eventId: "event-b",
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 60,
      initialQrToken: "qr-B",
      onNotify,
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(60)
    expect(result.current.qrToken).toBe("qr-B")
    expect.soft(result.current.isLoading).toBe(false)

    act(() => {
      void result.current.unregister()
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(59)
    expect(result.current.isLoading).toBe(true)

    await act(async () => {
      requestB.resolve({ data: null })
      await requestB.promise
      await Promise.resolve()
    })
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(59)
    expect.soft(result.current.isLoading).toBe(false)

    await act(async () => {
      requestA.resolve({ data: null })
      await requestA.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(59)
    expect(result.current.qrToken).toBeUndefined()
  })

  it("keeps loading until every concurrent operation in the current scope settles", async () => {
    const requestA = deferred<{ data: { qr_code: string } }>()
    const requestB = deferred<{ data: { qr_code: string } }>()
    mockPost.mockReturnValueOnce(requestA.promise).mockReturnValueOnce(requestB.promise)
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
        initialParticipantCount: 2,
      })
    )

    act(() => {
      void result.current.register()
      void result.current.register()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(true))

    await act(async () => {
      requestA.resolve({ data: { qr_code: "qr-A" } })
      await requestA.promise
      await Promise.resolve()
    })
    expect(result.current.isLoading).toBe(true)

    await act(async () => {
      requestB.resolve({ data: { qr_code: "qr-B" } })
      await requestB.promise
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(4)
    expect(result.current.qrToken).toBe("qr-B")
  })

  it("settles a pending registration after unmount without side effects", async () => {
    const request = deferred<{ data: { qr_code: string } }>()
    mockPost.mockReturnValueOnce(request.promise)
    const onNotify = vi.fn()
    const { result, unmount } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
        initialParticipantCount: 2,
        onNotify,
      })
    )

    act(() => {
      void result.current.register()
    })
    await waitFor(() => expect(result.current.isLoading).toBe(true))
    unmount()

    await act(async () => {
      request.resolve({ data: { qr_code: "qr-after-unmount" } })
      await request.promise
      await Promise.resolve()
    })
    expect(onNotify).not.toHaveBeenCalled()
  })
})
