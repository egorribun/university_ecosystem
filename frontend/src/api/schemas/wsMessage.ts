/**
 * Runtime validation schemas for WebSocket messages.
 *
 * RZ-NEW-05 (audit 2026-03): Previously the WS onmessage handler cast
 * JSON.parse output directly to WebSocketMessage without any runtime check.
 * A malicious or malformed server frame could inject arbitrary data into
 * the TanStack Query cache (XSS vector, corrupted UI state).
 *
 * All incoming frames MUST pass safeParse before touching the query cache
 * or calling callbacks.
 */
import * as v from "valibot"

// ── Leaf field schemas ────────────────────────────────────────────────────────

const UuidString = v.pipe(v.string(), v.uuid())
const NonEmptyString = v.pipe(v.string(), v.minLength(1), v.maxLength(4096))

// Mirrors the backend Message schema — only the fields the FE actually uses.
const MessageSchema = v.object({
  id: UuidString,
  chat_id: UuidString,
  sender_id: UuidString,
  content: v.pipe(v.string(), v.maxLength(32_768)),
  created_at: NonEmptyString,
  read_status: v.boolean(),
  // Optional attachment list — just validate shape, not individual entries
  attachments: v.optional(v.array(v.looseObject({}))),
  sender: v.optional(v.looseObject({})),
})

export type ParsedMessage = v.InferOutput<typeof MessageSchema>

// ── Per-type variant schemas ──────────────────────────────────────────────────

const PongSchema = v.object({ type: v.literal("pong") })

const ErrorSchema = v.object({
  type: v.literal("error"),
  detail: v.optional(v.pipe(v.string(), v.maxLength(1024))),
})

const NewMessageSchema = v.object({
  type: v.literal("new_message"),
  chat_id: UuidString,
  message: MessageSchema,
})

const TypingSchema = v.object({
  type: v.literal("typing"),
  chat_id: UuidString,
  user_id: UuidString,
  user_name: v.pipe(v.string(), v.minLength(1), v.maxLength(256)),
})

const ReadSchema = v.object({
  type: v.literal("read"),
  chat_id: UuidString,
  message_id: UuidString,
  user_id: UuidString,
})

const OnlineSchema = v.object({
  type: v.literal("online"),
  user_id: UuidString,
  status: v.boolean(),
})

const PresenceSchema = v.object({
  type: v.literal("presence"),
  user_id: UuidString,
  active: v.boolean(),
  last_seen: v.nullable(v.string()),
})

// ── Discriminated union of all valid server→client frames ─────────────────────

export const WsServerMessageSchema = v.variant("type", [
  PongSchema,
  ErrorSchema,
  NewMessageSchema,
  TypingSchema,
  ReadSchema,
  OnlineSchema,
  PresenceSchema,
])

export type WsServerMessage = v.InferOutput<typeof WsServerMessageSchema>

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
  const result = v.safeParse(WsServerMessageSchema, parsed)
  return result.success ? result.output : null
}
