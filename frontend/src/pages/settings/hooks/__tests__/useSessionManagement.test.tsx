import { rotateBrowserSession } from "@/stores/sessionEpoch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AxiosError } from "axios"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ActiveSession } from "@/types/Session"
import { useSessionManagement } from "../useSessionManagement"

const mocks = vi.hoisted(() => ({
  user: { id: "user-1" },
  logout: vi.fn(async () => undefined),
  fetchSessions: vi.fn(async () => [] as ActiveSession[]),
  deleteSession: vi.fn(),
  postRevokeAll: vi.fn(),
  updateSessionInCache: vi.fn(),
  invalidateSessions: vi.fn(async (): Promise<void> => undefined),
  t: vi.fn((key: string, options?: { count?: number }) =>
    options?.count === undefined ? key : `${key}:${options.count}`
  ),
  formatDate: vi.fn((value: string) => `formatted:${value}`),
  toDate: vi.fn((value: string) => new Date(value)),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, logout: mocks.logout }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

vi.mock("@/api/client", () => ({
  default: {
    delete: mocks.deleteSession,
    post: mocks.postRevokeAll,
  },
}))

vi.mock("@/api/hooks/sessions", () => ({
  sessionsQueryOptions: (userId: string) => ({
    queryKey: ["auth", "sessions", userId],
    queryFn: mocks.fetchSessions,
    retry: false,
  }),
  updateSessionInCache: mocks.updateSessionInCache,
  invalidateSessions: mocks.invalidateSessions,
}))

vi.mock("@/utils/date", () => ({
  formatDate: mocks.formatDate,
  toDate: mocks.toDate,
}))

const baseSession = (overrides: Partial<ActiveSession> = {}): ActiveSession => ({
  id: "session-1",
  user_id: "user-1",
  jti: "jti-1",
  created_at: "2026-07-01T00:00:00Z",
  expires_at: "2026-08-01T00:00:00Z",
  ...overrides,
})

const renderSessionHook = (options: Partial<Parameters<typeof useSessionManagement>[0]> = {}) => {
  const setSnackbar = vi.fn()
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const hook = renderHook(
    () =>
      useSessionManagement({
        setSnackbar,
        tabActive: true,
        ...options,
      }),
    { wrapper }
  )
  return { ...hook, setSnackbar, queryClient }
}

beforeEach(() => {
  rotateBrowserSession()
  vi.clearAllMocks()
  mocks.user = { id: "user-1" }
  mocks.fetchSessions.mockResolvedValue([])
  mocks.deleteSession.mockReset()
  mocks.postRevokeAll.mockReset()
  mocks.invalidateSessions.mockResolvedValue(undefined)
  mocks.logout.mockResolvedValue(undefined)
})

describe("useSessionManagement — query and sorting", () => {
  it("gates the sessions query when the security tab is inactive", async () => {
    const { result } = renderSessionHook({ tabActive: false })

    await act(async () => {
      await Promise.resolve()
    })
    expect(mocks.fetchSessions).not.toHaveBeenCalled()
    expect(result.current.sessions).toEqual([])
  })

  it("sorts current first, active next, and revoked sessions last by recency", async () => {
    const current = baseSession({ id: "current", is_current: true, last_seen_at: null })
    const active = baseSession({ id: "active", last_seen_at: "2026-07-03T00:00:00Z" })
    const revoked = baseSession({
      id: "revoked",
      revoked_at: "2026-07-04T00:00:00Z",
      last_seen_at: "2026-07-04T00:00:00Z",
    })
    const older = baseSession({ id: "older", created_at: "invalid-date", last_seen_at: null })
    mocks.fetchSessions.mockResolvedValue([revoked, older, active, current])
    const { result } = renderSessionHook()

    await waitFor(() => expect(result.current.sessions).toHaveLength(4))
    expect(result.current.sortedSessions.map((session) => session.id)).toEqual([
      "current",
      "active",
      "older",
      "revoked",
    ])
  })

  it("handles a session with no timestamps and a non-array response", async () => {
    const untimed = baseSession({ id: "untimed", created_at: null, last_seen_at: null } as never)
    mocks.fetchSessions.mockResolvedValueOnce([untimed, baseSession({ id: "timed" })])
    const { result } = renderSessionHook()

    await waitFor(() => expect(result.current.sessions).toHaveLength(2))
    expect(result.current.sortedSessions.map((session) => session.id)).toEqual(["timed", "untimed"])

    mocks.fetchSessions.mockResolvedValueOnce({ items: [] } as never)
    const rerendered = renderSessionHook()
    await waitFor(() => expect(rerendered.result.current.sessions).toEqual([]))
  })

  it("uses the me query key and safe formatting fallback when the user is absent", () => {
    mocks.user = null as never
    mocks.formatDate.mockReturnValueOnce("")
    const { result } = renderSessionHook({ tabActive: true })

    expect(result.current.sessions).toEqual([])
    expect(result.current.formatSessionTimestamp("2026-07-30T00:00:00Z")).toBe(
      "settings:sessions.lastSeen.never"
    )
    expect(mocks.fetchSessions).not.toHaveBeenCalled()
  })

  it("exposes query error state when the sessions request fails", async () => {
    const error = new Error("sessions offline")
    mocks.fetchSessions.mockRejectedValue(error)
    const { result } = renderSessionHook()

    await waitFor(() => expect(result.current.sessionsIsError).toBe(true))
    expect(result.current.sessionsError).toBe(error)
    expect(result.current.sessions).toEqual([])
  })
})

describe("useSessionManagement — single-session revoke", () => {
  it("updates cache and invalidates after revoking a non-current session", async () => {
    const revoked = baseSession({ revoked_at: "2026-07-30T00:00:00Z" })
    mocks.deleteSession.mockResolvedValue({ data: revoked })
    const { result, setSnackbar } = renderSessionHook()

    await act(async () => {
      await result.current.handleRevokeSession("session-1")
    })

    expect(mocks.deleteSession).toHaveBeenCalledWith("/auth/sessions/session-1")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:sessions.snackbar.revoked",
      severity: "success",
    })
    expect(mocks.updateSessionInCache).toHaveBeenCalled()
    expect(mocks.invalidateSessions).toHaveBeenCalledWith(expect.anything(), "user-1")
    expect(mocks.logout).not.toHaveBeenCalled()
  })

  it("logs out when revoking the current session", async () => {
    mocks.deleteSession.mockResolvedValue({ data: baseSession({ is_current: true }) })
    const { result } = renderSessionHook()

    await act(async () => {
      await result.current.handleRevokeSession("current")
    })

    expect(mocks.logout).toHaveBeenCalledOnce()
  })

  it("opens step-up and retries a session revoke", async () => {
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    const error = new AxiosError("step-up")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.deleteSession.mockRejectedValueOnce(error).mockResolvedValueOnce({
      data: baseSession({ revoked_at: "2026-07-30T00:00:00Z" }),
    })
    const { result, setSnackbar } = renderSessionHook({ openStepUpFor })

    await act(async () => {
      await result.current.handleRevokeSession("session-1")
    })
    expect(openStepUpFor).toHaveBeenCalledOnce()
    expect(setSnackbar).not.toHaveBeenCalled()

    await act(async () => {
      await retry?.()
    })
    expect(mocks.deleteSession).toHaveBeenCalledTimes(2)
    expect(setSnackbar).toHaveBeenCalledWith(expect.objectContaining({ severity: "success" }))
  })

  it("reports Axios detail and generic revoke failures", async () => {
    const setSnackbar = vi.fn()
    const detailError = new AxiosError("denied")
    detailError.response = {
      status: 403,
      data: { detail: "Cannot revoke" },
    } as AxiosError["response"]
    mocks.deleteSession
      .mockRejectedValueOnce(detailError)
      .mockRejectedValueOnce(new Error("offline"))
    const { result } = renderSessionHook({ setSnackbar })

    await act(async () => {
      await result.current.handleRevokeSession("session-1")
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "Cannot revoke", severity: "error" })

    await act(async () => {
      await result.current.handleRevokeSession("session-1")
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "offline", severity: "error" })

    mocks.deleteSession.mockRejectedValueOnce({ reason: "unknown" })
    await act(async () => {
      await result.current.handleRevokeSession("session-1")
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:sessions.snackbar.failed",
      severity: "error",
    })
  })

  it("does not reopen step-up when a retry is explicitly marked as resumed", async () => {
    const setSnackbar = vi.fn()
    const error = new AxiosError("step-up")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.deleteSession.mockRejectedValue(error)
    const { result } = renderSessionHook({ setSnackbar })

    await act(async () => {
      await result.current.handleRevokeSession("session-1", { skipStepUp: true })
    })

    expect(setSnackbar).toHaveBeenCalledWith({ text: "step-up", severity: "error" })
  })
})

describe("useSessionManagement — revoke all and formatting", () => {
  it("revokes other sessions and reports the returned count", async () => {
    mocks.postRevokeAll.mockResolvedValue({ data: { revoked: 3 } })
    const { result, setSnackbar } = renderSessionHook()

    await act(async () => {
      await result.current.handleRevokeAllSessions()
    })

    expect(mocks.postRevokeAll).toHaveBeenCalledWith("/auth/sessions/revoke-others")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:sessions.snackbar.revokedAll:3",
      severity: "success",
    })
  })

  it("opens step-up and retries revoke-all", async () => {
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    const error = new AxiosError("step-up")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.postRevokeAll.mockRejectedValueOnce(error).mockResolvedValueOnce({ data: { revoked: 0 } })
    const { result } = renderSessionHook({ openStepUpFor })

    await act(async () => {
      await result.current.handleRevokeAllSessions()
    })
    expect(openStepUpFor).toHaveBeenCalledOnce()
    await act(async () => {
      await retry?.()
    })
    expect(mocks.postRevokeAll).toHaveBeenCalledTimes(2)
  })

  it("uses the zero count fallback and does not reopen a resumed step-up", async () => {
    const setSnackbar = vi.fn()
    const error = new AxiosError("step-up")
    error.response = { status: 428 } as AxiosError["response"]
    mocks.postRevokeAll.mockResolvedValueOnce({ data: {} }).mockRejectedValueOnce(error)
    const openStepUpFor = vi.fn()
    const { result } = renderSessionHook({ setSnackbar, openStepUpFor })

    await act(async () => {
      await result.current.handleRevokeAllSessions()
    })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:sessions.snackbar.revokedAll:0",
      severity: "success",
    })

    await act(async () => {
      await result.current.handleRevokeAllSessions({ skipStepUp: true })
    })
    expect(openStepUpFor).not.toHaveBeenCalled()
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "step-up", severity: "error" })
  })

  it("reports revoke-all failures and formats missing/invalid timestamps safely", async () => {
    const setSnackbar = vi.fn()
    mocks.postRevokeAll.mockRejectedValue(new Error("all failed"))
    const { result } = renderSessionHook({ setSnackbar })

    await act(async () => {
      await result.current.handleRevokeAllSessions()
    })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "all failed",
      severity: "error",
    })
    expect(result.current.formatSessionTimestamp(null)).toBe("settings:sessions.lastSeen.never")
    expect(result.current.formatSessionTimestamp("2026-07-30T00:00:00Z")).toContain("formatted:")
  })
})

it("does not log account B out after account A's pending revoke invalidation completes", async () => {
  let resolveInvalidation!: () => void
  const pending = new Promise<void>((resolve) => {
    resolveInvalidation = resolve
  })
  mocks.deleteSession.mockResolvedValue({ data: baseSession({ is_current: true }) })
  mocks.invalidateSessions.mockReturnValueOnce(pending)
  const { result, rerender } = renderSessionHook()
  let operation!: Promise<void>
  act(() => {
    operation = result.current.handleRevokeSession("session-1")
  })
  await waitFor(() => expect(mocks.invalidateSessions).toHaveBeenCalled())
  rotateBrowserSession()
  mocks.user = { id: "user-2" }
  rerender()
  await act(async () => {
    resolveInvalidation()
    await operation
  })
  expect(mocks.logout).not.toHaveBeenCalled()
})

it.each(["single", "all"] as const)(
  "does not dispatch %s session revocation from an obsolete tab",
  async (kind) => {
    const { result, setSnackbar } = renderSessionHook()
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "other-tab", hash: null })
    )
    await act(() =>
      kind === "single"
        ? result.current.handleRevokeSession("session-1")
        : result.current.handleRevokeAllSessions()
    )
    expect(mocks.deleteSession).not.toHaveBeenCalled()
    expect(mocks.postRevokeAll).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  }
)

it.each([
  ["single", "success"],
  ["single", "failure"],
  ["all", "success"],
  ["all", "failure"],
] as const)("ignores an obsolete %s revocation %s", async (kind, outcome) => {
  let resolve!: (value: unknown) => void
  let reject!: (reason: unknown) => void
  const pending = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  const request = kind === "single" ? mocks.deleteSession : mocks.postRevokeAll
  request.mockReturnValueOnce(pending)
  const { result, rerender, setSnackbar } = renderSessionHook()
  let operation!: Promise<void>
  act(() => {
    operation =
      kind === "single"
        ? result.current.handleRevokeSession("session-1")
        : result.current.handleRevokeAllSessions()
  })
  await waitFor(() => expect(request).toHaveBeenCalledOnce())
  rotateBrowserSession()
  mocks.user = { id: "user-2" }
  rerender()
  await act(async () => {
    if (outcome === "success")
      resolve({ data: kind === "single" ? baseSession({ is_current: true }) : { revoked: 2 } })
    else reject(new Error("Account A failed"))
    await operation
  })
  expect(mocks.updateSessionInCache).not.toHaveBeenCalled()
  expect(mocks.invalidateSessions).not.toHaveBeenCalled()
  expect(mocks.logout).not.toHaveBeenCalled()
  expect(setSnackbar).not.toHaveBeenCalled()
})

it.each(["single", "all"] as const)(
  "does not replay a %s revocation step-up for account B",
  async (kind) => {
    const request = kind === "single" ? mocks.deleteSession : mocks.postRevokeAll
    request.mockRejectedValueOnce({ isAxiosError: true, response: { status: 428 } })
    const openStepUpFor = vi.fn()
    const { result, rerender } = renderSessionHook({ openStepUpFor })
    await act(() =>
      kind === "single"
        ? result.current.handleRevokeSession("session-1")
        : result.current.handleRevokeAllSessions()
    )
    expect(openStepUpFor).toHaveBeenCalledOnce()
    rotateBrowserSession()
    mocks.user = { id: "user-2" }
    rerender()
    await act(() => openStepUpFor.mock.calls[0]![0]())
    expect(request).toHaveBeenCalledOnce()
  }
)

it("suppresses revoke-all completion after account change during invalidation", async () => {
  let resolve!: () => void
  mocks.invalidateSessions.mockReturnValueOnce(
    new Promise<void>((done) => {
      resolve = done
    })
  )
  mocks.postRevokeAll.mockResolvedValueOnce({ data: { revoked: 2 } })
  const { result, rerender, setSnackbar } = renderSessionHook()
  let operation!: Promise<void>
  act(() => {
    operation = result.current.handleRevokeAllSessions()
  })
  await waitFor(() => expect(mocks.invalidateSessions).toHaveBeenCalledOnce())
  rotateBrowserSession()
  mocks.user = { id: "user-2" }
  rerender()
  await act(async () => {
    resolve()
    await operation
  })
  expect(setSnackbar).not.toHaveBeenCalled()
})
