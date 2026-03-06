import { useEffect, useRef, useCallback, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { Message, MessagesListResponse, ChatsListResponse } from "@/api/chat"
// Auth token storage handled natively via cookies
import { logDebug, logError } from "@/app/logger"

// Reconnection configuration
const RECONNECT_BASE_DELAY_MS = 1000 // 1 second
const RECONNECT_MAX_DELAY_MS = 30000 // 30 seconds
const RECONNECT_JITTER_FACTOR = 0.1 // ±10% jitter
const PING_INTERVAL_MS = 30000 // Heartbeat every 30 seconds

/**
 * Calculate reconnection delay with exponential backoff and jitter.
 * Jitter prevents "thundering herd" when many clients reconnect simultaneously.
 */
function calculateReconnectDelay(attempt: number): number {
  // Exponential backoff: baseDelay * 2^attempt, capped at maxDelay
  const expDelay = Math.min(RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt), RECONNECT_MAX_DELAY_MS)
  // Add jitter: random value in range [1-jitter, 1+jitter]
  const jitter = 1 + (Math.random() * 2 - 1) * RECONNECT_JITTER_FACTOR
  return Math.round(expDelay * jitter)
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
}

export interface UseChatWebSocketOptions {
  enabled?: boolean
  onNewMessage?: (message: Message, chatId: string) => void
  onTyping?: (chatId: string, userId: string, userName: string) => void
  onRead?: (chatId: string, messageId: string, userId: string) => void
  onOnlineStatus?: (userId: string, status: boolean) => void
  onPresenceUpdate?: (userId: string, active: boolean, lastSeen: string | null) => void
}

interface TypingUser {
  userId: string
  userName: string
  timeout: ReturnType<typeof setTimeout>
}

export function useChatWebSocket({
  enabled = true,
  onNewMessage,
  onTyping,
  onRead,
  onOnlineStatus,
  onPresenceUpdate,
}: UseChatWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectAttemptRef = useRef(0)
  const [isConnected, setIsConnected] = useState(false)
  const [typingUsers, setTypingUsers] = useState<Map<string, TypingUser>>(new Map())
  const queryClient = useQueryClient()

  // Store callbacks in refs to avoid recreating connect on every render
  const onNewMessageRef = useRef(onNewMessage)
  const onTypingRef = useRef(onTyping)
  const onReadRef = useRef(onRead)
  const onOnlineStatusRef = useRef(onOnlineStatus)
  const onPresenceUpdateRef = useRef(onPresenceUpdate)
  const enabledRef = useRef(enabled)

  // Keep refs updated
  useEffect(() => {
    onNewMessageRef.current = onNewMessage
    onTypingRef.current = onTyping
    onReadRef.current = onRead
    onOnlineStatusRef.current = onOnlineStatus
    onPresenceUpdateRef.current = onPresenceUpdate
    enabledRef.current = enabled
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
    if (!enabledRef.current) return

    // Prevent duplicate connections (important for React StrictMode)
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      if (import.meta.env.DEV) logDebug("[WebSocket] Already connected or connecting, skipping")
      return
    }

    // Determine WebSocket URL
    // In dev mode, use same origin (Vite proxy will forward to backend)
    // In production, use same origin directly
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/chat`

    try {
      // Authentication is handled via HttpOnly cookie (access_token_v2).
      // The browser sends it automatically — no token in Sec-WebSocket-Protocol needed.
      // Passing a token as subprotocol logs it in every Nginx access line (SECURITY RISK).
      // Backend fallback: websocket.py:809 reads access_token_v2 cookie directly.
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (import.meta.env.DEV) logDebug("[WebSocket] Connected")
        setIsConnected(true)
        // Reset reconnect attempts on successful connection
        reconnectAttemptRef.current = 0

        // Start ping interval (heartbeat)
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }))
          }
        }, PING_INTERVAL_MS)
      }

      ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data)

          switch (data.type) {
            case "new_message":
              if (data.message && data.chat_id) {
                // Update messages cache
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", data.chat_id],
                  (old) => {
                    if (!old) return { items: [data.message!], has_more: false, next_cursor: null }
                    // Check for duplicate
                    if (old.items.some((m) => m.id === data.message!.id)) return old
                    return { ...old, items: [...old.items, data.message!] }
                  }
                )
                // DEBT-04 (audit 2026-03-06): Update chats cache surgically instead of
                // invalidating the full list (which triggers a network round-trip per message).
                // unread_count is incremented unconditionally; it resets via the read-receipt
                // pathway (sendRead → backend → WS "read" event → setQueryData).
                queryClient.setQueryData<ChatsListResponse>(["chats"], (old) => {
                  if (!old) return old
                  return {
                    ...old,
                    items: old.items.map((chat) =>
                      chat.id === data.chat_id
                        ? {
                            ...chat,
                            last_message: data.message,
                            unread_count: chat.unread_count + 1,
                          }
                        : chat
                    ),
                  }
                })
                onNewMessageRef.current?.(data.message, data.chat_id)
              }
              break

            case "typing":
              if (data.chat_id && data.user_id && data.user_name) {
                setTypingUsers((prev) => {
                  const newMap = new Map(prev)
                  const key = `${data.chat_id}:${data.user_id}`

                  // Clear previous timeout
                  const existing = newMap.get(key)
                  if (existing) clearTimeout(existing.timeout)

                  // Set new typing indicator with 3 second timeout.
                  // Guard mountedRef.current so the setState after the timeout
                  // does not fire on an already-unmounted component.
                  const timeout = setTimeout(() => {
                    if (!mountedRef.current) return
                    setTypingUsers((p) => {
                      const updated = new Map(p)
                      updated.delete(key)
                      return updated
                    })
                  }, 3000)

                  newMap.set(key, {
                    userId: data.user_id!,
                    userName: data.user_name!,
                    timeout,
                  })
                  return newMap
                })
                onTypingRef.current?.(data.chat_id, data.user_id, data.user_name)
              }
              break

            case "read":
              if (data.chat_id && data.message_id && data.user_id) {
                // Update message read status in cache
                queryClient.setQueryData<MessagesListResponse>(
                  ["messages", data.chat_id],
                  (old) => {
                    if (!old) return old
                    return {
                      ...old,
                      items: old.items.map((m) =>
                        m.id === data.message_id ? { ...m, read_status: true } : m
                      ),
                    }
                  }
                )
                onReadRef.current?.(data.chat_id, data.message_id, data.user_id)
              }
              break

            case "online":
              if (data.user_id !== undefined && data.status !== undefined) {
                onOnlineStatusRef.current?.(data.user_id, data.status)
              }
              break

            case "presence":
              if (data.user_id !== undefined && data.active !== undefined) {
                const lastSeen = data.last_seen ?? null
                onPresenceUpdateRef.current?.(data.user_id, data.active, lastSeen)
                // Maintain backward compatibility with online status updates
                onOnlineStatusRef.current?.(data.user_id, data.active)
              }
              break

            case "pong":
              // Heartbeat response, nothing to do
              break

            case "error":
              logError("[WebSocket] Server error:", data)
              break
          }
        } catch (e) {
          logError("[WebSocket] Failed to parse message:", e)
        }
      }

      ws.onclose = (event) => {
        if (import.meta.env.DEV) logDebug("[WebSocket] Disconnected:", event.code, event.reason)
        setIsConnected(false)
        cleanup()

        // Reconnect with exponential backoff + jitter unless it was a clean close or auth error
        // Error codes: 1000 = normal close, 4001 = unauthorized, 4003 = forbidden
        if (event.code !== 1000 && event.code !== 4001 && event.code !== 4003) {
          const delay = calculateReconnectDelay(reconnectAttemptRef.current)
          reconnectAttemptRef.current += 1
          if (import.meta.env.DEV) {
            logDebug(
              `[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current})`
            )
          }
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        }
      }

      ws.onerror = (error) => {
        logError("[WebSocket] Error:", error)
      }
    } catch (e) {
      logError("[WebSocket] Failed to connect:", e)
    }
  }, [cleanup, queryClient])

  const disconnect = useCallback(() => {
    cleanup()
    if (wsRef.current) {
      wsRef.current.close(1000)
      wsRef.current = null
    }
    setIsConnected(false)
  }, [cleanup])

  // Store connect/disconnect in refs for stable effect
  const connectRef = useRef(connect)
  const disconnectRef = useRef(disconnect)
  useEffect(() => {
    connectRef.current = connect
    disconnectRef.current = disconnect
  })

  // Connect on mount, disconnect on unmount
  // Use mounted flag to handle React StrictMode double mount/unmount
  const mountedRef = useRef(false)
  useEffect(() => {
    // Cancel any pending disconnect from previous unmount
    mountedRef.current = true
    connectRef.current()

    return () => {
      mountedRef.current = false
      // Delay disconnect slightly to allow StrictMode remount to cancel it
      setTimeout(() => {
        if (!mountedRef.current) {
          disconnectRef.current()
        }
      }, 100)
    }
  }, [])

  // Send typing indicator
  const sendTyping = useCallback((chatId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "typing", chat_id: chatId }))
    }
  }, [])

  // Send read receipt
  const sendRead = useCallback((chatId: string, messageId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "read", chat_id: chatId, message_id: messageId }))
    }
  }, [])

  // Get typing users for a specific chat
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
