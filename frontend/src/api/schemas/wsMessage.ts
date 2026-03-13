/**
 * Runtime validation schemas for WebSocket messages.
 *
 * RZ-NEW-05 (audit 2026-03): Previously the WS onmessage handler cast
 * JSON.parse output directly to WebSocketMessage without any runtime check.
 * A malicious or malformed server frame could inject arbitrary data into
 * the TanStack Query cache (XSS vector, corrupted UI state).
 *
 * MOD-W5-02 (audit 2026-03-13): Migrated from valibot to Zod v4.
 * Zod v4's discriminatedUnion builds an O(1) lookup map by discriminant value
 * vs valibot variant's O(n) linear scan. Bundle: 7.9 KB vs ~12 KB.
 *
 * All incoming frames MUST pass parseWsMessage before touching the query cache
 * or calling callbacks.
 */
import { z } from "zod/v4"

// ── Leaf field schemas ────────────────────────────────────────────────────────

const UuidString = z.string().uuid()
const NonEmptyString = z.string().min(1).max(4096)

// Mirrors the backend Message schema — only the fields the FE actually uses.
const MessageSchema = z.object({
  id: UuidString,
  chat_id: UuidString,
  sender_id: UuidString,
  content: z.string().max(32_768),
  created_at: NonEmptyString,
  read_status: z.boolean(),
  // Optional attachment list — just validate shape, not individual entries
  attachments: z.array(z.record(z.string(), z.unknown())).optional(),
  sender: z.record(z.string(), z.unknown()).optional(),
})

export type ParsedMessage = z.infer<typeof MessageSchema>

// ── Per-type variant schemas ──────────────────────────────────────────────────

const PongSchema = z.object({ type: z.literal("pong") })

const ErrorSchema = z.object({
  type: z.literal("error"),
  detail: z.string().max(1024).optional(),
})

const NewMessageSchema = z.object({
  type: z.literal("new_message"),
  chat_id: UuidString,
  message: MessageSchema,
})

const TypingSchema = z.object({
  type: z.literal("typing"),
  chat_id: UuidString,
  user_id: UuidString,
  user_name: z.string().min(1).max(256),
})

const ReadSchema = z.object({
  type: z.literal("read"),
  chat_id: UuidString,
  message_id: UuidString,
  user_id: UuidString,
})

const OnlineSchema = z.object({
  type: z.literal("online"),
  user_id: UuidString,
  status: z.boolean(),
})

const PresenceSchema = z.object({
  type: z.literal("presence"),
  user_id: UuidString,
  active: z.boolean(),
  last_seen: z.string().nullable(),
})

// ── Discriminated union of all valid server→client frames ─────────────────────

export const WsServerMessageSchema = z.discriminatedUnion("type", [
  PongSchema,
  ErrorSchema,
  NewMessageSchema,
  TypingSchema,
  ReadSchema,
  OnlineSchema,
  PresenceSchema,
])

export type WsServerMessage = z.infer<typeof WsServerMessageSchema>

/**
 * Parse a raw WebSocket frame. Returns the typed message on success, or null
 * on any parse/validation failure (errors are already logged by the caller).
 */
export function parseWsMessage(raw: string): WsServerMessage | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  const result = WsServerMessageSchema.safeParse(parsed)
  return result.success ? result.data : null
}
