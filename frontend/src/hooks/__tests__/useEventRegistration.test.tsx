import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { useEventRegistration } from "../useEventRegistration"
import { http, HttpResponse } from "msw"
import { server } from "@/tests/mocks/server"

describe("useEventRegistration", () => {
  const mockUser = {
    id: 123,
    username: "testuser",
    email: "test@example.com",
    is_active: true,
    avatar_url_optimized: null,
    cover_url_optimized: null,
  } as any
  const eventId = "event-456"

  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it("initializes with provided state", () => {
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialParticipantCount: 5,
      })
    )

    expect(result.current.isRegistered).toBe(true)
    expect(result.current.participantCount).toBe(5)
  })

  it("registers for an event optimistically", async () => {
    server.use(
      http.post("*/events/attendance", () => {
        return HttpResponse.json({ qr_code: "mock-qr-token" })
      })
    )

    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
        initialParticipantCount: 10,
      })
    )

    await act(async () => {
      await result.current.register()
    })

    await waitFor(() => expect(result.current.isRegistered).toBe(true))
    expect(result.current.participantCount).toBe(11)
    expect(result.current.qrToken).toBe("mock-qr-token")
    expect(localStorage.getItem(`event:qr:${eventId}:123`)).toBe("mock-qr-token")
  })

  it("unregisters from an event optimistically", async () => {
    server.use(
      http.delete("*/events/attendance", () => {
        return new HttpResponse(null, { status: 204 })
      })
    )

    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: true,
        initialParticipantCount: 10,
      })
    )

    await act(async () => {
      await result.current.unregister()
    })

    await waitFor(() => expect(result.current.isRegistered).toBe(false))
    expect(result.current.participantCount).toBe(9)
    expect(result.current.qrToken).toBeUndefined()
  })

  it("reverts optimistic state on API failure", async () => {
    server.use(
      http.post("*/events/attendance", () => {
        return new HttpResponse(null, { status: 500 })
      })
    )

    const onNotify = vi.fn()
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
        initialParticipantCount: 10,
        onNotify,
      })
    )

    await act(async () => {
      result.current.register()
    })

    // It should briefly be true, but we want to see it go back to false
    await waitFor(() => expect(result.current.isRegistered).toBe(false), { timeout: 2000 })
    expect(result.current.participantCount).toBe(10)
    expect(onNotify).toHaveBeenCalled()
  })

  it("restores state from localStorage on mount", () => {
    localStorage.setItem(`event:reg:${eventId}:123`, "1")

    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: mockUser,
        initialRegistered: false,
      })
    )

    expect(result.current.isRegistered).toBe(true)
  })
})
