import { useEffect, useRef, useCallback, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { Message, MessagesListResponse } from "../api/chat"

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
  user_id?: number
  user_name?: string
  message?: Message
  status?: boolean
  users?: number[]
  active?: boolean
  last_seen?: string | null
}

export interface UseChatWebSocketOptions {
  enabled?: boolean
  onNewMessage?: (message: Message, chatId: string) => void
  onTyping?: (chatId: string, userId: number, userName: string) => void
  onRead?: (chatId: string, messageId: string, userId: number) => void
  onOnlineStatus?: (userId: number, status: boolean) => void
  onPresenceUpdate?: (userId: number, active: boolean, lastSeen: string | null) => void
}

interface TypingUser {
  userId: number
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
  }, [])

  const connect = useCallback(() => {
    if (!enabledRef.current) return

    // Prevent duplicate connections (important for React StrictMode)
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      console.log("[WebSocket] Already connected or connecting, skipping")
      return
    }

    // Determine WebSocket URL
    // In dev mode, use same origin (Vite proxy will forward to backend)
    // In production, use same origin directly
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/chat`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log("[WebSocket] Connected")
        setIsConnected(true)
        // Reset reconnect attempts on successful connection
        reconnectAttemptRef.current = 0

        // Start ping interval
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }))
          }
        }, 30000) // Ping every 30 seconds
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
                // Invalidate chats to update unread counts
                queryClient.invalidateQueries({ queryKey: ["chats"] })
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

                  // Set new typing indicator with 3 second timeout
                  const timeout = setTimeout(() => {
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
              console.error("[WebSocket] Server error:", data)
              break
          }
        } catch (e) {
          console.error("[WebSocket] Failed to parse message:", e)
        }
      }

      ws.onclose = (event) => {
        console.log("[WebSocket] Disconnected:", event.code, event.reason)
        setIsConnected(false)
        cleanup()

        // Reconnect with exponential backoff unless it was a clean close or auth error
        if (event.code !== 1000 && event.code !== 4001 && event.code !== 4003) {
          // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000)
          reconnectAttemptRef.current += 1
          console.log(
            `[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current})`
          )
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        }
      }

      ws.onerror = (error) => {
        console.error("[WebSocket] Error:", error)
      }
    } catch (e) {
      console.error("[WebSocket] Failed to connect:", e)
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
      const users: { userId: number; userName: string }[] = []
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
