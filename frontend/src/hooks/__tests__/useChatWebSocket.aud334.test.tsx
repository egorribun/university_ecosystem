import { act, cleanup, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
  logError: vi.fn(),
}))

vi.mock("@/api/client", () => ({ default: { post: mocks.apiPost } }))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))

import { writeReplayCheckpoint } from "../chatReplayCheckpoints"
import { useChatWebSocket, WebSocketProvider } from "../useChatWebSocket"

const ROOM = "8ef3bb0c-a893-4f74-bdb4-01544a532626"
const OTHER_ROOM = "9a8e2d87-1188-40fb-a1ef-d33f943d16f5"
const USER = "aud334-user"

class AuditSocket {
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static instances: AuditSocket[] = []

  readyState = AuditSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(_url: string) {
    AuditSocket.instances.push(this)
  }

  send = vi.fn((_frame: string) => {})

  close = vi.fn((code = 1000, reason?: string) => {
    this.readyState = AuditSocket.CLOSED
    this.onclose?.({ code, reason } as CloseEvent)
  })

  receive(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent)
  }
}

function sentJoins(socket: AuditSocket) {
  return socket.send.mock.calls
    .map(([frame]) => JSON.parse(frame) as { type: string; room?: string; resume_token?: string })
    .filter((frame) => frame.type === "join")
}

async function connect() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
  const hook = renderHook(() => useChatWebSocket({ enabled: true, currentUserId: USER }), {
    wrapper,
  })
  await act(() => vi.advanceTimersByTimeAsync(0))
  const socket = AuditSocket.instances.at(-1)!
  act(() => socket.onopen?.())
  return { ...hook, socket }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  vi.stubGlobal("WebSocket", AuditSocket)
  vi.spyOn(Math, "random").mockReturnValue(0.5)
  window.sessionStorage.clear()
  AuditSocket.instances = []
  mocks.apiPost.mockResolvedValue({ data: { ticket: "ticket", expires_in: 15 } })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("AUD-334 rejected resume recovery", () => {
  it("reconnects with the saved cursor if the same-socket replay retry is rejected", async () => {
    const { socket, result } = await connect()
    writeReplayCheckpoint(USER, ROOM, 12, "saved-cursor", ROOM)
    act(() => result.current.sendJoin(ROOM))

    act(() => socket.receive({ type: "error", room: ROOM, code: "replay_join_rate_limited" }))
    act(() => socket.receive({ type: "error", room: ROOM, code: "replay_join_rate_limited" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
    ])

    act(() => socket.receive({ type: "error", room: ROOM, code: "replay_join_rate_limited" }))
    expect(socket.close).toHaveBeenCalledOnce()
    await act(() => vi.advanceTimersByTimeAsync(500))
    expect(AuditSocket.instances).toHaveLength(2)
    const replacement = AuditSocket.instances[1]!
    act(() => replacement.onopen?.())
    expect(sentJoins(replacement)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
    ])
    act(() => {
      for (let count = 0; count < 5; count += 1) {
        socket.receive({ type: "error", room: ROOM, code: "replay_join_rate_limited" })
      }
    })
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(socket.close).toHaveBeenCalledOnce()
    expect(AuditSocket.instances).toHaveLength(2)
  })

  it("retries a recently sent resume after the generic inbound rate-limit response", async () => {
    const { socket, result } = await connect()
    writeReplayCheckpoint(USER, ROOM, 12, "saved-cursor", ROOM)
    act(() => result.current.sendJoin(ROOM))

    act(() => socket.receive({ type: "rate_limit_exceeded" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
    ])
  })

  it("retries the newly active room when it is rejected before an older room's timer fires", async () => {
    const { socket, result } = await connect()
    writeReplayCheckpoint(USER, ROOM, 12, "first-cursor", ROOM)
    writeReplayCheckpoint(USER, OTHER_ROOM, 20, "second-cursor", ROOM)
    act(() => result.current.sendJoin(ROOM))
    act(() => socket.receive({ type: "error", room: ROOM, code: "replay_join_rate_limited" }))
    act(() => result.current.sendJoin(OTHER_ROOM))
    act(() => socket.receive({ type: "error", room: OTHER_ROOM, code: "replay_join_rate_limited" }))

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "first-cursor" },
      { type: "join", room: OTHER_ROOM, resume_token: "second-cursor" },
      { type: "join", room: OTHER_ROOM, resume_token: "second-cursor" },
    ])
  })

  it("keeps the active room's retry when an unrelated room reports a rejection", async () => {
    const { socket, result } = await connect()
    writeReplayCheckpoint(USER, ROOM, 12, "saved-cursor", ROOM)
    act(() => result.current.sendJoin(ROOM))
    act(() => socket.receive({ type: "error", room: ROOM, code: "replay_join_rate_limited" }))
    act(() => socket.receive({ type: "error", room: OTHER_ROOM, code: "replay_join_rate_limited" }))

    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
      { type: "join", room: ROOM, resume_token: "saved-cursor" },
    ])
    expect(socket.close).not.toHaveBeenCalled()
  })

  it("does not react to a generic rate-limit response with no active room", async () => {
    const { socket } = await connect()

    act(() => socket.receive({ type: "rate_limit_exceeded" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))

    expect(sentJoins(socket)).toHaveLength(0)
    expect(socket.close).not.toHaveBeenCalled()
  })
})
