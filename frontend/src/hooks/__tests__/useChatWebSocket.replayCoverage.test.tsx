import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
  logError: vi.fn(),
  parseWsMessage: vi.fn(),
  dbLoad: vi.fn(),
}))

class ScriptedWebSocket {
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static instances: ScriptedWebSocket[] = []

  readyState = ScriptedWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(readonly url: string) {
    ScriptedWebSocket.instances.push(this)
  }

  send = vi.fn((payload: string) => {
    const frame = JSON.parse(payload) as { type?: unknown; nonce?: unknown }
    if (frame.type === "heartbeat_ping" && typeof frame.nonce === "string") {
      const pong = { type: "heartbeat_pong", nonce: frame.nonce }
      mocks.parseWsMessage.mockReturnValueOnce(pong)
      this.onmessage?.({ data: JSON.stringify(pong) } as MessageEvent)
    }
  })

  close = vi.fn((code = 1000, reason?: string) => {
    this.readyState = ScriptedWebSocket.CLOSED
    this.onclose?.({ code, reason } as CloseEvent)
  })

  receive(frame: unknown) {
    mocks.parseWsMessage.mockReturnValueOnce(frame)
    this.onmessage?.({ data: "frame" } as MessageEvent)
  }
}

vi.mock("@/api/client", () => ({ default: { post: mocks.apiPost } }))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))
vi.mock("@/api/schemas/wsMessage", () => ({ parseWsMessage: mocks.parseWsMessage }))
vi.mock("@/db/lazy", () => ({ getDatabaseLazily: mocks.dbLoad }))

import { useChatWebSocket, WebSocketProvider } from "../useChatWebSocket"

const ROOM = "replay-room-edge"
const TICKET = { data: { ticket: "ticket-1", expires_in: 15 } }

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

async function connected() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
  const hook = renderHook(() => useChatWebSocket({ enabled: true, currentUserId: "user-a" }), {
    wrapper,
  })
  await flush()
  const socket = ScriptedWebSocket.instances.at(-1)!
  act(() => socket.onopen?.())
  return { ...hook, queryClient, invalidateQueries, socket }
}

function markRefreshRequired(socket: ScriptedWebSocket) {
  act(() =>
    socket.receive({
      type: "replay_checkpoint",
      chat_id: ROOM,
      refresh_required: true,
    })
  )
}

beforeEach(() => {
  vi.useFakeTimers({ now: Date.UTC(2026, 7, 25, 12) })
  vi.clearAllMocks()
  window.sessionStorage.clear()
  ScriptedWebSocket.instances = []
  vi.stubGlobal("WebSocket", ScriptedWebSocket)
  mocks.apiPost.mockReset().mockResolvedValue(TICKET)
  mocks.parseWsMessage.mockReset().mockReturnValue(null)
  mocks.dbLoad.mockReset().mockResolvedValue({ messages: { upsert: vi.fn() } })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true })
})

describe("replay REST recovery timer edges", () => {
  it("does not recreate a cooldown timer when an in-flight refresh settles after unmount", async () => {
    const session = await connected()
    let finishRefresh!: () => void
    session.invalidateQueries.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finishRefresh = resolve
        })
    )

    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    session.unmount()
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout")
    await act(async () => {
      finishRefresh()
    })

    expect(timeoutSpy.mock.calls.filter(([, delay]) => delay === 60_000)).toEqual([])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)
  })

  it("releases an idle room recovery entry at the cooldown boundary", async () => {
    const session = await connected()
    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(4)
    session.unmount()
  })

  it("defers a queued refresh again when the system clock moves behind its deadline", async () => {
    const session = await connected()
    const startedAt = Date.now()
    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    markRefreshRequired(session.socket)
    vi.setSystemTime(startedAt - 90_000)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(90_000)
    })
    expect(session.invalidateQueries).toHaveBeenCalledTimes(4)
    session.unmount()
  })

  it("swallows a transient invalidation rejection and allows a later recovery", async () => {
    const session = await connected()
    session.invalidateQueries.mockImplementationOnce(() => Promise.reject(new Error("offline")))

    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(4)
    session.unmount()
  })

  it("does not refetch from a stale recovery timer after unmount", async () => {
    const session = await connected()
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout")

    markRefreshRequired(session.socket)
    await flush()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(2)

    // A second marker leaves pending work behind the cooldown timer. Unmount
    // marks that cache stale without refetching and disposes the timer/map.
    markRefreshRequired(session.socket)
    const cooldownTimer = timeoutSpy.mock.calls.find(([, delay]) => delay === 60_000)?.[0]
    expect(typeof cooldownTimer).toBe("function")

    session.unmount()
    expect(session.invalidateQueries).toHaveBeenCalledTimes(4)
    expect(
      session.invalidateQueries.mock.calls
        .slice(2)
        .map(([filters]) => (filters as { refetchType?: string }).refetchType)
    ).toEqual(["none", "none"])

    // Model a timeout callback already queued when cleanup cancels its timer.
    if (typeof cooldownTimer === "function") act(() => cooldownTimer())
    expect(session.invalidateQueries).toHaveBeenCalledTimes(4)
  })
})
