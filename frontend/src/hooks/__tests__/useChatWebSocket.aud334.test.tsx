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

  it.each([1_050, 1_051, 5_000])("recovers a current resume after %i ms", async (delay) => {
    const session = await connect()
    try {
      writeReplayCheckpoint(USER, ROOM, 12, "saved-cursor", ROOM)
      act(() => session.result.current.sendJoin(ROOM))
      expect(sentJoins(session.socket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
      ])
      // No room, account, transport or checkpoint change makes this request obsolete.
      await act(() => vi.advanceTimersByTimeAsync(delay))
      expect(session.socket.close).not.toHaveBeenCalled()
      act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
      await act(() => vi.advanceTimersByTimeAsync(1_050))

      expect(AuditSocket.instances.length).toBeLessThanOrEqual(2)
      const currentSocket = AuditSocket.instances.at(-1)!
      if (currentSocket !== session.socket) {
        act(() => currentSocket.onopen?.())
      }
      expect(AuditSocket.instances.flatMap(sentJoins)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
      ])
    } finally {
      session.unmount()
    }
  })

  it("bounds repeated late rejections and preserves explicit manual recovery", async () => {
    const session = await connect()
    try {
      writeReplayCheckpoint(USER, ROOM, 12, "saved-cursor", ROOM)
      act(() => session.result.current.sendJoin(ROOM))

      for (let reconnects = 0; reconnects <= 10; reconnects += 1) {
        const socket = AuditSocket.instances.at(-1)!
        expect(sentJoins(socket)).toStrictEqual([
          { type: "join", room: ROOM, resume_token: "saved-cursor" },
        ])
        await act(() => vi.advanceTimersByTimeAsync(1_051))
        act(() => {
          for (let duplicate = 0; duplicate < 3; duplicate += 1) {
            socket.receive({ type: "rate_limit_exceeded" })
          }
        })
        await act(() => vi.advanceTimersByTimeAsync(1_050))
        expect(AuditSocket.instances).toHaveLength(reconnects + 1)
        expect(sentJoins(socket)).toStrictEqual([
          { type: "join", room: ROOM, resume_token: "saved-cursor" },
          { type: "join", room: ROOM, resume_token: "saved-cursor" },
        ])

        await act(() => vi.advanceTimersByTimeAsync(1_051))
        act(() => {
          for (let duplicate = 0; duplicate < 3; duplicate += 1) {
            socket.receive({ type: "rate_limit_exceeded" })
          }
        })
        expect(socket.close).toHaveBeenCalledOnce()
        expect(socket.close).toHaveBeenCalledWith(4002, "replay_unavailable")
        expect(session.result.current.isConnected).toBe(false)
        if (reconnects < 10) {
          await act(() => vi.advanceTimersByTimeAsync(60_000))
          expect(AuditSocket.instances).toHaveLength(reconnects + 2)
          act(() => AuditSocket.instances.at(-1)!.onopen?.())
        }
      }

      await act(() => vi.advanceTimersByTimeAsync(60_000))
      expect(AuditSocket.instances).toHaveLength(11)
      expect(mocks.logError).toHaveBeenCalledWith(
        "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
        { attempts: 10, lastCode: 4002 }
      )
      expect(vi.getTimerCount()).toBe(0)

      act(() => session.result.current.reconnect())
      await act(() => vi.advanceTimersByTimeAsync(0))
      expect(AuditSocket.instances).toHaveLength(12)
      const recoveredSocket = AuditSocket.instances.at(-1)!
      act(() => recoveredSocket.onopen?.())
      expect(sentJoins(recoveredSocket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
      ])
      expect(session.result.current.isConnected).toBe(true)
      act(() =>
        recoveredSocket.receive({
          type: "replay_checkpoint",
          room: ROOM,
          seq: 13,
          resume_token: "recovered-cursor",
          replayed: true,
          payload: { type: "replay_checkpoint", chat_id: ROOM },
        })
      )
      act(() => session.result.current.sendJoin(ROOM))
      expect(sentJoins(recoveredSocket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
        { type: "join", room: ROOM, resume_token: "recovered-cursor" },
      ])
    } finally {
      session.unmount()
    }
  })
})

it("bounds replay retries despite healthy heartbeats on each transport", async () => {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
  const session = await connect()
  try {
    // Keep one mounted account, active room and unadvanced seq-12 checkpoint.
    writeReplayCheckpoint(USER, ROOM, 12, "saved-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))

    for (let reconnects = 0; reconnects <= 10; reconnects += 1) {
      const socket = AuditSocket.instances.at(-1)!
      expect(AuditSocket.instances).toHaveLength(reconnects + 1)
      expect(sentJoins(socket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
      ])
      expect(session.result.current.isConnected).toBe(true)

      await act(() => vi.advanceTimersByTimeAsync(30_000))
      const pings = socket.send.mock.calls
        .map(([frame]) => JSON.parse(frame) as { type: string; nonce?: string })
        .filter((frame) => frame.type === "heartbeat_ping")
      expect(pings).toHaveLength(1)
      expect(pings[0]!.nonce).toMatch(/^[0-9a-f]{32}$/)
      act(() => socket.receive({ type: "heartbeat_pong", nonce: pings[0]!.nonce }))

      // Passing the ACK deadline proves the real parser accepted the matching pong.
      // Transport liveness is not progress for this unchanged rejected cursor.
      await act(() => vi.advanceTimersByTimeAsync(10_001))
      expect(socket.close).not.toHaveBeenCalled()
      expect(session.result.current.isConnected).toBe(true)
      expect(sentJoins(socket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "saved-cursor" },
      ])

      act(() => socket.receive({ type: "error", room: ROOM, code: "replay_unavailable" }))
      expect(socket.close).toHaveBeenCalledOnce()
      expect(socket.close).toHaveBeenCalledWith(4002, "replay_unavailable")
      expect(session.result.current.isConnected).toBe(false)

      if (reconnects < 10) {
        await act(() => vi.advanceTimersByTimeAsync(60_000))
        expect(AuditSocket.instances).toHaveLength(reconnects + 2)
        act(() => AuditSocket.instances.at(-1)!.onopen?.())
      }
    }

    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(AuditSocket.instances).toHaveLength(11)
    expect(session.result.current.isConnected).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  } finally {
    session.unmount()
  }
})

it("restores ordinary retries in a quiet resumed room without observed rejections", async () => {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "quiet-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))

    // A quiet resume has no completion ACK or newer cursor. Twelve separated
    // healthy connections must not consume a permanent replay-failure budget.
    for (let cycle = 0; cycle < 12; cycle += 1) {
      const socket = AuditSocket.instances.at(-1)!
      expect(AuditSocket.instances).toHaveLength(cycle + 1)
      expect(sentJoins(socket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "quiet-cursor" },
      ])

      await act(() => vi.advanceTimersByTimeAsync(30_000))
      const pings = socket.send.mock.calls
        .map(([frame]) => JSON.parse(frame) as { type: string; nonce?: string })
        .filter((frame) => frame.type === "heartbeat_ping")
      expect(pings).toHaveLength(1)
      expect(pings[0]!.nonce).toMatch(/^[0-9a-f]{32}$/)
      act(() => socket.receive({ type: "heartbeat_pong", nonce: pings[0]!.nonce }))
      await act(() => vi.advanceTimersByTimeAsync(10_001))
      expect(socket.close).not.toHaveBeenCalled()
      expect(session.result.current.isConnected).toBe(true)

      act(() => socket.close(1006))
      expect(session.result.current.isConnected).toBe(false)
      await act(() => vi.advanceTimersByTimeAsync(499))
      expect(AuditSocket.instances).toHaveLength(cycle + 1)
      await act(() => vi.advanceTimersByTimeAsync(1))
      expect(AuditSocket.instances).toHaveLength(cycle + 2)
      act(() => AuditSocket.instances.at(-1)!.onopen?.())
      expect(session.result.current.isConnected).toBe(true)
    }

    expect(AuditSocket.instances).toHaveLength(13)
    expect(mocks.logError).not.toHaveBeenCalledWith(
      "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
      expect.anything()
    )
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it("restores healthy-heartbeat retry reset after accepted same-room replay progress", async () => {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "rejected-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "error", room: ROOM, code: "replay_unavailable" }))
    expect(session.socket.close).toHaveBeenCalledWith(4002, "replay_unavailable")
    expect(session.result.current.isConnected).toBe(false)

    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(AuditSocket.instances).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(AuditSocket.instances).toHaveLength(2)
    const recoveredSocket = AuditSocket.instances[1]!
    act(() => recoveredSocket.onopen?.())
    expect(sentJoins(recoveredSocket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "rejected-cursor" },
    ])

    act(() =>
      recoveredSocket.receive({
        type: "replay_checkpoint",
        room: ROOM,
        seq: 13,
        resume_token: "advanced-cursor",
        replayed: true,
        payload: { type: "replay_checkpoint", chat_id: ROOM },
      })
    )
    act(() => session.result.current.sendJoin(ROOM))
    expect(sentJoins(recoveredSocket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "rejected-cursor" },
      { type: "join", room: ROOM, resume_token: "advanced-cursor" },
    ])

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const pings = recoveredSocket.send.mock.calls
      .map(([frame]) => JSON.parse(frame) as { type: string; nonce?: string })
      .filter((frame) => frame.type === "heartbeat_ping")
    expect(pings).toHaveLength(1)
    expect(pings[0]!.nonce).toMatch(/^[0-9a-f]{32}$/)
    act(() => recoveredSocket.receive({ type: "heartbeat_pong", nonce: pings[0]!.nonce }))
    await act(() => vi.advanceTimersByTimeAsync(10_001))
    expect(recoveredSocket.close).not.toHaveBeenCalled()
    expect(session.result.current.isConnected).toBe(true)

    // One rejection already spent a retry. Successful progress plus the stable
    // matching pong must restore the observable first (500 ms) backoff.
    act(() => recoveredSocket.close(1006))
    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(AuditSocket.instances).toHaveLength(2)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(AuditSocket.instances).toHaveLength(3)
    const replacement = AuditSocket.instances[2]!
    act(() => replacement.onopen?.())
    expect(sentJoins(replacement)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "advanced-cursor" },
    ])
    expect(session.result.current.isConnected).toBe(true)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it.each([
  ["unrelated-room progress", 1_000],
  ["same-sequence token replacement", 500],
  ["matching invalidation", 500],
  ["active-room leave", 500],
  ["active-room switch", 500],
  ["unrelated-room leave", 1_000],
  ["unrelated-room invalidation", 1_000],
  ["equal-sequence wire frame", 1_000],
  ["malformed wire frame", 1_000],
  ["old-transport progress", 1_000],
  ["checkpoint removal", 500],
] as const)("scopes observed replay recovery debt across %s", async (transition, delay) => {
  const { peekReplayCheckpoint, removeReplayCheckpoint } = await import("../chatReplayCheckpoints")
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "debt-cursor", ROOM)
    writeReplayCheckpoint(USER, OTHER_ROOM, 20, "other-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "error", room: ROOM, code: "replay_unavailable" }))
    expect(session.socket.close).toHaveBeenCalledWith(4002, "replay_unavailable")
    await act(() => vi.advanceTimersByTimeAsync(500))
    expect(AuditSocket.instances).toHaveLength(2)
    const socket = AuditSocket.instances[1]!
    act(() => socket.onopen?.())
    expect(sentJoins(socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "debt-cursor" },
    ])

    switch (transition) {
      case "unrelated-room progress":
        act(() =>
          socket.receive({
            type: "replay_checkpoint",
            room: OTHER_ROOM,
            seq: 21,
            resume_token: "other-advanced",
            replayed: true,
            payload: { type: "replay_checkpoint", chat_id: OTHER_ROOM },
          })
        )
        expect(peekReplayCheckpoint(USER, OTHER_ROOM)).toStrictEqual({
          sequence: 21,
          resumeToken: "other-advanced",
        })
        break
      case "equal-sequence wire frame":
      case "malformed wire frame":
      case "old-transport progress": {
        const sender = transition === "old-transport progress" ? session.socket : socket
        const sequence = transition === "equal-sequence wire frame" ? 12 : 13
        act(() =>
          sender.receive({
            type: "replay_checkpoint",
            room: ROOM,
            seq: transition === "malformed wire frame" ? "not-a-sequence" : sequence,
            resume_token: "must-not-replace",
            replayed: true,
            payload: { type: "replay_checkpoint", chat_id: ROOM },
          })
        )
        expect(peekReplayCheckpoint(USER, ROOM)).toStrictEqual({
          sequence: 12,
          resumeToken: "debt-cursor",
        })
        if (transition === "malformed wire frame") {
          expect(mocks.logError).toHaveBeenCalledWith("[ws] Invalid frame dropped", {
            size: expect.any(Number),
          })
        }
        break
      }
      case "checkpoint removal":
        act(() => removeReplayCheckpoint(USER, ROOM))
        expect(peekReplayCheckpoint(USER, ROOM)).toBeUndefined()
        break
      case "same-sequence token replacement":
        // Another owner of the real shared store may replace an opaque token.
        // This is not an equal-sequence wire frame, which the hook discards.
        act(() => writeReplayCheckpoint(USER, ROOM, 12, "replacement-cursor", ROOM))
        expect(peekReplayCheckpoint(USER, ROOM)).toStrictEqual({
          sequence: 12,
          resumeToken: "replacement-cursor",
        })
        break
      case "matching invalidation":
        act(() => socket.receive({ type: "error", room: ROOM, code: "invalid_resume_token" }))
        expect(peekReplayCheckpoint(USER, ROOM)).toBeUndefined()
        break
      case "active-room leave":
        act(() => session.result.current.sendLeave(ROOM))
        expect(socket.send).toHaveBeenLastCalledWith(JSON.stringify({ type: "leave", room: ROOM }))
        break
      case "active-room switch":
        act(() => session.result.current.sendJoin(OTHER_ROOM))
        expect(sentJoins(socket)).toStrictEqual([
          { type: "join", room: ROOM, resume_token: "debt-cursor" },
          { type: "join", room: OTHER_ROOM, resume_token: "other-cursor" },
        ])
        break
      case "unrelated-room leave":
        act(() => session.result.current.sendLeave(OTHER_ROOM))
        expect(socket.send).toHaveBeenLastCalledWith(
          JSON.stringify({ type: "leave", room: OTHER_ROOM })
        )
        break
      case "unrelated-room invalidation":
        act(() => socket.receive({ type: "error", room: OTHER_ROOM, code: "invalid_resume_token" }))
        expect(peekReplayCheckpoint(USER, OTHER_ROOM)).toBeUndefined()
        break
    }
    if (transition.startsWith("unrelated-room")) {
      expect(peekReplayCheckpoint(USER, ROOM)).toStrictEqual({
        sequence: 12,
        resumeToken: "debt-cursor",
      })
    }

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const pings = socket.send.mock.calls
      .map(([frame]) => JSON.parse(frame) as { type: string; nonce?: string })
      .filter((frame) => frame.type === "heartbeat_ping")
    expect(pings).toHaveLength(1)
    expect(pings[0]!.nonce).toMatch(/^[0-9a-f]{32}$/)
    act(() => socket.receive({ type: "heartbeat_pong", nonce: pings[0]!.nonce }))
    await act(() => vi.advanceTimersByTimeAsync(10_001))
    expect(socket.close).not.toHaveBeenCalled()
    expect(session.result.current.isConnected).toBe(true)

    // The first failure spent one retry: unchanged debt preserves the second
    // 1000 ms backoff; an obsolete debt permits the stable pong's 500 ms reset.
    act(() => socket.close(1006))
    await act(() => vi.advanceTimersByTimeAsync(delay - 1))
    expect(AuditSocket.instances).toHaveLength(2)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(AuditSocket.instances).toHaveLength(3)
    act(() => AuditSocket.instances[2]!.onopen?.())
    expect(session.result.current.isConnected).toBe(true)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it("does not carry observed replay debt into a replacement account", async () => {
  const { peekReplayCheckpoint } = await import("../chatReplayCheckpoints")
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
  const nextUser = "aud334-replacement-user"
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
  const session = renderHook(
    ({ userId }) => useChatWebSocket({ enabled: true, currentUserId: userId }),
    { initialProps: { userId: USER }, wrapper }
  )
  try {
    await act(() => vi.advanceTimersByTimeAsync(0))
    const originalSocket = AuditSocket.instances[0]!
    act(() => originalSocket.onopen?.())
    writeReplayCheckpoint(USER, ROOM, 12, "same-looking-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => originalSocket.receive({ type: "error", room: ROOM, code: "replay_unavailable" }))
    expect(originalSocket.close).toHaveBeenCalledWith(4002, "replay_unavailable")
    await act(() => vi.advanceTimersByTimeAsync(500))
    expect(AuditSocket.instances).toHaveLength(2)
    const indebtedSocket = AuditSocket.instances[1]!
    act(() => indebtedSocket.onopen?.())

    // Match the room, sequence and opaque text deliberately: only the account
    // boundary distinguishes this new session from the old recovery identity.
    writeReplayCheckpoint(nextUser, ROOM, 12, "same-looking-cursor", ROOM)
    act(() => session.rerender({ userId: nextUser }))
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(indebtedSocket.close).toHaveBeenCalledWith(1000)
    expect(AuditSocket.instances).toHaveLength(3)
    expect(peekReplayCheckpoint(USER, ROOM)).toBeUndefined()
    expect(peekReplayCheckpoint(nextUser, ROOM)).toStrictEqual({
      sequence: 12,
      resumeToken: "same-looking-cursor",
    })
    const firstNewAccountSocket = AuditSocket.instances[2]!
    act(() => firstNewAccountSocket.onopen?.())
    act(() => session.result.current.sendJoin(ROOM))
    expect(sentJoins(firstNewAccountSocket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "same-looking-cursor" },
    ])

    // Spend a new-account retry before any healthy pong. Otherwise a zero
    // counter could hide old debt incorrectly blocking the following reset.
    act(() => firstNewAccountSocket.close(1006))
    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(AuditSocket.instances).toHaveLength(3)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(AuditSocket.instances).toHaveLength(4)
    const stableSocket = AuditSocket.instances[3]!
    act(() => stableSocket.onopen?.())
    expect(sentJoins(stableSocket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "same-looking-cursor" },
    ])

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    const pings = stableSocket.send.mock.calls
      .map(([frame]) => JSON.parse(frame) as { type: string; nonce?: string })
      .filter((frame) => frame.type === "heartbeat_ping")
    expect(pings).toHaveLength(1)
    expect(pings[0]!.nonce).toMatch(/^[0-9a-f]{32}$/)
    act(() => stableSocket.receive({ type: "heartbeat_pong", nonce: pings[0]!.nonce }))
    await act(() => vi.advanceTimersByTimeAsync(10_001))
    expect(stableSocket.close).not.toHaveBeenCalled()
    expect(session.result.current.isConnected).toBe(true)

    act(() => stableSocket.close(1006))
    await act(() => vi.advanceTimersByTimeAsync(499))
    expect(AuditSocket.instances).toHaveLength(4)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(AuditSocket.instances).toHaveLength(5)
    act(() => AuditSocket.instances[4]!.onopen?.())
    expect(session.result.current.isConnected).toBe(true)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it.each([
  { name: "sequence", sequence: 13, token: "sent-cursor" },
  { name: "token", sequence: 12, token: "replacement-cursor" },
])("binds generic retries to the current resume $name", async ({ sequence, token }) => {
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "sent-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(sentJoins(session.socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "sent-cursor" },
      { type: "join", room: ROOM, resume_token: "sent-cursor" },
    ])
    // The old allowance is spent. Only an actually sent new identity may renew it.
    // This is a public registry replacement, not acceptance of an equal-sequence wire frame.
    writeReplayCheckpoint(USER, ROOM, sequence, token, ROOM)
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(sentJoins(session.socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "sent-cursor" },
      { type: "join", room: ROOM, resume_token: "sent-cursor" },
    ])
    expect(session.socket.close).not.toHaveBeenCalled()

    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(sentJoins(session.socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "sent-cursor" },
      { type: "join", room: ROOM, resume_token: "sent-cursor" },
      { type: "join", room: ROOM, resume_token: token },
      { type: "join", room: ROOM, resume_token: token },
    ])
    expect(session.socket.close).not.toHaveBeenCalled()
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it("does not replenish the same resume retry when a caller joins the same room again", async () => {
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "same-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    await act(() => vi.advanceTimersByTimeAsync(1_050))
    expect(sentJoins(session.socket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "same-cursor" },
      { type: "join", room: ROOM, resume_token: "same-cursor" },
      { type: "join", room: ROOM, resume_token: "same-cursor" },
    ])

    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    expect(sentJoins(session.socket)).toHaveLength(4)
    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(4002, "replay_unavailable")
    expect(session.result.current.isConnected).toBe(false)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it("keeps observed rejection debt bounded across automatic online events", async () => {
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "offline-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    // Cancel the pending same-socket retry before any reconnect was charged.
    act(() => window.dispatchEvent(new Event("offline")))
    expect(session.socket.close).toHaveBeenCalledExactlyOnceWith(1000)
    expect(vi.getTimerCount()).toBe(0)

    const delays = [500, 1_000, 2_000, 4_000, 8_000, 15_000, 15_000, 15_000, 15_000, 15_000]
    for (const [attempt, delay] of delays.entries()) {
      act(() => {
        window.dispatchEvent(new Event("online"))
        window.dispatchEvent(new Event("online"))
      })
      await act(() => vi.advanceTimersByTimeAsync(delay - 1))
      expect(AuditSocket.instances).toHaveLength(attempt + 1)
      await act(() => vi.advanceTimersByTimeAsync(1))
      expect(AuditSocket.instances).toHaveLength(attempt + 2)
      const socket = AuditSocket.instances.at(-1)!
      act(() => socket.onopen?.())
      expect(sentJoins(socket)).toStrictEqual([
        { type: "join", room: ROOM, resume_token: "offline-cursor" },
      ])
      // A duplicate online event on an already-open transport spends nothing.
      act(() => window.dispatchEvent(new Event("online")))
      act(() => window.dispatchEvent(new Event("offline")))
      expect(socket.close).toHaveBeenCalledExactlyOnceWith(1000)
      expect(session.result.current.isConnected).toBe(false)
      expect(vi.getTimerCount()).toBe(0)
    }

    act(() => {
      window.dispatchEvent(new Event("online"))
      window.dispatchEvent(new Event("online"))
    })
    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(AuditSocket.instances).toHaveLength(11)
    expect(session.result.current.isConnected).toBe(false)
    expect(vi.getTimerCount()).toBe(0)

    act(() => session.result.current.reconnect())
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(AuditSocket.instances).toHaveLength(12)
    const manualSocket = AuditSocket.instances.at(-1)!
    act(() => manualSocket.onopen?.())
    expect(sentJoins(manualSocket)).toStrictEqual([
      { type: "join", room: ROOM, resume_token: "offline-cursor" },
    ])
    expect(session.result.current.isConnected).toBe(true)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it("does not charge an online recovery while its ticket request is in flight", async () => {
  const session = await connect()
  try {
    writeReplayCheckpoint(USER, ROOM, 12, "pending-ticket-cursor", ROOM)
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    act(() => window.dispatchEvent(new Event("offline")))

    let completeTicket!: (value: { data: { ticket: string; expires_in: number } }) => void
    mocks.apiPost.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          completeTicket = resolve
        })
    )
    act(() => window.dispatchEvent(new Event("online")))
    await act(() => vi.advanceTimersByTimeAsync(500))
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(AuditSocket.instances).toHaveLength(1)
    act(() => {
      window.dispatchEvent(new Event("online"))
      window.dispatchEvent(new Event("online"))
    })
    await act(async () => {
      completeTicket({ data: { ticket: "recovered-ticket", expires_in: 15 } })
    })
    expect(AuditSocket.instances).toHaveLength(2)
    act(() => AuditSocket.instances[1]!.onopen?.())
    act(() => window.dispatchEvent(new Event("offline")))
    act(() => window.dispatchEvent(new Event("online")))
    // Only one attempt was spent; duplicate events cannot advance this backoff.
    await act(() => vi.advanceTimersByTimeAsync(999))
    expect(AuditSocket.instances).toHaveLength(2)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(AuditSocket.instances).toHaveLength(3)
    act(() => AuditSocket.instances[2]!.onopen?.())
    expect(session.result.current.isConnected).toBe(true)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})

it.each(["manual", "online"])("retires old backoff on a %s restart", async (restart) => {
  const session = await connect()
  try {
    act(() => session.socket.close(1006))
    await act(() => vi.advanceTimersByTimeAsync(100))
    mocks.apiPost.mockRejectedValueOnce(new Error("temporary ticket failure"))
    act(() => {
      if (restart === "manual") session.result.current.reconnect()
      else window.dispatchEvent(new Event("online"))
    })
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(1)

    // The superseded original timer was due at t=500. It must not create a
    // transport or clear the reservation belonging to the newer ticket failure.
    await act(() => vi.advanceTimersByTimeAsync(400))
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    expect(AuditSocket.instances).toHaveLength(1)
    const replacementDelay = restart === "manual" ? 1_000 : 500
    await act(() => vi.advanceTimersByTimeAsync(replacementDelay - 401))
    expect(mocks.apiPost).toHaveBeenCalledTimes(2)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(mocks.apiPost).toHaveBeenCalledTimes(3)
    expect(AuditSocket.instances).toHaveLength(2)
    act(() => AuditSocket.instances[1]!.onopen?.())
    expect(session.result.current.isConnected).toBe(true)
  } finally {
    session.unmount()
  }
  expect(vi.getTimerCount()).toBe(0)
})
