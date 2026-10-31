import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import api from "@/api/client"
import type { User } from "@/types/User"
import { useEventRegistration } from "../useEventRegistration"
import { useEventCardLogic } from "../useEventCardLogic"

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: "account-a" } }) }))
vi.mock("@/contexts/CampusTimezoneContext", () => ({ useCampusTimezone: () => "UTC" }))
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useNavigate: () => vi.fn(),
}))

const accountA = { id: "account-a" } as User
const accountB = { id: "account-b" } as User
const eventId = "event-1"
const key = (id: string) => `event:qr:${eventId}:${id}`

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe("AUD-260 My-card QR storage", () => {
  it("uses the fresh server token in memory and removes only the current user's legacy value", () => {
    localStorage.setItem(key("account-a"), "legacy-a")
    localStorage.setItem(key("account-b"), "legacy-b")
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: true,
        initialQrToken: "fresh-a",
        qrStorage: "memory",
      })
    )
    expect(result.current.qrToken).toBe("fresh-a")
    expect(localStorage.getItem(key("account-a"))).toBeNull()
    expect(localStorage.getItem(key("account-b"))).toBe("legacy-b")
  })

  it("does not recover a stale stored token when the server returns no token", () => {
    localStorage.setItem(key("account-a"), "legacy-a")
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: true,
        initialQrToken: undefined,
        qrStorage: "memory",
      })
    )
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(key("account-a"))).toBeNull()
  })

  it("replaces and then clears the in-memory token when authoritative props change", () => {
    const { result, rerender } = renderHook(
      ({ token }) =>
        useEventRegistration({
          eventId,
          user: accountA,
          initialRegistered: true,
          initialQrToken: token,
          qrStorage: "memory",
        }),
      { initialProps: { token: "first" as string | undefined } }
    )
    expect(result.current.qrToken).toBe("first")
    rerender({ token: "second" })
    expect(result.current.qrToken).toBe("second")
    rerender({ token: undefined })
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(key("account-a"))).toBeNull()
  })

  it("never carries account A's in-memory token into account B", () => {
    localStorage.setItem(key("account-b"), "legacy-b")
    const { result, rerender } = renderHook(
      ({ user, token }) =>
        useEventRegistration({
          eventId,
          user,
          initialRegistered: true,
          initialQrToken: token,
          qrStorage: "memory",
        }),
      { initialProps: { user: accountA, token: "fresh-a" as string | undefined } }
    )
    rerender({ user: accountB, token: undefined })
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(key("account-b"))).toBeNull()
  })

  it("hides a supplied My token without a user and preserves unrelated storage", () => {
    localStorage.setItem(key("anon"), "unrelated")
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: null,
        initialRegistered: true,
        initialQrToken: "old-user-value",
        qrStorage: "memory",
      })
    )
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(key("anon"))).toBe("unrelated")
  })

  it("passes the My policy through the real event-card logic", () => {
    localStorage.setItem(key("account-a"), "legacy-a")
    const { result, rerender } = renderHook(
      ({ token }) =>
        useEventCardLogic({
          id: eventId,
          is_registered: true,
          my_qr_token: token,
          qrStorage: "memory",
        }),
      { initialProps: { token: "first" as string | null } }
    )
    expect(result.current.registration.qrToken).toBe("first")
    expect(localStorage.getItem(key("account-a"))).toBeNull()
    rerender({ token: null })
    expect(result.current.registration.qrToken).toBeUndefined()
    expect(localStorage.getItem(key("account-a"))).toBeNull()
  })

  it("keeps the memory-only policy when browser storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: true,
        initialQrToken: "fresh-a",
        qrStorage: "memory",
      })
    )
    expect(result.current.qrToken).toBe("fresh-a")
  })

  it("clears the in-memory QR when fresh registration reconciliation returns no token", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: { is_registered: true, participant_count: 4, my_qr_token: null },
    })
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: true,
        initialQrToken: "old-in-memory",
        qrStorage: "memory",
      })
    )
    await act(async () => expect(await result.current.sync()).toBe("registered"))
    expect(result.current.qrToken).toBeUndefined()
    expect(localStorage.getItem(key("account-a"))).toBeNull()
  })

  it("keeps a newly reconciled QR in memory without writing it to storage", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: { is_registered: true, participant_count: 4, my_qr_token: "reconciled" },
    })
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: true,
        initialQrToken: "older",
        qrStorage: "memory",
      })
    )
    await act(async () => expect(await result.current.sync()).toBe("registered"))
    expect(result.current.qrToken).toBe("reconciled")
    expect(localStorage.getItem(key("account-a"))).toBeNull()
  })

  it("keeps an explicitly registered token in memory without writing it to My storage", async () => {
    vi.spyOn(api, "post").mockResolvedValue({ data: { qr_token: "registered" } })
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: false,
        qrStorage: "memory",
      })
    )
    await act(async () => result.current.register())
    await waitFor(() => expect(result.current.isRegistered).toBe(true))
    expect(result.current.qrToken).toBe("registered")
    expect(localStorage.getItem(key("account-a"))).toBeNull()
  })

  it("preserves the existing user-scoped storage behavior outside My", () => {
    const { result } = renderHook(() =>
      useEventRegistration({
        eventId,
        user: accountA,
        initialRegistered: true,
        initialQrToken: "legacy-mode",
      })
    )
    expect(result.current.qrToken).toBe("legacy-mode")
    expect(localStorage.getItem(key("account-a"))).toBe("legacy-mode")
  })
})
