import { useCallback, useEffect, useRef, useState } from "react"
import { renderHook, act } from "@testing-library/react"
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
    mockGet.mockReset()
    mockPost.mockReset()
    mockDelete.mockReset()
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
    expect(result.current.isRegistered).toBe(true)
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
    expect(result.current.isRegistered).toBe(false)
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
    expect(result.current.isRegistered).toBe(true)
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

  it("uses the documented defaults for an omitted registration state", () => {
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialParticipantCount: 4 })
    )

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(4)
    expect(result.current.qrToken).toBeUndefined()
  })

  // ---- register() (lines 145-189) ----

  it("register(): success persists qr token to localStorage (153-163)", async () => {
    mockPost.mockResolvedValue({
      data: {
        id: "attendance-7",
        user_id: "123",
        event_id: eventId,
        registered_at: new Date().toISOString(),
        qr_token: "code-7",
      },
    })
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

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.qrToken).toBe("code-7")
    expect(result.current.participantCount).toBe(5)
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("code-7")
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerSuccess")
  })

  it("register(): an optional null QR token does not persist an invalid value", async () => {
    mockPost.mockResolvedValue({ data: { qr_token: null } })
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    await act(async () => {
      await result.current.register()
    })

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
  })

  it("requests push education only after a successful authenticated registration", async () => {
    mockPost.mockResolvedValue({ data: { qr_token: "code-7" } })
    const request = vi.fn()
    window.addEventListener("ecosystem:push-education-requested", request)
    try {
      const { result } = renderHook(() =>
        useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
      )
      await act(async () => {
        await result.current.register()
      })
      expect(request).toHaveBeenCalledOnce()
    } finally {
      window.removeEventListener("ecosystem:push-education-requested", request)
    }
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

    expect(mockGet).toHaveBeenCalled()
    expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerSuccess")
  })

  it("register(): a recovered anonymous registration does not request push education", async () => {
    const axiosErr = { isAxiosError: true, response: { status: 500, data: {} } }
    mockPost.mockRejectedValue(axiosErr)
    mockIsAxiosError.mockImplementation((error: unknown) => error === axiosErr)
    mockGet.mockResolvedValue({ data: { is_registered: true, participant_count: 1 } })
    const onNotify = vi.fn()
    const onEducationRequest = vi.fn()
    window.addEventListener("ecosystem:push-education-requested", onEducationRequest)
    try {
      const { result } = renderHook(() =>
        useEventRegistration({ eventId, user: null, initialRegistered: false, onNotify })
      )

      await act(async () => {
        await result.current.register()
      })

      expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerSuccess")
      expect(result.current.isRegistered).toBe(true)
      expect(onEducationRequest).not.toHaveBeenCalled()
      expect(localStorage.length).toBe(0)
    } finally {
      window.removeEventListener("ecosystem:push-education-requested", onEducationRequest)
    }
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

    expect(onNotify).toHaveBeenCalled()
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

    expect(onNotify).toHaveBeenCalledWith("Already full")
    // 400 is not a resync case → no GET issued.
    expect(mockGet).not.toHaveBeenCalled()
  })

  it.each([
    {
      label: "abort code",
      error: { isAxiosError: true, code: "ECONNABORTED", response: { status: 400, data: {} } },
    },
    {
      label: "network code",
      error: { isAxiosError: true, code: "ERR_NETWORK", response: { status: 400, data: {} } },
    },
    {
      label: "missing response",
      error: { isAxiosError: true, code: undefined, response: undefined },
    },
    {
      label: "server response",
      error: { isAxiosError: true, code: undefined, response: { status: 500, data: {} } },
    },
  ])("register: resynchronizes after a $label failure", async ({ error }) => {
    mockPost.mockRejectedValue(error)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    mockGet.mockResolvedValue({ data: { is_registered: false, participant_count: 4 } })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    await act(async () => {
      await result.current.register()
    })

    expect(mockGet).toHaveBeenCalledWith(`/events/${eventId}`)
  })

  it("register: keeps client errors local and uses the translated fallback for non-string detail", async () => {
    const error = {
      isAxiosError: true,
      code: undefined,
      response: { status: 422, data: { detail: 42 } },
    }
    mockPost.mockRejectedValue(error)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    const onNotify = vi.fn()
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false, onNotify })
    )

    await act(async () => {
      await result.current.register()
    })

    expect(onNotify).toHaveBeenCalledWith("events:card.messages.registerFailure")
    expect(mockGet).not.toHaveBeenCalled()
  })

  it("register: does not require an optional notification callback", async () => {
    const error = { isAxiosError: false, response: { status: 422, data: {} } }
    mockPost.mockRejectedValue(error)
    mockIsAxiosError.mockReturnValue(false)

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    await expect(
      act(async () => {
        await result.current.register()
      })
    ).resolves.toBeUndefined()
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

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(9)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
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

    expect(mockGet).toHaveBeenCalled()
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

    expect(onNotify).toHaveBeenCalled()
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

    expect(onNotify).toHaveBeenCalledWith("Cannot leave now")
    expect(mockGet).not.toHaveBeenCalled()
  })

  it.each([
    {
      label: "abort code",
      error: { isAxiosError: true, code: "ECONNABORTED", response: { status: 400, data: {} } },
    },
    {
      label: "network code",
      error: { isAxiosError: true, code: "ERR_NETWORK", response: { status: 400, data: {} } },
    },
    {
      label: "missing response",
      error: { isAxiosError: true, code: undefined, response: undefined },
    },
    {
      label: "server response",
      error: { isAxiosError: true, code: undefined, response: { status: 500, data: {} } },
    },
  ])("unregister: resynchronizes after a $label failure", async ({ error }) => {
    mockDelete.mockRejectedValue(error)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    mockGet.mockResolvedValue({ data: { is_registered: true, participant_count: 4 } })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true })
    )

    await act(async () => {
      await result.current.unregister()
    })

    expect(mockGet).toHaveBeenCalledWith(`/events/${eventId}`)
  })

  it("unregister: uses the translated fallback for non-string detail and keeps the callback optional", async () => {
    const error = {
      isAxiosError: true,
      code: undefined,
      response: { status: 422, data: { detail: 42 } },
    }
    mockDelete.mockRejectedValue(error)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true })
    )

    await expect(
      act(async () => {
        await result.current.unregister()
      })
    ).resolves.toBeUndefined()
  })

  it("sends the event id in the attendance request", async () => {
    mockPost.mockResolvedValue({ data: { qr_token: "request-qr" } })
    mockDelete.mockResolvedValue({ data: null })

    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )
    await act(async () => {
      await result.current.register()
    })
    expect(mockPost).toHaveBeenCalledWith("/events/attendance", { event_id: eventId })

    await act(async () => {
      await result.current.unregister()
    })
    expect(mockDelete).toHaveBeenCalledWith("/events/attendance", { data: { event_id: eventId } })
  })

  // ---- register/unregister stopPropagation guard (lines 146, 192) ----

  it("register/unregister call stopPropagation when given an event (146, 192)", async () => {
    mockPost.mockResolvedValue({ data: { qr_token: "c" } })
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
    mockPost.mockResolvedValue({ data: { qr_token: "created-qr" } })
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
    const readCache = vi.spyOn(Storage.prototype, "getItem")
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: null, initialRegistered: false })
    )

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.qrToken).toBeUndefined()
    expect(readCache).not.toHaveBeenCalled()
  })

  it("uses the anonymous QR namespace when an anonymous registration succeeds", async () => {
    mockPost.mockResolvedValue({ data: { qr_token: "anon-qr" } })
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: null,
        initialRegistered: false,
      })
    )

    await act(async () => {
      await result.current.register()
    })

    expect(result.current.qrToken).toBe("anon-qr")
    expect(localStorage.getItem(`event:qr:${eventId}:anon`)).toBe("anon-qr")
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

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.qrToken).toBe("qr-A")
    expect(result.current.participantCount).toBe(8)

    const setItem = vi.spyOn(Storage.prototype, "setItem")
    rerender({
      eventId: eventB,
      user: userB,
      initialRegistered: false,
      initialParticipantCount: 2,
      initialQrToken: undefined,
    })

    expect(result.current.isRegistered).toBe(false)
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
    const request = deferred<{ data: { qr_token: string } }>()
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
      request.resolve({ data: { qr_token: "qr-A" } })
      await request.promise
      await Promise.resolve()
    })
    expect(result.current.isLoading).toBe(false)

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
    const request = deferred<{ data: { qr_token: string } }>()
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
    expect(result.current.isLoading).toBe(false)

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(51)
    expect(result.current.qrToken).toBeUndefined()
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("does not notify when a registration resync becomes stale", async () => {
    const postRequest = deferred<{ data: { qr_token: string } }>()
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
    expect(mockGet).toHaveBeenCalledOnce()

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
    expect(result.current.isLoading).toBe(false)

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
    expect(result.current.isLoading).toBe(false)

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
    expect(result.current.isLoading).toBe(false)

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
    expect(mockGet).toHaveBeenCalledOnce()

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
    expect(result.current.isLoading).toBe(false)

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(62)
    expect(result.current.qrToken).toBe("qr-B")
    expect(setItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("tracks registration loading only for the current scope", async () => {
    const requestA = deferred<{ data: { qr_token: string } }>()
    const requestB = deferred<{ data: { qr_token: string } }>()
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
    expect(result.current.isLoading).toBe(true)

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
      requestB.resolve({ data: { qr_token: "qr-B" } })
      await requestB.promise
      await Promise.resolve()
    })
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(41)
    expect.soft(result.current.isLoading).toBe(false)

    await act(async () => {
      requestA.resolve({ data: { qr_token: "qr-A" } })
      await requestA.promise
      await Promise.resolve()
    })
    expect(result.current.isLoading).toBe(false)
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
    expect(result.current.isLoading).toBe(true)

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
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(59)
    expect(result.current.qrToken).toBeUndefined()
  })

  it("keeps loading until every concurrent operation in the current scope settles", async () => {
    const requestA = deferred<{ data: { qr_token: string } }>()
    const requestB = deferred<{ data: { qr_token: string } }>()
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
    expect(result.current.isLoading).toBe(true)

    await act(async () => {
      requestA.resolve({ data: { qr_token: "qr-A" } })
      await requestA.promise
      await Promise.resolve()
    })
    expect(result.current.isLoading).toBe(true)

    await act(async () => {
      requestB.resolve({ data: { qr_token: "qr-B" } })
      await requestB.promise
      await Promise.resolve()
    })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(4)
    expect(result.current.qrToken).toBe("qr-B")
  })

  it("settles a pending registration after unmount without side effects", async () => {
    const request = deferred<{ data: { qr_token: string } }>()
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
    expect(result.current.isLoading).toBe(true)
    unmount()

    await act(async () => {
      request.resolve({ data: { qr_token: "qr-after-unmount" } })
      await request.promise
      await Promise.resolve()
    })
    expect(onNotify).not.toHaveBeenCalled()
  })

  it("updates registration and participant state when the current event props refresh", () => {
    const initialProps: HookProps = {
      eventId,
      user: mockUser,
      initialRegistered: false,
      initialParticipantCount: 4,
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    rerender({ ...initialProps, initialRegistered: true, initialParticipantCount: 17 })

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(17)
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")

    rerender({ ...initialProps, initialRegistered: true, initialParticipantCount: 0 })

    expect(result.current.participantCount).toBe(0)
    expect(result.current.isRegistered).toBe(true)
  })

  it("recovers a QR token only from the registered event and user cache", () => {
    localStorage.setItem(`event:qr:${eventId}:123`, "current-user-qr")
    localStorage.setItem(`event:qr:${eventId}:456`, "other-user-qr")
    localStorage.setItem("event:qr:other-event:123", "other-event-qr")
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: true })
    )

    expect(result.current.qrToken).toBe("current-user-qr")
    expect(localStorage.getItem(`event:qr:${eventId}:456`)).toBe("other-user-qr")
    expect(localStorage.getItem("event:qr:other-event:123")).toBe("other-event-qr")
  })

  it("removes a stale QR cache only for the unregistered event and user", () => {
    localStorage.setItem(`event:qr:${eventId}:123`, "expired-qr")
    localStorage.setItem(`event:reg:${eventId}:456`, "1")
    localStorage.setItem(`event:qr:${eventId}:456`, "other-user-qr")
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialRegistered: false })
    )

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
    expect(localStorage.getItem(`event:reg:${eventId}:456`)).toBe("1")
    expect(localStorage.getItem(`event:qr:${eventId}:456`)).toBe("other-user-qr")
  })

  it("reconciles a refreshed QR token without discarding an omitted participant count", async () => {
    localStorage.setItem(`event:qr:${eventId}:123`, "previous-qr")
    mockGet.mockResolvedValueOnce({
      data: { is_registered: true, my_qr_token: "refreshed-qr" },
    })
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialParticipantCount: 14,
      })
    )
    expect(result.current.qrToken).toBe("previous-qr")

    await act(async () => {
      expect(await result.current.sync()).toBe("registered")
    })

    expect(mockGet).toHaveBeenCalledExactlyOnceWith(`/events/${eventId}`)
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(14)
    expect(result.current.qrToken).toBe("refreshed-qr")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("refreshed-qr")
  })

  it("uses the new event request and cache scope after a rerender", async () => {
    mockGet.mockResolvedValueOnce({
      data: { is_registered: true, participant_count: 24, my_qr_token: "new-event-qr" },
    })
    const initialProps: HookProps = { eventId, user: mockUser }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })
    rerender({ eventId: "new-event", user: { ...mockUser, id: 456 } })

    await act(async () => {
      expect(await result.current.sync()).toBe("registered")
    })

    expect(mockGet).toHaveBeenCalledExactlyOnceWith("/events/new-event")
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(24)
    expect(result.current.qrToken).toBe("new-event-qr")
    expect(localStorage.getItem("event:reg:new-event:456")).toBe("1")
    expect(localStorage.getItem("event:qr:new-event:456")).toBe("new-event-qr")
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
  })

  it("rolls back a pending registration rejected by the server", async () => {
    const request = deferred<{ data: { qr_token: string } }>()
    const error = { isAxiosError: true, response: { status: 409, data: { detail: "Event full" } } }
    mockPost.mockReturnValueOnce(request.promise)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    const onNotify = vi.fn()
    const { result } = renderHook(() =>
      useEventRegistration({ eventId, user: mockUser, initialParticipantCount: 12, onNotify })
    )

    act(() => {
      void result.current.register()
    })

    expect
      .soft(mockPost)
      .toHaveBeenCalledExactlyOnceWith("/events/attendance", { event_id: eventId })
    expect.soft(result.current.isLoading).toBe(true)
    expect.soft(result.current.isRegistered).toBe(true)
    expect.soft(result.current.participantCount).toBe(13)
    expect.soft(result.current.qrToken).toBeUndefined()
    expect.soft(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect.soft(onNotify).not.toHaveBeenCalled()

    await act(async () => {
      request.reject(error)
      await request.promise.catch(() => undefined)
    })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(12)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
    expect(onNotify).toHaveBeenCalledExactlyOnceWith("Event full")
    expect(mockGet).not.toHaveBeenCalled()
  })

  it("keeps registration pending through reconciliation and adopts the server count and QR", async () => {
    const registration = deferred<{ data: { qr_token: string } }>()
    const reconciliation = deferred<{
      data: { is_registered: boolean; participant_count: number; my_qr_token: string }
    }>()
    const error = { isAxiosError: true, code: "ERR_NETWORK" }
    mockPost.mockReturnValueOnce(registration.promise)
    mockGet.mockReturnValueOnce(reconciliation.promise)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    const onNotify = vi.fn()
    const onEducationRequest = vi.fn()
    window.addEventListener("ecosystem:push-education-requested", onEducationRequest)
    try {
      const { result } = renderHook(() =>
        useEventRegistration({ eventId, user: mockUser, initialParticipantCount: 12, onNotify })
      )
      act(() => {
        void result.current.register()
      })
      expect.soft(result.current.isLoading).toBe(true)
      expect.soft(result.current.isRegistered).toBe(true)
      expect.soft(result.current.participantCount).toBe(13)

      await act(async () => {
        registration.reject(error)
        await registration.promise.catch(() => undefined)
      })

      expect.soft(mockGet).toHaveBeenCalledExactlyOnceWith(`/events/${eventId}`)
      expect.soft(result.current.isLoading).toBe(true)
      expect.soft(result.current.isRegistered).toBe(true)
      expect.soft(result.current.participantCount).toBe(13)
      expect.soft(onNotify).not.toHaveBeenCalled()
      expect.soft(onEducationRequest).not.toHaveBeenCalled()

      await act(async () => {
        reconciliation.resolve({
          data: { is_registered: true, participant_count: 28, my_qr_token: "reconciled-qr" },
        })
        await reconciliation.promise
      })

      expect(result.current.isLoading).toBe(false)
      expect(result.current.isRegistered).toBe(true)
      expect(result.current.participantCount).toBe(28)
      expect(result.current.qrToken).toBe("reconciled-qr")
      expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
      expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("reconciled-qr")
      expect(onNotify).toHaveBeenCalledExactlyOnceWith("events:card.messages.registerSuccess")
      expect(onEducationRequest).toHaveBeenCalledOnce()
    } finally {
      window.removeEventListener("ecosystem:push-education-requested", onEducationRequest)
    }
  })

  it("restores the registered state and QR when pending unregistration is rejected", async () => {
    const request = deferred<{ data: null }>()
    const error = {
      isAxiosError: true,
      response: { status: 422, data: { detail: [{ msg: "Cannot cancel this registration" }] } },
    }
    mockDelete.mockReturnValueOnce(request.promise)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    const onNotify = vi.fn()
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialParticipantCount: 12,
        initialQrToken: "existing-qr",
        onNotify,
      })
    )

    act(() => {
      void result.current.unregister()
    })

    expect.soft(mockDelete).toHaveBeenCalledExactlyOnceWith("/events/attendance", {
      data: { event_id: eventId },
    })
    expect.soft(result.current.isLoading).toBe(true)
    expect.soft(result.current.isRegistered).toBe(false)
    expect.soft(result.current.participantCount).toBe(11)
    expect.soft(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
    expect.soft(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("existing-qr")
    expect.soft(onNotify).not.toHaveBeenCalled()

    await act(async () => {
      request.reject(error)
      await request.promise.catch(() => undefined)
    })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(12)
    expect(result.current.qrToken).toBe("existing-qr")
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("existing-qr")
    expect(onNotify).toHaveBeenCalledExactlyOnceWith("events:card.messages.unregisterFailure")
    expect(mockGet).not.toHaveBeenCalled()
  })

  it("keeps unregistration pending until reconciliation confirms cancellation", async () => {
    const cancellation = deferred<{ data: null }>()
    const reconciliation = deferred<{
      data: { is_registered: boolean; participant_count: number; my_qr_token: null }
    }>()
    const error = { isAxiosError: true, response: { status: 503, data: {} } }
    mockDelete.mockReturnValueOnce(cancellation.promise)
    mockGet.mockReturnValueOnce(reconciliation.promise)
    mockIsAxiosError.mockImplementation((value: unknown) => value === error)
    const onNotify = vi.fn()
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialParticipantCount: 12,
        initialQrToken: "existing-qr",
        onNotify,
      })
    )
    act(() => {
      void result.current.unregister()
    })
    expect.soft(result.current.isLoading).toBe(true)
    expect.soft(result.current.isRegistered).toBe(false)
    expect.soft(result.current.participantCount).toBe(11)

    await act(async () => {
      cancellation.reject(error)
      await cancellation.promise.catch(() => undefined)
    })

    expect.soft(mockGet).toHaveBeenCalledExactlyOnceWith(`/events/${eventId}`)
    expect.soft(result.current.isLoading).toBe(true)
    expect.soft(result.current.isRegistered).toBe(false)
    expect.soft(result.current.participantCount).toBe(11)
    expect.soft(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
    expect.soft(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("existing-qr")
    expect.soft(onNotify).not.toHaveBeenCalled()

    await act(async () => {
      reconciliation.resolve({
        data: { is_registered: false, participant_count: 23, my_qr_token: null },
      })
      await reconciliation.promise
    })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(23)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
    expect(onNotify).toHaveBeenCalledExactlyOnceWith("events:card.messages.unregisterSuccess")
  })

  it.each(["register", "unregister"] as const)(
    "completes a recovered %s without a notification callback",
    async (operation) => {
      const error = { isAxiosError: true, code: "ERR_NETWORK" }
      if (operation === "register") mockPost.mockRejectedValueOnce(error)
      else mockDelete.mockRejectedValueOnce(error)
      mockIsAxiosError.mockImplementation((value: unknown) => value === error)
      const registered = operation === "register"
      mockGet.mockResolvedValueOnce({
        data: {
          is_registered: registered,
          participant_count: 6,
          my_qr_token: registered ? "recovered-qr" : null,
        },
      })
      const { result } = renderHook(() =>
        useEventRegistration({
          eventId,
          user: mockUser,
          initialRegistered: !registered,
          initialParticipantCount: 4,
        })
      )

      await act(async () => {
        await result.current[operation]()
      })

      expect(result.current.isLoading).toBe(false)
      expect(result.current.isRegistered).toBe(registered)
      expect(result.current.participantCount).toBe(6)
      expect(result.current.qrToken).toBe(registered ? "recovered-qr" : undefined)
    }
  )

  it("restores registration for a newly selected event cached by another mounted card", () => {
    const initialProps: HookProps = { eventId: "first-event", user: mockUser }
    const selected = renderHook((props: HookProps) => useEventRegistration(props), { initialProps })
    const otherCard = renderHook(() =>
      useEventRegistration({ eventId: "cached-event", user: mockUser, initialRegistered: true })
    )
    expect(otherCard.result.current.isRegistered).toBe(true)
    expect(localStorage.getItem("event:reg:cached-event:123")).toBe("1")

    selected.rerender({ eventId: "cached-event", user: mockUser })

    expect(selected.result.current.isRegistered).toBe(true)
    expect(localStorage.getItem("event:reg:cached-event:123")).toBe("1")
    expect(localStorage.getItem("event:reg:first-event:123")).toBeNull()
  })

  it("does not persist a user registration entry while the authenticated user is absent", () => {
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: null,
        initialRegistered: true,
        initialQrToken: "anonymous-qr",
      })
    )

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.qrToken).toBe("anonymous-qr")
    expect(localStorage.length).toBe(1)
    expect(localStorage.key(0)).toBe(`event:qr:${eventId}:anon`)
    expect(localStorage.getItem(`event:qr:${eventId}:anon`)).toBe("anonymous-qr")
  })

  it("clears the previous QR when another card cancels and refreshed props confirm it", async () => {
    const initialProps: HookProps = {
      eventId,
      user: mockUser,
      initialRegistered: true,
      initialParticipantCount: 8,
      initialQrToken: "original-qr",
    }
    const visibleCard = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })
    const otherCard = renderHook(() => useEventRegistration(initialProps))
    mockDelete.mockResolvedValueOnce({ data: null })

    await act(async () => {
      await otherCard.result.current.unregister()
    })
    expect(otherCard.result.current.isRegistered).toBe(false)
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect(visibleCard.result.current.qrToken).toBe("original-qr")

    visibleCard.rerender({
      ...initialProps,
      initialRegistered: false,
      initialParticipantCount: 7,
      initialQrToken: undefined,
    })

    expect(visibleCard.result.current.isRegistered).toBe(false)
    expect(visibleCard.result.current.participantCount).toBe(7)
    expect(visibleCard.result.current.qrToken).toBeUndefined()
  })

  it("removes a QR cached by another card when reconciliation still reports unregistered", async () => {
    const visibleCard = renderHook(() => useEventRegistration({ eventId, user: mockUser }))
    const otherCard = renderHook(() => useEventRegistration({ eventId, user: mockUser }))
    mockPost.mockResolvedValueOnce({ data: { qr_token: "other-card-qr" } })
    await act(async () => {
      await otherCard.result.current.register()
    })
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("other-card-qr")
    expect(visibleCard.result.current.isRegistered).toBe(false)
    mockGet.mockResolvedValueOnce({
      data: { is_registered: false, participant_count: 0, my_qr_token: null },
    })

    await act(async () => {
      expect(await visibleCard.result.current.sync()).toBe("unregistered")
    })

    expect(visibleCard.result.current.isRegistered).toBe(false)
    expect(visibleCard.result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
  })

  it("clears QR state when concurrent reconciliations finish registered then unregistered", async () => {
    const registeredResponse = deferred<{
      data: { is_registered: boolean; participant_count: number; my_qr_token: string | null }
    }>()
    const cancelledResponse = deferred<{
      data: { is_registered: boolean; participant_count: number; my_qr_token: string | null }
    }>()
    mockGet
      .mockReturnValueOnce(registeredResponse.promise)
      .mockReturnValueOnce(cancelledResponse.promise)
    const { result } = renderHook(() => useEventRegistration({ eventId, user: mockUser }))
    const firstSync = result.current.sync()
    const secondSync = result.current.sync()

    await act(async () => {
      registeredResponse.resolve({
        data: { is_registered: true, participant_count: 1, my_qr_token: "transient-qr" },
      })
      cancelledResponse.resolve({
        data: { is_registered: false, participant_count: 0, my_qr_token: null },
      })
      expect(await Promise.all([firstSync, secondSync])).toEqual(["registered", "unregistered"])
    })

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.participantCount).toBe(0)
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
  })

  it.each(["register", "unregister"] as const)(
    "uses a fallback notification for an Axios %s rejection with a JSON null body",
    async (operation) => {
      const { AxiosError, AxiosHeaders, isAxiosError } =
        await vi.importActual<typeof import("axios")>("axios")
      const config = { headers: new AxiosHeaders() }
      const error = new AxiosError(
        "Request failed with status code 403",
        "ERR_BAD_REQUEST",
        config,
        undefined,
        {
          config,
          status: 403,
          statusText: "Forbidden",
          headers: new AxiosHeaders({ "content-type": "application/json" }),
          data: null,
        }
      )
      mockIsAxiosError.mockImplementation(isAxiosError)
      if (operation === "register") mockPost.mockRejectedValueOnce(error)
      else mockDelete.mockRejectedValueOnce(error)
      const onNotify = vi.fn()
      const registered = operation === "unregister"
      const { result } = renderHook(() =>
        useEventRegistration({ eventId, user: mockUser, initialRegistered: registered, onNotify })
      )

      await act(async () => {
        await result.current[operation]()
      })

      expect(result.current.isRegistered).toBe(registered)
      expect(result.current.isLoading).toBe(false)
      expect(onNotify).toHaveBeenCalledExactlyOnceWith(`events:card.messages.${operation}Failure`)
      expect(mockGet).not.toHaveBeenCalled()
    }
  )

  it("restores both registration and its persisted QR after remount", () => {
    const previous = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialQrToken: "persisted-qr",
      })
    )
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("persisted-qr")
    previous.unmount()

    const reopened = renderHook(() => useEventRegistration({ eventId, user: mockUser }))

    expect(reopened.result.current.isRegistered).toBe(true)
    expect(reopened.result.current.qrToken).toBe("persisted-qr")
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("persisted-qr")
  })

  it("persists cancellation after registration was restored from cache", async () => {
    const previous = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialQrToken: "persisted-qr",
      })
    )
    previous.unmount()
    const reopened = renderHook(() => useEventRegistration({ eventId, user: mockUser }))
    mockDelete.mockResolvedValueOnce({ data: null })

    await act(async () => {
      await reopened.result.current.unregister()
    })

    expect(reopened.result.current.isRegistered).toBe(false)
    expect(reopened.result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
  })

  it.each([false, true])(
    "persists authoritative registered=%s reconciliation when another card changed the cache",
    async (registered) => {
      const options: HookProps = { eventId, user: mockUser, initialRegistered: registered }
      const visible = renderHook(() => useEventRegistration(options))
      const other = renderHook(() => useEventRegistration(options))
      if (registered) mockDelete.mockResolvedValueOnce({ data: null })
      else mockPost.mockResolvedValueOnce({ data: { qr_token: "other-qr" } })
      await act(async () => {
        if (registered) await other.result.current.unregister()
        else await other.result.current.register()
      })
      mockGet.mockResolvedValueOnce({
        data: {
          is_registered: registered,
          participant_count: registered ? 1 : 0,
          my_qr_token: registered ? "authoritative-qr" : null,
        },
      })

      await act(async () => {
        expect(await visible.result.current.sync()).toBe(registered ? "registered" : "unregistered")
      })

      expect(visible.result.current.isRegistered).toBe(registered)
      expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe(registered ? "1" : null)
      const reopened = renderHook(() => useEventRegistration({ eventId, user: mockUser }))
      expect(reopened.result.current.isRegistered).toBe(registered)
      expect(reopened.result.current.qrToken).toBe(registered ? "authoritative-qr" : undefined)
    }
  )

  it("limits pending cache restoration to its event and user scope", () => {
    const saved = renderHook(() =>
      useEventRegistration({
        eventId: "saved-event",
        user: mockUser,
        initialRegistered: true,
        initialQrToken: "saved-qr",
      })
    )
    saved.unmount()
    const anonymous = renderHook(() =>
      useEventRegistration({
        eventId: "anonymous-event",
        user: null,
        initialRegistered: true,
        initialQrToken: "old-anonymous-qr",
      })
    )
    anonymous.unmount()

    const { result } = renderHook(function useChangingRegistrationScope() {
      const [scope, setScope] = useState<HookProps>({ eventId: "saved-event", user: mockUser })
      const registration = useEventRegistration(scope)
      useEffect(() => {
        setScope({ eventId: "anonymous-event", user: null })
      }, [])
      return registration
    })

    expect(result.current.isRegistered).toBe(false)
    expect(result.current.qrToken).toBeUndefined()
    expect(result.current.isLoading).toBe(false)
    expect(localStorage.getItem("event:qr:anonymous-event:anon")).toBeNull()
    expect(localStorage.getItem("event:reg:saved-event:123")).toBe("1")
    expect(localStorage.getItem("event:qr:saved-event:123")).toBe("saved-qr")
  })

  it.each([false, true])(
    "accepts refreshed unregistered props after mounting with registered=%s",
    (initialRegistered) => {
      const initialProps: HookProps = {
        eventId,
        user: mockUser,
        initialRegistered,
        initialParticipantCount: initialRegistered ? 9 : 8,
        initialQrToken: initialRegistered ? "registered-qr" : undefined,
      }
      const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
        initialProps,
      })
      if (!initialRegistered) {
        rerender({
          ...initialProps,
          initialRegistered: true,
          initialParticipantCount: 9,
          initialQrToken: "registered-qr",
        })
      }
      expect(result.current.isRegistered).toBe(true)
      expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")

      rerender({
        ...initialProps,
        initialRegistered: false,
        initialParticipantCount: 8,
        initialQrToken: undefined,
      })

      expect(result.current.isRegistered).toBe(false)
      expect(result.current.participantCount).toBe(8)
      expect(result.current.qrToken).toBeUndefined()
      expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBeNull()
      expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBeNull()
    }
  )

  it("updates a rotated QR token from props while registration stays true", () => {
    const initialProps: HookProps = {
      eventId,
      user: mockUser,
      initialRegistered: true,
      initialQrToken: "previous-qr",
    }
    const { result, rerender } = renderHook((props: HookProps) => useEventRegistration(props), {
      initialProps,
    })

    rerender({ ...initialProps, initialQrToken: "rotated-qr" })

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.qrToken).toBe("rotated-qr")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("rotated-qr")
  })

  it("keeps the initially captured registration action valid while its scope is unchanged", async () => {
    mockPost.mockResolvedValueOnce({ data: { qr_token: "captured-action-qr" } })
    const { result } = renderHook(function useInitialRegistrationAction() {
      const registration = useEventRegistration({
        eventId,
        user: mockUser,
        initialParticipantCount: 4,
      })
      const initialRegister = useRef(registration.register)
      const registerInitialScope = useCallback(() => initialRegister.current(), [])
      return { registration, registerInitialScope }
    })

    await act(async () => {
      await result.current.registerInitialScope()
    })

    expect(mockPost).toHaveBeenCalledExactlyOnceWith("/events/attendance", { event_id: eventId })
    expect(result.current.registration.isRegistered).toBe(true)
    expect(result.current.registration.participantCount).toBe(5)
    expect(result.current.registration.qrToken).toBe("captured-action-qr")
    expect(result.current.registration.isLoading).toBe(false)
    expect(localStorage.getItem(`event:reg:${eventId}:123`)).toBe("1")
  })
})
