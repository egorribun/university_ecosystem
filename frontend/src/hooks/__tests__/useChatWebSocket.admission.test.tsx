import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({ post: vi.fn(), logError: vi.fn() }))
vi.mock("@/api/client", () => ({ default: { post: mocks.post } }))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))

import {
  useChatWebSocket,
  WebSocketProvider,
  type UseChatWebSocketOptions,
} from "../useChatWebSocket"
import { clearReplayCheckpoints, writeReplayCheckpoint } from "../chatReplayCheckpoints"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"

const ROOM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const OTHER_ROOM = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
class Socket {
  static OPEN = 1
  static CLOSED = 3
  static instances: Socket[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  sent: string[] = []
  constructor(_url: string) {
    Socket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  open() {
    this.readyState = Socket.OPEN
    this.onopen?.()
  }
  receive(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent)
  }
  close(code = 1000) {
    this.readyState = Socket.CLOSED
    this.onclose?.({ code } as CloseEvent)
  }
}
type Join = {
  type: string
  room: string
  resume_token?: string
  payload?: { admission_nonce: string }
}
const joins = (socket: Socket): Join[] =>
  socket.sent.map((line) => JSON.parse(line) as Join).filter((frame) => frame.type === "join")
const ack = (join: Join) => ({
  type: "room_admitted",
  room: join.room,
  nonce: join.payload!.admission_nonce,
})
const drain = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20))
  })

beforeEach(() => {
  Socket.instances = []
  vi.stubGlobal("WebSocket", Socket)
  mocks.post.mockResolvedValue({ data: { ticket: "synthetic", expires_in: 15 } })
  clearReplayCheckpoints("user-a")
})
afterEach(() => {
  cleanup()
  clearReplayCheckpoints("user-a")
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function connect(options: UseChatWebSocketOptions = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(queryClient, "invalidateQueries")
  const cancel = vi.spyOn(queryClient, "cancelQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>{children}</WebSocketProvider>
    </QueryClientProvider>
  )
  const hook = renderHook((props: UseChatWebSocketOptions) => useChatWebSocket(props), {
    wrapper,
    initialProps: { currentUserId: "user-a", roomAdmission: true, ...options },
  })
  await waitFor(() => expect(Socket.instances).toHaveLength(1))
  const socket = Socket.instances[0]!
  act(() => socket.open())
  return { ...hook, socket, invalidate, cancel }
}

describe("room admission hook", () => {
  it("sends one join and exposes membership only after a matching ACK without a GET", async () => {
    const session = await connect()
    act(() => session.result.current.sendJoin(ROOM))
    expect(session.result.current.isConnected).toBe(true)
    expect(session.result.current.admittedRoom).toBeNull()
    expect(session.socket.sent).toHaveLength(1)
    const join = joins(session.socket)[0]!
    expect(join).toEqual({
      type: "join",
      room: ROOM,
      payload: { admission_nonce: expect.stringMatching(/^[a-f0-9]{32}$/) },
    })
    act(() => session.socket.receive(ack(join)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
    await drain()
    expect(session.invalidate).not.toHaveBeenCalled()
    expect(session.cancel).not.toHaveBeenCalled()
  })

  it("keeps opt-out and legacy server paths immediate without inferring admission", async () => {
    const legacy = await connect({ roomAdmission: false })
    act(() => legacy.result.current.sendJoin(ROOM))
    expect(joins(legacy.socket)).toEqual([{ type: "join", room: ROOM }])
    expect(legacy.result.current.isConnected).toBe(true)
    expect(legacy.result.current.admittedRoom).toBeNull()
    legacy.unmount()
    Socket.instances = []
    const oldHub = await connect()
    act(() => oldHub.result.current.sendJoin(ROOM))
    expect(joins(oldHub.socket)[0]?.payload?.admission_nonce).toMatch(/^[a-f0-9]{32}$/)
    await drain()
    expect(oldHub.result.current.isConnected).toBe(true)
    expect(oldHub.result.current.admittedRoom).toBeNull()
    expect(oldHub.invalidate).not.toHaveBeenCalled()
  })

  it("rejects wrong, wrapped, duplicate, and stale same-room attempts", async () => {
    const { result, socket, invalidate } = await connect()
    act(() => result.current.sendJoin(ROOM))
    const old = joins(socket)[0]!
    act(() => result.current.sendJoin(ROOM))
    const current = joins(socket)[1]!
    expect(current.payload?.admission_nonce).not.toBe(old.payload?.admission_nonce)
    act(() => {
      socket.receive(ack(old))
      socket.receive({ ...ack(current), room: OTHER_ROOM })
      socket.receive({ ...ack(current), nonce: "e".repeat(32) })
      socket.receive({ type: "broadcast", payload: ack(current) })
    })
    expect(result.current.admittedRoom).toBeNull()
    act(() => socket.receive(ack(current)))
    expect(result.current.admittedRoom).toBe(ROOM)
    act(() => socket.receive(ack(current)))
    expect(result.current.admittedRoom).toBe(ROOM)
    await drain()
    expect(invalidate).not.toHaveBeenCalled()
  })

  it("rejects queued ACKs after leave or socket replacement", async () => {
    const session = await connect()
    act(() => session.result.current.sendJoin(ROOM))
    const first = joins(session.socket)[0]!
    const staleMessage = session.socket.onmessage!
    act(() => {
      session.result.current.sendLeave(ROOM)
      session.socket.receive(ack(first))
    })
    expect(session.result.current.admittedRoom).toBeNull()
    act(() => {
      session.socket.close()
      session.result.current.sendJoin(ROOM)
      session.result.current.reconnect()
    })
    await waitFor(() => expect(Socket.instances).toHaveLength(2))
    const replacement = Socket.instances[1]!
    act(() => replacement.open())
    const next = joins(replacement)[0]!
    act(() => staleMessage({ data: JSON.stringify(ack(first)) } as MessageEvent))
    expect(session.result.current.admittedRoom).toBeNull()
    act(() => replacement.receive(ack(next)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
  })

  it("retires admitted state on same-user rotation and does not claim the new session on its old socket", async () => {
    const session = await connect()
    act(() => session.result.current.sendJoin(ROOM))
    const old = joins(session.socket)[0]!
    act(() => session.socket.receive(ack(old)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
    act(() => invalidateSessionEpoch())
    await waitFor(() => expect(session.result.current.admittedRoom).toBeNull())
    act(() => {
      session.socket.receive(ack(old))
      session.result.current.sendJoin(ROOM)
    })
    expect(joins(session.socket)[1]).toEqual({ type: "join", room: ROOM })
    expect(session.result.current.admittedRoom).toBeNull()
    act(() => {
      session.socket.close()
      session.result.current.reconnect()
    })
    await waitFor(() => expect(Socket.instances).toHaveLength(2))
    const replacement = Socket.instances[1]!
    act(() => replacement.open())
    const current = joins(replacement)[0]!
    act(() => replacement.receive(ack(current)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
  })

  it("binds room comparison byte-for-byte and rejects a different cross-tab generation", async () => {
    const session = await connect()
    const upper = ROOM.toUpperCase()
    act(() => session.result.current.sendJoin(upper))
    const join = joins(session.socket)[0]!
    act(() => session.socket.receive({ ...ack(join), room: ROOM }))
    expect(session.result.current.admittedRoom).toBeNull()
    const key = "ecosystem.session.generation.v1"
    const old = localStorage.getItem(key)
    try {
      localStorage.setItem(key, JSON.stringify({ nonce: "synthetic-new-generation", hash: null }))
      act(() => session.socket.receive(ack(join)))
      expect(session.result.current.admittedRoom).toBeNull()
    } finally {
      if (old === null) localStorage.removeItem(key)
      else localStorage.setItem(key, old)
    }
    act(() => session.socket.receive(ack(join)))
    expect(session.result.current.admittedRoom).toBe(upper)
  })

  it("keeps a resume token top-level and does not equate membership with replay completion", async () => {
    writeReplayCheckpoint("user-a", ROOM, 9, "cursor", ROOM)
    const session = await connect()
    act(() => session.result.current.sendJoin(ROOM))
    const join = joins(session.socket)[0]!
    expect(join).toEqual({
      type: "join",
      room: ROOM,
      resume_token: "cursor",
      payload: { admission_nonce: expect.stringMatching(/^[a-f0-9]{32}$/) },
    })
    act(() => session.socket.receive(ack(join)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
    await drain()
    expect(session.invalidate).not.toHaveBeenCalled()
  })

  it("retires admitted state on leave and a generic server denial", async () => {
    const session = await connect()
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive(ack(joins(session.socket)[0]!)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
    act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
    expect(session.result.current.admittedRoom).toBeNull()
    act(() => session.result.current.sendJoin(ROOM))
    act(() => session.socket.receive(ack(joins(session.socket)[1]!)))
    expect(session.result.current.admittedRoom).toBe(ROOM)
    act(() => session.result.current.sendLeave(ROOM))
    expect(session.result.current.admittedRoom).toBeNull()
  })

  it("degrades a repeated nonce or invalid legacy room to the original join", async () => {
    vi.spyOn(globalThis.crypto, "getRandomValues").mockImplementation((array) => {
      if (!(array instanceof Uint8Array)) throw new Error("unexpected array")
      array.fill(0)
      return array
    })
    const session = await connect()
    act(() => {
      session.result.current.sendJoin(ROOM)
      session.result.current.sendJoin(ROOM)
      session.result.current.sendJoin("legacy-room")
    })
    expect(joins(session.socket)).toEqual([
      { type: "join", room: ROOM, payload: { admission_nonce: "0".repeat(32) } },
      { type: "join", room: ROOM },
      { type: "join", room: "legacy-room" },
    ])
    act(() => session.socket.receive({ type: "room_admitted", room: ROOM, nonce: "0".repeat(32) }))
    expect(session.result.current.admittedRoom).toBeNull()
  })

  it("degrades safely when randomness fails or the socket nonce budget is exhausted", async () => {
    const session = await connect()
    const random = vi.spyOn(globalThis.crypto, "getRandomValues")
    random.mockImplementationOnce(() => {
      throw new Error("unavailable")
    })
    act(() => session.result.current.sendJoin(ROOM))
    expect(joins(session.socket)[0]).toEqual({ type: "join", room: ROOM })
    for (let index = 0; index < 65; index += 1) act(() => session.result.current.sendJoin(ROOM))
    expect(
      joins(session.socket)
        .slice(1, 65)
        .every((join) => join.payload !== undefined)
    ).toBe(true)
    expect(joins(session.socket)[65]).toEqual({ type: "join", room: ROOM })
  })
})

it("retires admission as soon as the caller disables admission or changes account", async () => {
  const session = await connect()
  act(() => session.result.current.sendJoin(ROOM))
  act(() => session.socket.receive(ack(joins(session.socket)[0]!)))
  expect(session.result.current.admittedRoom).toBe(ROOM)
  session.rerender({ currentUserId: "user-a", roomAdmission: false })
  expect(session.result.current.admittedRoom).toBeNull()
  session.rerender({ currentUserId: "user-a", roomAdmission: true })
  expect(session.result.current.admittedRoom).toBeNull()
  session.rerender({ currentUserId: "user-b", roomAdmission: true })
  expect(session.result.current.admittedRoom).toBeNull()
})

it("clears matching and unscoped server errors while preserving unrelated admission", async () => {
  const session = await connect()
  act(() => session.result.current.sendJoin(ROOM))
  act(() => session.socket.receive(ack(joins(session.socket)[0]!)))
  expect(session.result.current.admittedRoom).toBe(ROOM)
  act(() => session.socket.receive({ type: "error", room: OTHER_ROOM, code: "unrelated" }))
  expect(session.result.current.admittedRoom).toBe(ROOM)
  act(() => session.socket.receive({ type: "error", room: ROOM, code: "denied" }))
  expect(session.result.current.admittedRoom).toBeNull()
  act(() => session.result.current.sendJoin(ROOM))
  act(() => session.socket.receive(ack(joins(session.socket)[1]!)))
  act(() => session.socket.receive({ type: "error", code: "unscoped" }))
  expect(session.result.current.admittedRoom).toBeNull()
})

it("does not accept an acknowledgement after WebSocket.send throws", async () => {
  const session = await connect()
  act(() => session.result.current.sendJoin(ROOM))
  act(() => session.socket.receive(ack(joins(session.socket)[0]!)))
  expect(session.result.current.admittedRoom).toBe(ROOM)
  let failed: Join | undefined
  vi.spyOn(session.socket, "send").mockImplementationOnce((payload) => {
    failed = JSON.parse(payload) as Join
    throw new Error("socket closed during send")
  })
  act(() => session.result.current.sendJoin(ROOM))
  expect(session.result.current.admittedRoom).toBeNull()
  expect(failed?.payload?.admission_nonce).toMatch(/^[0-9a-f]{32}$/)
  act(() => session.socket.receive(ack(failed!)))
  expect(session.result.current.admittedRoom).toBeNull()
  expect(session.result.current.isConnected).toBe(true)
})

it("drops confirmed admission on a cross-tab storage generation event", async () => {
  const session = await connect()
  act(() => session.result.current.sendJoin(ROOM))
  act(() => session.socket.receive(ack(joins(session.socket)[0]!)))
  expect(session.result.current.admittedRoom).toBe(ROOM)
  const key = "ecosystem.session.generation.v1"
  const previous = localStorage.getItem(key)
  const next = JSON.stringify({ nonce: "synthetic-new-generation", hash: null })
  try {
    localStorage.setItem(key, next)
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key, oldValue: previous, newValue: next }))
    })
    await waitFor(() => expect(session.result.current.admittedRoom).toBeNull())
  } finally {
    session.unmount()
    if (previous === null) localStorage.removeItem(key)
    else localStorage.setItem(key, previous)
  }
})

it("keeps a plain join when the session rotates while its nonce is generated", async () => {
  const session = await connect()
  vi.spyOn(globalThis.crypto, "getRandomValues").mockImplementationOnce((array) => {
    if (!(array instanceof Uint8Array)) throw new Error("unexpected array")
    invalidateSessionEpoch()
    return array
  })
  act(() => session.result.current.sendJoin(ROOM))
  expect(joins(session.socket)).toEqual([{ type: "join", room: ROOM }])
  expect(session.result.current.admittedRoom).toBeNull()
})

it("does not send a join if the owned socket closes during nonce generation", async () => {
  const session = await connect()
  vi.spyOn(globalThis.crypto, "getRandomValues").mockImplementationOnce((array) => {
    session.result.current.disconnect()
    return array
  })
  act(() => session.result.current.sendJoin(ROOM))
  expect(session.socket.sent).toEqual([])
  expect(session.result.current.admittedRoom).toBeNull()
  expect(session.result.current.isConnected).toBe(false)
})

it("rejects a stale ACK from another socket even when that socket reused the nonce", async () => {
  vi.spyOn(globalThis.crypto, "getRandomValues").mockImplementation((array) => {
    if (!(array instanceof Uint8Array)) throw new Error("unexpected array")
    array.fill(7)
    return array
  })
  const session = await connect()
  act(() => session.result.current.sendJoin(ROOM))
  const first = joins(session.socket)[0]!
  const staleMessage = session.socket.onmessage!
  act(() => {
    session.socket.close()
    session.result.current.reconnect()
  })
  await waitFor(() => expect(Socket.instances).toHaveLength(2))
  const replacement = Socket.instances[1]!
  act(() => replacement.open())
  const second = joins(replacement)[0]!
  expect(second.payload?.admission_nonce).toBe(first.payload?.admission_nonce)
  act(() => staleMessage({ data: JSON.stringify(ack(first)) } as MessageEvent))
  expect(session.result.current.admittedRoom).toBeNull()
  act(() => replacement.receive(ack(second)))
  expect(session.result.current.admittedRoom).toBe(ROOM)
})

it("preserves a plain join if the authenticated user is unavailable", async () => {
  const session = await connect({ currentUserId: undefined })
  act(() => session.result.current.sendJoin(ROOM))
  expect(joins(session.socket)).toEqual([{ type: "join", room: ROOM }])
  expect(session.result.current.admittedRoom).toBeNull()
})

it("keeps replay retry correlation on a fresh nonce and never claims replay completion", async () => {
  writeReplayCheckpoint("user-a", ROOM, 9, "cursor", ROOM)
  const session = await connect()
  act(() => session.result.current.sendJoin(ROOM))
  const first = joins(session.socket)[0]!
  act(() => session.socket.receive({ type: "rate_limit_exceeded" }))
  await waitFor(() => expect(joins(session.socket)).toHaveLength(2), { timeout: 2500 })
  const retry = joins(session.socket)[1]!
  expect(retry.resume_token).toBe("cursor")
  expect(retry.payload?.admission_nonce).not.toBe(first.payload?.admission_nonce)
  act(() => session.socket.receive(ack(first)))
  expect(session.result.current.admittedRoom).toBeNull()
  act(() => session.socket.receive(ack(retry)))
  expect(session.result.current.admittedRoom).toBe(ROOM)
  expect(session.invalidate).not.toHaveBeenCalled()
})

it("does not revive an attempt superseded synchronously while send throws", async () => {
  const session = await connect()
  let failed: Join | undefined
  vi.spyOn(session.socket, "send").mockImplementationOnce((payload) => {
    failed = JSON.parse(payload) as Join
    session.result.current.sendLeave(ROOM)
    throw new Error("synthetic send failure after leave")
  })
  act(() => session.result.current.sendJoin(ROOM))
  expect(failed?.payload?.admission_nonce).toMatch(/^[0-9a-f]{32}$/)
  act(() => session.socket.receive(ack(failed!)))
  expect(session.result.current.admittedRoom).toBeNull()
  expect(session.socket.sent.map((payload) => JSON.parse(payload))).toEqual([
    { type: "leave", room: ROOM },
  ])
})
