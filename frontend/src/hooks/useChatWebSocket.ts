import {
  useEffect,
  useRef,
  useCallback,
  useState,
  useSyncExternalStore,
  createContext,
  useContext,
  useMemo,
} from "react"
import { useQueryClient } from "@tanstack/react-query"
import {
  chatApi,
  type Message,
  type MessagesListResponse,
  type ChatsListResponse,
} from "@/api/chat"
// Auth token storage handled natively via cookies
import { logError } from "@/app/logger"
import { parseWsMessage } from "@/api/schemas/wsMessage"
import api from "@/api/client"
import { getDatabaseLazily } from "@/db/lazy"

// Reconnection configuration
const RECONNECT_BASE_DELAY_MS = 1000 // 1 second
const RECONNECT_MAX_DELAY_MS = 30000 // 30 seconds
const PING_INTERVAL_MS = 30000 // Heartbeat every 30 seconds
// Wave 183 SW3 — Cap reconnection attempts to prevent runaway retry loops
// when backend is unreachable for extended periods. Before the cap, each
// failed attempt logged ~2 console errors (WS handshake fail + onerror
// handler). Empirically observed in SW1 verification under VITE_LHCI=true
// with no backend: 15+ attempts logged 30+ errors in 30 seconds.
// With max=10 attempts + exponential backoff (1s, 2s, 4s, 8s, 16s, then
// 30s cap × 5), total retry window is ~3 minutes before stopping. After
// the cap, the WS stays disconnected; user can manually retry via UI
// (W183 SW6 will add a "Reconnect" banner). In real production with
// backend running, first attempt typically succeeds, so this cap rarely
// fires.
const MAX_RECONNECT_ATTEMPTS = 10
// Wave 183 SW3 — extract magic number into named constant (W181 SW1
// convention). Typing indicator clears 3s after the last typing event from
// a peer; if peer continues typing, the next event resets the timeout.
const TYPING_INDICATOR_TIMEOUT_MS = 3000
export const LIVE_MESSAGE_CACHE_LIMIT = 200
// Retain the 4096 most-recently-seen composite chat/message IDs. This is wide
// enough to bridge ordinary reconnect replay windows while keeping hook memory
// strictly bounded; LRU refresh protects IDs that are actively replayed.
const LIVE_MESSAGE_DEDUP_LIMIT = 4096
const REPLAY_CHECKPOINT_PREFIX = "university.chat.replay.v2:"
const REPLAY_CHECKPOINT_LIMIT = 256
const REPLAY_CHECKPOINT_USER_LIMIT = 16
const REPLAY_CHECKPOINT_STORAGE_LIMIT = 65_536
type ReplayCheckpoint = { sequence: number; resumeToken: string }
const replayCheckpointMemory = new Map<string, Map<string, ReplayCheckpoint>>()
const replayCheckpointMounts = new Map<string, number>()

function replayCheckpointKey(userId: string): string {
  return `${REPLAY_CHECKPOINT_PREFIX}${encodeURIComponent(userId)}`
}

function persistReplayCheckpoints(userId: string, registry: Map<string, ReplayCheckpoint>): void {
  try {
    window.sessionStorage.setItem(
      replayCheckpointKey(userId),
      JSON.stringify({
        entries: [...registry.entries()].map(([chatId, checkpoint]) => [
          chatId,
          checkpoint.sequence,
          checkpoint.resumeToken,
        ]),
      })
    )
  } catch {
    // The in-memory registry still protects this mounted browser session.
  }
}

function replayCheckpointRegistry(userId: string): Map<string, ReplayCheckpoint> {
  const cached = replayCheckpointMemory.get(userId)
  if (cached) {
    replayCheckpointMemory.delete(userId)
    replayCheckpointMemory.set(userId, cached)
    return cached
  }

  const registry = new Map<string, ReplayCheckpoint>()
  replayCheckpointMemory.set(userId, registry)
  while (replayCheckpointMemory.size > REPLAY_CHECKPOINT_USER_LIMIT) {
    // size > limit proves the iterator has a first key.
    const oldestUserId = replayCheckpointMemory.keys().next().value!
    replayCheckpointMemory.delete(oldestUserId)
  }
  try {
    const key = replayCheckpointKey(userId)
    const stored = window.sessionStorage.getItem(key)
    if (stored === null) return registry
    if (stored.length > REPLAY_CHECKPOINT_STORAGE_LIMIT)
      throw new Error("checkpoint registry too large")
    const parsed = JSON.parse(stored) as { entries?: unknown }
    if (!Array.isArray(parsed.entries)) throw new Error("invalid checkpoint registry")
    for (const entry of parsed.entries.slice(-REPLAY_CHECKPOINT_LIMIT)) {
      if (
        !Array.isArray(entry) ||
        entry.length !== 3 ||
        typeof entry[0] !== "string" ||
        entry[0].length === 0 ||
        entry[0].length > 512 ||
        typeof entry[1] !== "number" ||
        !Number.isSafeInteger(entry[1]) ||
        entry[1] < 1 ||
        typeof entry[2] !== "string" ||
        entry[2].length === 0 ||
        entry[2].length > 4096
      ) {
        throw new Error("invalid checkpoint entry")
      }
      registry.delete(entry[0])
      registry.set(entry[0], { sequence: entry[1], resumeToken: entry[2] })
    }
  } catch {
    registry.clear()
    try {
      window.sessionStorage.removeItem(replayCheckpointKey(userId))
    } catch {
      // Storage can be disabled; the in-memory registry is already fail-closed.
    }
  }
  return registry
}

function readAndTouchReplayCheckpoint(
  userId: string | undefined,
  chatId: string
): ReplayCheckpoint | undefined {
  if (!userId) return undefined
  const registry = replayCheckpointRegistry(userId)
  const checkpoint = registry.get(chatId)
  if (checkpoint === undefined) return undefined
  registry.delete(chatId)
  registry.set(chatId, checkpoint)
  persistReplayCheckpoints(userId, registry)
  return checkpoint
}

function peekReplayCheckpoint(
  userId: string | undefined,
  chatId: string
): ReplayCheckpoint | undefined {
  if (!userId) return undefined
  return replayCheckpointRegistry(userId).get(chatId)
}

function writeReplayCheckpoint(
  userId: string | undefined,
  chatId: string,
  sequence: number,
  resumeToken: string,
  protectedChatId: string | null
): void {
  if (!userId) return
  const registry = replayCheckpointRegistry(userId)
  registry.delete(chatId)
  registry.set(chatId, { sequence, resumeToken })
  while (registry.size > REPLAY_CHECKPOINT_LIMIT) {
    const evictionCandidate = [...registry.keys()].find(
      (candidate) => candidate !== protectedChatId && candidate !== chatId
    )
    // A registry over the limit contains more entries than the two protected
    // ids, so a candidate necessarily exists.
    registry.delete(evictionCandidate!)
  }
  persistReplayCheckpoints(userId, registry)
}

function clearReplayCheckpoints(userId: string): void {
  replayCheckpointMemory.delete(userId)
  try {
    window.sessionStorage.removeItem(replayCheckpointKey(userId))
  } catch {
    // Storage can be disabled; the in-memory state was already cleared.
  }
}

function removeReplayCheckpoint(userId: string | undefined, chatId: string): void {
  if (!userId) return
  const registry = replayCheckpointRegistry(userId)
  if (!registry.delete(chatId)) return
  persistReplayCheckpoints(userId, registry)
}

function joinFrame(userId: string | undefined, chatId: string) {
  const checkpoint = readAndTouchReplayCheckpoint(userId, chatId)
  return checkpoint === undefined
    ? { type: "join", room: chatId }
    : { type: "join", room: chatId, resume_token: checkpoint.resumeToken }
}

export function rememberLiveMessage(
  seenMessageIds: Map<string, true>,
  chatId: string,
  messageId: string
): boolean {
  const key = `${chatId}\u0000${messageId}`
  if (seenMessageIds.has(key)) {
    // Refresh duplicate entries so frequently replayed frames remain protected
    // when the bounded window evicts its least-recently-seen member.
    seenMessageIds.delete(key)
    seenMessageIds.set(key, true)
    return false
  }

  seenMessageIds.set(key, true)
  if (seenMessageIds.size > LIVE_MESSAGE_DEDUP_LIMIT) {
    seenMessageIds.delete(seenMessageIds.keys().next().value!)
  }
  return true
}

function messageEpochMicroseconds(createdAt: string): bigint | null {
  const epochMilliseconds = Date.parse(createdAt)
  if (!Number.isFinite(epochMilliseconds)) return null

  // Date.parse keeps only millisecond precision. Preserve the final three
  // fractional digits so the cursor exactly matches the backend's integer
  // microsecond keyset contract.
  const fractional = /\.(\d{1,6})(?:Z|[+-]\d{2}:\d{2})$/u.exec(createdAt)?.[1] ?? ""
  const subMillisecondDigits = fractional.padEnd(6, "0").slice(3, 6)
  return BigInt(epochMilliseconds) * 1000n + BigInt(subMillisecondDigits)
}

function compareMessageOrder(left: Message, right: Message): number | null {
  const leftEpoch = messageEpochMicroseconds(left.created_at)
  const rightEpoch = messageEpochMicroseconds(right.created_at)
  if (leftEpoch === null || rightEpoch === null) return null
  if (leftEpoch < rightEpoch) return -1
  if (leftEpoch > rightEpoch) return 1

  const leftId = String(left.id)
  const rightId = String(right.id)
  if (leftId < rightId) return -1
  if (leftId > rightId) return 1
  return 0
}

function messageHistoryCursor(message: Message): string {
  return `${messageEpochMicroseconds(message.created_at)!}:${message.id}`
}

// MOD-W10-05: Per-message-type minimum interval (ms) for outgoing WS messages.
// Prevents a runaway component from flooding the server with typing events
const OUTGOING_RATE_LIMITS: Readonly<Record<string, number>> = {
  typing: 500, // at most one "typing" event per 500 ms
  read: 200, // at most one "read" receipt per 200 ms per chat
} as const

export function appendLiveMessageToCache(
  cached: MessagesListResponse,
  message: Message
): MessagesListResponse {
  const unorderedItems = [...cached.items, message]
  // An invalid timestamp makes ordering and a lossless recovery edge
  // unknowable. Preserve deterministic arrival order, but never relax the hard
  // memory bound; the hook forces an active history refetch to repair this
  // legacy/corrupt cache path. Wire frames are rejected earlier by Valibot.
  if (unorderedItems.some((item) => messageEpochMicroseconds(item.created_at) === null)) {
    if (unorderedItems.length <= LIVE_MESSAGE_CACHE_LIMIT) {
      return { ...cached, items: unorderedItems }
    }
    return {
      ...cached,
      items: unorderedItems.slice(-LIVE_MESSAGE_CACHE_LIMIT),
      has_more: true,
    }
  }

  // Backend history is ascending by (created_at, id). Insert a delayed live
  // frame at the same deterministic position without re-sorting existing items
  // or changing their object identity, preserving virtualizer scroll anchors.
  const insertionIndex = cached.items.findIndex(
    (cachedMessage) => compareMessageOrder(message, cachedMessage)! < 0
  )
  const items =
    insertionIndex < 0
      ? unorderedItems
      : [...cached.items.slice(0, insertionIndex), message, ...cached.items.slice(insertionIndex)]
  if (items.length <= LIVE_MESSAGE_CACHE_LIMIT) return { ...cached, items }

  const boundedItems = items.slice(-LIVE_MESSAGE_CACHE_LIMIT)
  const recoveryCursor = messageHistoryCursor(boundedItems[0]!)
  return {
    ...cached,
    items: boundedItems,
    has_more: true,
    next_cursor: recoveryCursor,
  }
}

/**
 * Calculate reconnection delay with full-jitter exponential backoff.
 */
export function calculateReconnectDelay(attempt: number): number {
  const base = Math.min(RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt), RECONNECT_MAX_DELAY_MS)
  return Math.floor(Math.random() * base)
}

/**
 * Pure cache update for a chat-level `read` frame. Extracted as a module-level
 * function so the transformation remains directly testable independently of
 * the WebSocket ticket and transport machinery.
 *
 * The frame's `user_id` is the READER (the other participant). Every message NOT
 * sent by the reader — i.e. the current user's own sent messages, in a 1-on-1 DM
 * — flips to read + the chat-level read_at. Idempotent: re-applying is a no-op.
 */
export function applyReadFrame(
  old: MessagesListResponse | undefined,
  frame: { user_id: string; read_at: string | null }
): MessagesListResponse | undefined {
  if (!old) return old
  return {
    ...old,
    items: old.items.map((m) =>
      m.sender_id !== frame.user_id ? { ...m, read_status: true, read_at: frame.read_at } : m
    ),
  }
}

/**
 * Wave 205 — pure cache update for a `message_edited` frame. Replaces content +
 * edited_at for the matching message in the open chat. Idempotent: re-applying the
 * same frame is a no-op, so the author's own NATS echo (arriving after the optimistic
 * mutation) just reconciles its client-time edited_at to the authoritative server value.
 */
export function applyMessageEditedFrame(
  old: MessagesListResponse | undefined,
  frame: { message_id: string; content: string; edited_at: string }
): MessagesListResponse | undefined {
  if (!old) return old
  return {
    ...old,
    items: old.items.map((m) =>
      m.id === frame.message_id ? { ...m, content: frame.content, edited_at: frame.edited_at } : m
    ),
  }
}

/**
 * Wave 205 — pure cache update for a `message_deleted` frame. Soft-deletes the
 * matching message: stamps deleted_at + clears content/attachments (the tombstone the
 * UI renders as "Message deleted"). Idempotent.
 */
export function applyMessageDeletedFrame(
  old: MessagesListResponse | undefined,
  frame: { message_id: string; deleted_at: string }
): MessagesListResponse | undefined {
  if (!old) return old
  return {
    ...old,
    items: old.items.map((m) =>
      m.id === frame.message_id
        ? { ...m, deleted_at: frame.deleted_at, content: "", attachments: [] }
        : m
    ),
  }
}

/**
 * Wave 206 — pure cache update for a `reaction_changed` DELTA frame. Patches the
 * matched message's reaction aggregate: added → +1 (or push {emoji, count:1,
 * reacted_by_me:false}); removed → -1 (drop when count hits 0). reacted_by_me is
 * left untouched — the frame's actor is never the current user (the case-handler
 * self-echo guard skips the actor, who already patched optimistically), and a
 * peer's reaction must not flip the viewer's own flag. Drift self-heals on refetch.
 */
export function applyReactionChangedFrame(
  old: MessagesListResponse | undefined,
  frame: { message_id: string; emoji: string; action: "added" | "removed" }
): MessagesListResponse | undefined {
  if (!old) return old
  return {
    ...old,
    items: old.items.map((m) => {
      if (m.id !== frame.message_id) return m
      const reactions = [...(m.reactions ?? [])]
      const idx = reactions.findIndex((r) => r.emoji === frame.emoji)
      const existing = reactions[idx] // idx === -1 → undefined (noUncheckedIndexedAccess)
      if (frame.action === "added") {
        if (existing) {
          reactions[idx] = { ...existing, count: existing.count + 1 }
        } else {
          reactions.push({ emoji: frame.emoji, count: 1, reacted_by_me: false })
        }
      } else if (existing) {
        const next = existing.count - 1
        if (next <= 0) {
          reactions.splice(idx, 1)
        } else {
          reactions[idx] = { ...existing, count: next }
        }
      }
      return { ...m, reactions }
    }),
  }
}

// WebSocket message types
export type WebSocketMessageType =
  | "ping"
  | "pong"
  | "typing"
  | "read"
  | "new_message"
  | "online"
  | "presence"
  | "error"
  | "message_edited"
  | "message_deleted"
  | "reaction_changed"

export interface WebSocketMessage {
  type: WebSocketMessageType
  chat_id?: string
  message_id?: string
  user_id?: string
  user_name?: string
  message?: Message
  status?: boolean
  users?: string[]
  active?: boolean
  last_seen?: string | null
  read_at?: string | null // Wave 203 — chat-level read-receipt timestamp
}

export interface UseChatWebSocketOptions {
  enabled?: boolean
  // Wave 204 SW4 — the current user's id, used to drop self-echoes: the
  // NATS→ws-hub→room fan-out (W204 SW2) has no per-recipient exclusion, so the
  // sender receives its own new_message/read frame back. Threaded from useAuth
  // via MessengerContext (W204 SW5).
  currentUserId?: string
  onNewMessage?: (message: Message, chatId: string) => void
  onTyping?: (chatId: string, userId: string, userName: string) => void
  // Wave 203 SW5 — chat-level read receipt: (chatId, readerId, readAt).
  onRead?: (chatId: string, userId: string, readAt: string | null) => void
  onOnlineStatus?: (userId: string, status: boolean) => void
  onPresenceUpdate?: (userId: string, active: boolean, lastSeen: string | null) => void
  /**
   * RZ-W15-03 (audit 2026-03-23 Wave 15): Called when the upgrade-ticket fetch
   * returns 401 or 403, indicating the session has expired or been revoked.
   * Callers should redirect to /login or trigger a full logout.
   */
  onAuthError?: () => void
}

interface TypingUser {
  userId: string
  userName: string
  timeout: ReturnType<typeof setTimeout>
}

/**
 * MOD-11 Fix: useSyncExternalStore for robust WS connection state.
 *
 * TD-09: Replaced manual useRef/useEffect connection tracking with an external
 * store pattern. This natively handles React Strict Mode double-mounts
 * without complex internal flags and ensures consistent 'isConnected' state
 * across all consuming components.
 */
class WebSocketStore {
  private isConnected = false
  private listeners: Set<() => void> = new Set()

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  getSnapshot = () => this.isConnected

  setConnected(status: boolean) {
    if (this.isConnected === status) return
    this.isConnected = status
    this.emitChange()
  }

  private emitChange() {
    for (const listener of this.listeners) listener()
  }
}

import { createElement } from "react"

export const WebSocketStoreContext = createContext<WebSocketStore | null>(null)

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const store = useMemo(() => new WebSocketStore(), [])
  return createElement(WebSocketStoreContext.Provider, { value: store }, children)
}
export function useChatWebSocket({
  enabled = true,
  currentUserId,
  onNewMessage,
  onTyping,
  onRead,
  onOnlineStatus,
  onPresenceUpdate,
  onAuthError,
}: UseChatWebSocketOptions) {
  const wsStore = useContext(WebSocketStoreContext)
  if (!wsStore) {
    throw new Error("useChatWebSocket must be used within a WebSocketProvider")
  }

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectAttemptRef = useRef(0)
  const connectionGenerationRef = useRef(0)
  const ticketRequestRef = useRef<{
    generation: number
    controller: AbortController
  } | null>(null)

  // MOD-11: Subscribe to external store for connection state
  // W127 SW1: 3rd arg getServerSnapshot returns `false` — no WS connection
  // exists server-side, so SSR-rendered consumers (MessengerProvider via
  // AppProviders chain in __root.tsx RootComponent) see disconnected state.
  // Without this arg, React 19 throws "Missing getServerSnapshot, which is
  // required for server-rendered content" at module evaluation time.
  const isConnected = useSyncExternalStore(wsStore.subscribe, wsStore.getSnapshot, () => false)

  const [typingUsers, setTypingUsers] = useState<Map<string, TypingUser>>(new Map())
  const queryClient = useQueryClient()
  const lastSentRef = useRef<Map<string, number>>(new Map())

  const onNewMessageRef = useRef(onNewMessage)
  const onTypingRef = useRef(onTyping)
  const onReadRef = useRef(onRead)
  const onOnlineStatusRef = useRef(onOnlineStatus)
  const onPresenceUpdateRef = useRef(onPresenceUpdate)
  const onAuthErrorRef = useRef(onAuthError)
  const mountedRef = useRef(false)
  // Assigned by the first effect before the connection effect can schedule a
  // retry. Avoid a never-invoked placeholder callback in the runtime graph.
  const connectRef = useRef<() => void>(null!)
  // W204 SW4 — latest current-user id (self-echo guard) + the room this client
  // should be joined to (re-sent on every (re)connect in ws.onopen, since
  // ws-hub room membership is per-connection).
  const currentUserIdRef = useRef(currentUserId)
  const activeRoomRef = useRef<string | null>(null)
  // At-least-once delivery can replay a message after it has left the smaller
  // render cache. Keep transport deduplication independent and bounded for the
  // complete authenticated hook session, including reconnects.
  const seenMessageIdsRef = useRef<Map<string, true>>(new Map())
  const seenMessageSessionRef = useRef(currentUserId)

  useEffect(() => {
    if (seenMessageSessionRef.current !== currentUserId) {
      if (seenMessageSessionRef.current) {
        clearReplayCheckpoints(seenMessageSessionRef.current)
      }
      seenMessageIdsRef.current.clear()
      seenMessageSessionRef.current = currentUserId
    }
    onNewMessageRef.current = onNewMessage
    onTypingRef.current = onTyping
    onReadRef.current = onRead
    onOnlineStatusRef.current = onOnlineStatus
    onPresenceUpdateRef.current = onPresenceUpdate
    onAuthErrorRef.current = onAuthError
    currentUserIdRef.current = currentUserId
  })

  useEffect(
    () => () => {
      seenMessageIdsRef.current.clear()
    },
    []
  )

  useEffect(() => {
    if (!currentUserId) return
    replayCheckpointMounts.set(currentUserId, (replayCheckpointMounts.get(currentUserId) ?? 0) + 1)
    return () => {
      // This cleanup exists only after the setup increment above.
      const remaining = replayCheckpointMounts.get(currentUserId)! - 1
      if (remaining > 0) {
        replayCheckpointMounts.set(currentUserId, remaining)
        return
      }
      replayCheckpointMounts.delete(currentUserId)
      replayCheckpointMemory.delete(currentUserId)
    }
  }, [currentUserId])

  const cleanup = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current)
      pingIntervalRef.current = null
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    setTypingUsers((currentMap) => {
      currentMap.forEach((user) => clearTimeout(user.timeout))
      return new Map()
    })
  }, [])

  const connect = useCallback(() => {
    if (!enabled || !mountedRef.current || navigator.onLine === false) return

    if (
      ticketRequestRef.current ||
      (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED)
    ) {
      return
    }
    const requestGeneration = ++connectionGenerationRef.current
    const ticketController = new AbortController()
    ticketRequestRef.current = { generation: requestGeneration, controller: ticketController }

    // RZ-W14-01 (audit 2026-03-23 Wave 14): fetch a short-lived upgrade ticket
    // before opening the WebSocket.  This eliminates the JWT from the URL and
    // from Sec-WebSocket-Protocol headers (which are written to proxy logs).
    //
    // Flow: POST /ws/ticket → { ticket, expires_in: 15 }
    //       new WebSocket(`${wsUrl}?ticket=${ticket}`)
    //
    // The ticket is single-use and expires after 15s — it is consumed atomically
    // by the server on the first upgrade attempt, preventing replay.
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const baseWsUrl = `${wsProtocol}//${window.location.host}/ws/chat`

    void (async () => {
      // RZ-W15-03 (audit 2026-03-23 Wave 15): Upgrade tickets are mandatory since
      // Wave 14 (RZ-W14-01).  ws-hub rejects WS connections without a valid ticket.
      // Error handling is now explicit:
      //   • 401 / 403 → session expired or revoked; call onAuthError, do NOT connect.
      //   • Other non-2xx (5xx, network error) → transient; schedule a backoff reconnect.
      // The previous "fall through to cookie-auth" comment was incorrect — the server
      // does NOT accept cookie-only upgrades since Wave 14.
      let ticket: string
      // TD-26-02: AbortController for cleanup on unmount; TD-26-03: 5s timeout
      const ticketTimeout = setTimeout(() => ticketController.abort(), 5000)
      try {
        // FIX-44-02: Use axios instead of fetch so CSRF header (X-CSRF-Token)
        // is automatically attached from the csrf_token cookie.
        // baseURL: "" prevents axios from prepending /api/v1 — the /ws/ticket
        // endpoint lives outside the API prefix (nginx /ws/ location block).
        const resp = await api.post<{ ticket: string; expires_in: number }>(
          "/ws/ticket",
          undefined,
          { signal: ticketController.signal, baseURL: "" }
        )
        ticket = resp.data.ticket
      } catch (e: unknown) {
        if (ticketController.signal.aborted || !mountedRef.current) return
        const axiosErr = e as { response?: { status: number } }
        const status = axiosErr?.response?.status
        if (status === 401 || status === 403) {
          // Session expired or revoked — do not attempt to connect.
          logError("[WebSocket] Session invalid (status %s); aborting connection.", status)
          onAuthErrorRef.current?.()
        } else {
          // Transient server/network error — schedule backoff reconnect.
          if (navigator.onLine === false) return
          if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
            logError("[WebSocket] Ticket retry limit reached.", {
              attempts: reconnectAttemptRef.current,
            })
            return
          }
          logError("[WebSocket] Ticket fetch failed; will retry.", e)
          const delay = calculateReconnectDelay(reconnectAttemptRef.current)
          reconnectAttemptRef.current += 1
          reconnectTimeoutRef.current = setTimeout(() => connectRef.current(), delay)
        }
        return
      } finally {
        clearTimeout(ticketTimeout) // TD-26-03: clean up timeout
        if (ticketRequestRef.current?.generation === requestGeneration) {
          ticketRequestRef.current = null
        }
      }

      if (
        !mountedRef.current ||
        ticketController.signal.aborted ||
        !enabled ||
        connectionGenerationRef.current !== requestGeneration
      )
        return

      try {
        const ws = new WebSocket(`${baseWsUrl}?ticket=${encodeURIComponent(ticket)}`)
        wsRef.current = ws

        ws.onopen = () => {
          wsStore.setConnected(true)
          reconnectAttemptRef.current = 0

          // W204 SW4 — rejoin the active room on (re)connect. ws-hub room
          // membership is per-connection: a reconnect is a fresh Client with
          // empty Rooms, so without re-joining the browser silently receives
          // nothing after a reconnect until the next chat-select.
          if (activeRoomRef.current) {
            try {
              ws.send(JSON.stringify(joinFrame(currentUserIdRef.current, activeRoomRef.current)))
            } catch {
              /* WS closed between open and send — the next connect re-joins */
            }
          }

          if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)
          pingIntervalRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "ping" }))
            }
          }, PING_INTERVAL_MS)
        }

        ws.onmessage = (event) => {
          try {
            const validated = parseWsMessage(event.data)
            if (!validated) {
              // MOD-W18-02 (audit 2026-03-23 Wave 18): log invalid frames for
              // observability. Previously silent drops made attack detection difficult.
              // Wave 183 SW3 — console.warn → logError. Invalid WS frames are
              // security-relevant (attack detection signal); the project's
              // logger pipes through Sentry breadcrumbs for forensic trail,
              // unlike raw console.warn which is silently dropped in prod.
              logError("[ws] Invalid frame dropped", { size: (event.data as string).length })
              return
            }

            const sequencedChatId = "chat_id" in validated ? validated.chat_id : undefined
            // An event without a stream sequence cannot be older than a durable
            // checkpoint. Normalizing that absence to an explicit upper sentinel
            // keeps the comparison total and avoids a redundant undefined guard.
            const incomingSequence = validated.stream_seq ?? Number.POSITIVE_INFINITY
            if (
              sequencedChatId !== undefined &&
              incomingSequence <=
                (peekReplayCheckpoint(currentUserIdRef.current, sequencedChatId)?.sequence ?? 0)
            ) {
              return
            }

            switch (validated.type) {
              case "new_message": {
                // A self-authored live echo is usually already present from the
                // optimistic mutation. A replay can arrive after that optimistic
                // cache entry was lost, though, so cache presence—not authorship—
                // decides whether reconciliation may be skipped.
                const selfAuthored = validated.message.sender_id === currentUserIdRef.current
                const cachedMessages = queryClient.getQueryData<MessagesListResponse>([
                  "messages",
                  validated.chat_id,
                ])
                const selfMessageAlreadyPresent =
                  selfAuthored &&
                  cachedMessages?.items.some((message) => message.id === validated.message.id)
                if (selfMessageAlreadyPresent) {
                  rememberLiveMessage(
                    seenMessageIdsRef.current,
                    validated.chat_id,
                    validated.message.id
                  )
                  break
                }
                if (
                  !rememberLiveMessage(
                    seenMessageIdsRef.current,
                    validated.chat_id,
                    validated.message.id
                  ) &&
                  !selfAuthored
                )
                  break

                // Wave 202 SW2 — `validated.message` is the Valibot `ParsedMessage`
                // (attachments/sender validated shape-only as Record<string,unknown>);
                // the cache stores `@/api/chat` `Message` (typed Attachment[]/User).
                // `Message` is assignable to `ParsedMessage`, so the two are comparable
                // → a single `as Message` is valid (collapsed from the prior, redundant
                // `as unknown as Message` double-cast; the `unknown` hop was never needed).
                // Do NOT delete the cast — `ParsedMessage` is NOT structurally `Message`.
                let inserted = false
                let requiresHistoryRecovery =
                  messageEpochMicroseconds(validated.message.created_at) === null
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", validated.chat_id],
                  (old) => {
                    if (!old) {
                      inserted = true
                      return {
                        items: [validated.message as Message],
                        has_more: false,
                        next_cursor: null,
                      }
                    }
                    if (old.items.some((m) => m.id === validated.message.id)) return old
                    requiresHistoryRecovery ||= old.items.some(
                      (message) => messageEpochMicroseconds(message.created_at) === null
                    )
                    inserted = true
                    return appendLiveMessageToCache(old, validated.message as Message)
                  }
                )
                if (!inserted) break

                // Persist only newly accepted frames to RxDB. A repeated delivery
                // is idempotent across the in-memory cache, unread count and callbacks.
                getDatabaseLazily()
                  .then((db) => {
                    const msg = validated.message as Message
                    db.messages
                      .upsert({
                        id: String(msg.id),
                        chat_id: String(validated.chat_id),
                        sender_id: String(msg.sender_id),
                        content: msg.content || "",
                        created_at: msg.created_at || new Date().toISOString(),
                        read_status: msg.read_status ?? false,
                        read_at: msg.read_at ?? null,
                        edited_at: msg.edited_at ?? null,
                        deleted_at: msg.deleted_at ?? null,
                        attachments: msg.attachments ?? [],
                        reactions: msg.reactions ?? [],
                        sync_status: "synced",
                      })
                      .catch(() => {})
                  })
                  .catch(() => {})
                queryClient.invalidateQueries({
                  queryKey: ["messages", validated.chat_id],
                  refetchType: requiresHistoryRecovery ? "active" : "none",
                })
                queryClient.setQueryData<ChatsListResponse>(["chats"], (old) => {
                  if (!old) return old
                  const incomingMessage = validated.message as Message
                  return {
                    ...old,
                    items: old.items.map((chat) =>
                      chat.id === validated.chat_id
                        ? {
                            ...chat,
                            last_message:
                              !chat.last_message ||
                              (compareMessageOrder(incomingMessage, chat.last_message) ?? -1) > 0
                                ? incomingMessage
                                : chat.last_message,
                            unread_count: selfAuthored ? chat.unread_count : chat.unread_count + 1,
                          }
                        : chat
                    ),
                  }
                })
                queryClient.invalidateQueries({ queryKey: ["chats"], refetchType: "none" })
                if (!selfAuthored) {
                  onNewMessageRef.current?.(validated.message as Message, validated.chat_id)
                }
                break
              }

              case "typing": {
                // PERF-26-02: per-chat cap replaces global 100 cap (was PERF-W18-02).
                // Global cap starved low-activity chats when many chats were active.
                const MAX_TYPING_PER_CHAT = 20
                setTypingUsers((prev) => {
                  const key = `${validated.chat_id}:${validated.user_id}`
                  // Allow updates to existing keys but reject new keys when at per-chat capacity
                  if (!prev.has(key)) {
                    let chatCount = 0
                    for (const k of prev.keys()) {
                      if (k.startsWith(`${validated.chat_id}:`)) chatCount++
                    }
                    if (chatCount >= MAX_TYPING_PER_CHAT) return prev
                  }
                  const newMap = new Map(prev)
                  const existing = newMap.get(key)
                  if (existing) clearTimeout(existing.timeout)

                  const timeout = setTimeout(() => {
                    if (!mountedRef.current) return
                    setTypingUsers((p) => {
                      if (!p.has(key)) return p
                      const updated = new Map(p)
                      updated.delete(key)
                      return updated
                    })
                  }, TYPING_INDICATOR_TIMEOUT_MS)

                  newMap.set(key, {
                    userId: validated.user_id,
                    userName: validated.user_name,
                    timeout,
                  })
                  return newMap
                })
                onTypingRef.current?.(validated.chat_id, validated.user_id, validated.user_name)
                break
              }

              case "read": {
                // W204 SW4 — self-echo guard. The reader receives its own read
                // frame back via the room fan-out (no per-recipient exclusion).
                // Skip it: applyReadFrame would flip the OTHER party's messages
                // to read in the reader's own cache (harmless but pointless
                // churn). The SENDER (user_id !== me) DOES process it → their
                // sent bubbles flip to "Seen · HH:MM" live.
                if (validated.user_id === currentUserIdRef.current) break
                // Wave 203 SW5 — chat-level read receipt. Flip every message NOT
                // sent by the reader (validated.user_id) to read + stamp the
                // chat-level read_at. applyReadFrame is the pure, unit-tested core.
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", validated.chat_id],
                  (old) => applyReadFrame(old, validated)
                )
                queryClient.invalidateQueries({
                  queryKey: ["messages", validated.chat_id],
                  refetchType: "none",
                })
                onReadRef.current?.(validated.chat_id, validated.user_id, validated.read_at)
                break
              }

              case "message_edited": {
                // Wave 205 — no self-echo guard: the frame is REST-initiated (carries
                // no actor) and applyMessageEditedFrame is idempotent, so the author's
                // own echo merely reconciles its optimistic client-time edited_at to the
                // authoritative server value. The OTHER participant sees the edit live.
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", validated.chat_id],
                  (old) => applyMessageEditedFrame(old, validated)
                )
                queryClient.invalidateQueries({
                  queryKey: ["messages", validated.chat_id],
                  refetchType: "none",
                })
                break
              }

              case "message_deleted": {
                // Wave 205 — soft-delete tombstone live; idempotent, no self-echo guard.
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", validated.chat_id],
                  (old) => applyMessageDeletedFrame(old, validated)
                )
                queryClient.invalidateQueries({
                  queryKey: ["messages", validated.chat_id],
                  refetchType: "none",
                })
                break
              }

              case "reaction_changed": {
                // Wave 206 — DELTA frame self-echo guard: the actor already patched
                // optimistically in toggleReactionMutation, so applying its own echo
                // would double-count. Other participants apply the delta live; a
                // missed/duplicate frame self-heals on the next GET /messages.
                if (validated.user_id === currentUserIdRef.current) break
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", validated.chat_id],
                  (old) => applyReactionChangedFrame(old, validated)
                )
                queryClient.invalidateQueries({
                  queryKey: ["messages", validated.chat_id],
                  refetchType: "none",
                })
                break
              }

              case "online": {
                onOnlineStatusRef.current?.(validated.user_id, validated.status)
                break
              }

              case "presence": {
                onPresenceUpdateRef.current?.(
                  validated.user_id,
                  validated.active,
                  validated.last_seen
                )
                onOnlineStatusRef.current?.(validated.user_id, validated.active)
                break
              }

              case "replay_checkpoint":
                // The server terminated a permanently malformed replay event.
                // Advancing the durable sequence below prevents that poison event
                // from being requested again on every reconnect.
                break

              case "error":
                if (validated.code === "invalid_resume_token" && validated.room !== undefined) {
                  removeReplayCheckpoint(currentUserIdRef.current, validated.room)
                  void queryClient.invalidateQueries({
                    queryKey: ["messages", validated.room],
                    refetchType: "all",
                  })
                  void queryClient.invalidateQueries({
                    queryKey: ["chats"],
                    refetchType: "all",
                  })
                }
                logError("[WebSocket] Server error:", validated)
                break
            }
            if (
              validated.stream_seq !== undefined &&
              validated.resume_token !== undefined &&
              sequencedChatId !== undefined
            ) {
              writeReplayCheckpoint(
                currentUserIdRef.current,
                sequencedChatId,
                validated.stream_seq,
                validated.resume_token,
                activeRoomRef.current
              )
            }
          } catch (e) {
            logError("[WebSocket] Failed to parse message:", e)
          }
        }

        ws.onclose = (event) => {
          // A late close from a superseded transport must not tear down the
          // connection state or timers belonging to the newer socket.
          if (wsRef.current !== ws) return
          wsRef.current = null
          wsStore.setConnected(false)
          cleanup()

          // Wave 183 SW3 — added MAX_RECONNECT_ATTEMPTS cap to prevent
          // runaway retry loops. Pre-W183 retried indefinitely on every
          // non-clean close, generating perpetual console errors when
          // backend was unreachable for extended periods. Empirically
          // observed in SW1 verification: 15+ attempts in 30s with no
          // backend, 30+ console errors logged. With cap, total retry
          // window is ~3 min (1s+2s+4s+8s+16s+30s×5) before giving up.
          // After cap, WS stays disconnected; W183 SW6 will add a UI
          // reconnect banner. Codes 1000 (normal close), 4001 (auth
          // expired), 4003 (forbidden) already short-circuit retries.
          if (event.code !== 1000 && event.code !== 4001 && event.code !== 4003) {
            if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
              logError(
                "[ws] Max reconnect attempts reached; giving up. Manual reconnect required.",
                { attempts: reconnectAttemptRef.current, lastCode: event.code }
              )
              return
            }
            const delay = calculateReconnectDelay(reconnectAttemptRef.current)
            reconnectAttemptRef.current += 1
            reconnectTimeoutRef.current = setTimeout(() => {
              connectRef.current()
            }, delay)
          }
        }

        ws.onerror = (error) => {
          logError("[WebSocket] Error:", error)
        }
      } catch (e) {
        logError("[WebSocket] Failed to connect:", e)
      }
    })() // end async IIFE — ticket fetch + WS connect
  }, [enabled, cleanup, queryClient, wsStore])

  const disconnect = useCallback(() => {
    cleanup()
    connectionGenerationRef.current += 1
    ticketRequestRef.current?.controller.abort()
    ticketRequestRef.current = null
    if (wsRef.current) {
      wsRef.current.close(1000)
      wsRef.current = null
    }
    wsStore.setConnected(false)
  }, [cleanup, wsStore])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()

    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, [enabled, connect, disconnect])

  useEffect(() => {
    if (!enabled) return
    const onOnline = () => {
      reconnectAttemptRef.current = 0
      connectRef.current()
    }
    const onOffline = () => disconnect()
    window.addEventListener("online", onOnline)
    window.addEventListener("offline", onOffline)
    return () => {
      window.removeEventListener("online", onOnline)
      window.removeEventListener("offline", onOffline)
    }
  }, [disconnect, enabled])

  // Wave 207 — typing is broadcast via REST (POST /chats/{id}/typing), NOT over the
  // WS: the frontend connects to ws-hub, whose allowedMessageTypes drops "typing" at
  // its parse boundary, so the pre-W207 wsRef.send({type:"typing"}) went nowhere. The
  // backend endpoint does participant authz + broadcast_to_chat → W204 bridge → ws-hub
  // chat.* fan-out → the recipient's live TypingIndicator (the receive-side `case
  // "typing"` handler is unchanged). The 500ms throttle is preserved (caps the REST
  // rate, complements the server's 180/60 limiter). NO WS-open guard: delivery depends
  // on the RECIPIENT's socket (server-side), not the sender's — so it fires whenever
  // the user is typing. Fire-and-forget; typing is ephemeral, errors are swallowed.
  const sendTyping = useCallback((chatId: string) => {
    const key = `typing:${chatId}`
    const now = Date.now()
    if (now - (lastSentRef.current.get(key) ?? 0) < OUTGOING_RATE_LIMITS.typing!) return
    lastSentRef.current.set(key, now)
    void chatApi.sendTyping(chatId).catch(() => {
      /* typing is ephemeral — swallow transient errors */
    })
  }, [])

  const sendRead = useCallback((chatId: string) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return
    const key = `read:${chatId}`
    const now = Date.now()
    if (now - (lastSentRef.current.get(key) ?? 0) < OUTGOING_RATE_LIMITS.read!) return
    lastSentRef.current.set(key, now)
    try {
      // RZ-26-07: guard TOCTOU race — WS may close between readyState check and send.
      // Wave 203 SW5 — chat-level read frame (no message_id).
      wsRef.current.send(JSON.stringify({ type: "read", chat_id: chatId }))
    } catch {
      /* WS closed between readyState check and send — safe to ignore */
    }
  }, [])

  // W204 SW4 — join/leave a ws-hub room (room == chat_id). A client must JOIN
  // to RECEIVE chat.{room} fan-out: ws-hub's collectRecipients returns nil for
  // an empty Rooms[room]. ws-hub authorizes the join via
  // /api/internal/chat/check-participant before adding the client. activeRoomRef
  // is set FIRST (before the OPEN check) so a chat selected before the socket
  // is open is still joined on the next ws.onopen.
  const sendJoin = useCallback((roomId: string) => {
    activeRoomRef.current = roomId
    if (wsRef.current?.readyState !== WebSocket.OPEN) return
    try {
      // RZ-26-07: guard TOCTOU race — WS may close between readyState check and send.
      wsRef.current.send(JSON.stringify(joinFrame(currentUserIdRef.current, roomId)))
    } catch {
      /* WS closed between readyState check and send — onopen re-joins activeRoomRef */
    }
  }, [])

  const sendLeave = useCallback((roomId: string) => {
    if (activeRoomRef.current === roomId) activeRoomRef.current = null
    if (wsRef.current?.readyState !== WebSocket.OPEN) return
    try {
      wsRef.current.send(JSON.stringify({ type: "leave", room: roomId }))
    } catch {
      /* WS closed — ws-hub strips room membership on disconnect anyway */
    }
  }, [])

  const getTypingUsersForChat = useCallback(
    (chatId: string) => {
      const users: { userId: string; userName: string }[] = []
      typingUsers.forEach((value, key) => {
        if (key.startsWith(`${chatId}:`)) {
          users.push({ userId: value.userId, userName: value.userName })
        }
      })
      return users
    },
    [typingUsers]
  )

  return {
    isConnected,
    sendTyping,
    sendRead,
    sendJoin,
    sendLeave,
    getTypingUsersForChat,
    disconnect,
    reconnect: connect,
  }
}
