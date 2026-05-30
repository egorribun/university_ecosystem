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
import type { Message, MessagesListResponse, ChatsListResponse } from "@/api/chat"
// Auth token storage handled natively via cookies
import { logError } from "@/app/logger"
import { parseWsMessage } from "@/api/schemas/wsMessage"
import api from "@/api/client"

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

// MOD-W10-05: Per-message-type minimum interval (ms) for outgoing WS messages.
// Prevents a runaway component from flooding the server with typing events
const OUTGOING_RATE_LIMITS: Readonly<Record<string, number>> = {
  typing: 500, // at most one "typing" event per 500 ms
  read: 200, // at most one "read" receipt per 200 ms per chat
} as const

/**
 * Calculate reconnection delay with full-jitter exponential backoff.
 */
function calculateReconnectDelay(attempt: number): number {
  const base = Math.min(RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt), RECONNECT_MAX_DELAY_MS)
  return Math.floor(Math.random() * base)
}

/**
 * Wave 203 SW5 — pure cache update for a chat-level `read` frame. Extracted as a
 * module-level function so it is unit-testable without the WS/ticket machinery
 * (the useChatWebSocket hook test suite is describe.skip'd since W113 on a
 * missing MSW ticket handler).
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
  const connectRef = useRef<() => void>(() => {})

  useEffect(() => {
    onNewMessageRef.current = onNewMessage
    onTypingRef.current = onTyping
    onReadRef.current = onRead
    onOnlineStatusRef.current = onOnlineStatus
    onPresenceUpdateRef.current = onPresenceUpdate
    onAuthErrorRef.current = onAuthError
  })

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
    if (!enabled) return

    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      return
    }

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
      const ticketController = new AbortController()
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
        const axiosErr = e as { response?: { status: number } }
        const status = axiosErr?.response?.status
        if (status === 401 || status === 403) {
          // Session expired or revoked — do not attempt to connect.
          logError("[WebSocket] Session invalid (status %s); aborting connection.", status)
          onAuthErrorRef.current?.()
        } else {
          // Transient server/network error — schedule backoff reconnect.
          logError("[WebSocket] Ticket fetch failed; will retry.", e)
          const delay = calculateReconnectDelay(reconnectAttemptRef.current)
          reconnectAttemptRef.current += 1
          reconnectTimeoutRef.current = setTimeout(() => connectRef.current(), delay)
        }
        return
      } finally {
        clearTimeout(ticketTimeout) // TD-26-03: clean up timeout
      }

      try {
        const ws = new WebSocket(`${baseWsUrl}?ticket=${encodeURIComponent(ticket)}`)
        wsRef.current = ws

        ws.onopen = () => {
          wsStore.setConnected(true)
          reconnectAttemptRef.current = 0

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

            switch (validated.type) {
              case "new_message": {
                // Wave 202 SW2 — `validated.message` is the Valibot `ParsedMessage`
                // (attachments/sender validated shape-only as Record<string,unknown>);
                // the cache stores `@/api/chat` `Message` (typed Attachment[]/User).
                // `Message` is assignable to `ParsedMessage`, so the two are comparable
                // → a single `as Message` is valid (collapsed from the prior, redundant
                // `as unknown as Message` double-cast; the `unknown` hop was never needed).
                // Do NOT delete the cast — `ParsedMessage` is NOT structurally `Message`.
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", validated.chat_id],
                  (old) => {
                    if (!old)
                      return {
                        items: [validated.message as Message],
                        has_more: false,
                        next_cursor: null,
                      }
                    if (old.items.some((m) => m.id === validated.message.id)) return old
                    // RZ-004: Sliding window prevents V8 heap exhaustion in long-lived sessions.
                    // Cap in-memory buffer at 200 messages — older messages are re-fetched
                    // via cursor-based pagination when the user scrolls up.
                    const MAX_BUFFERED_MESSAGES = 200
                    const appended = [...old.items, validated.message as Message]
                    const trimmed =
                      appended.length > MAX_BUFFERED_MESSAGES
                        ? appended.slice(appended.length - MAX_BUFFERED_MESSAGES)
                        : appended
                    return { ...old, items: trimmed }
                  }
                )
                queryClient.invalidateQueries({
                  queryKey: ["messages", validated.chat_id],
                  refetchType: "none",
                })
                queryClient.setQueryData<ChatsListResponse>(["chats"], (old) => {
                  if (!old) return old
                  return {
                    ...old,
                    items: old.items.map((chat) =>
                      chat.id === validated.chat_id
                        ? {
                            ...chat,
                            last_message: validated.message as Message,
                            unread_count: chat.unread_count + 1,
                          }
                        : chat
                    ),
                  }
                })
                queryClient.invalidateQueries({ queryKey: ["chats"], refetchType: "none" })
                onNewMessageRef.current?.(validated.message as Message, validated.chat_id)
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

              case "error":
                logError("[WebSocket] Server error:", validated)
                break
            }
          } catch (e) {
            logError("[WebSocket] Failed to parse message:", e)
          }
        }

        ws.onclose = (event) => {
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

  const sendTyping = useCallback((chatId: string) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return
    const key = `typing:${chatId}`
    const now = Date.now()
    if (now - (lastSentRef.current.get(key) ?? 0) < OUTGOING_RATE_LIMITS.typing!) return
    lastSentRef.current.set(key, now)
    try {
      // RZ-26-07: guard TOCTOU race — WS may close between readyState check and send
      wsRef.current.send(JSON.stringify({ type: "typing", chat_id: chatId }))
    } catch {
      /* WS closed between readyState check and send — safe to ignore */
    }
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
    getTypingUsersForChat,
    disconnect,
    reconnect: connect,
  }
}
