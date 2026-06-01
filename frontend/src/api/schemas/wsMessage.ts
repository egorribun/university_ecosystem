/**
 * Runtime validation schemas for WebSocket messages.
 *
 * RZ-NEW-05 (audit 2026-03): Previously the WS onmessage handler cast
 * JSON.parse output directly to WebSocketMessage without any runtime check.
 * A malicious or malformed server frame could inject arbitrary data into
 * the TanStack Query cache (XSS vector, corrupted UI state).
 *
 * TD-21-03 (audit 2026-03-25 Wave 21): Migrated from Zod v4 to Valibot to
 * standardise on a single validation library across the frontend.  Valibot's
 * variant() uses a discriminator key for O(1) dispatch (same as Zod's
 * discriminatedUnion) and is fully tree-shakeable (~6 KB vs Zod's ~12 KB).
 *
 * All incoming frames MUST pass parseWsMessage before touching the query cache
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
  // Wave 203 SW5 — read-receipt timestamp. optional+nullable so a cached
  // new_message frame serialized before the column existed still parses.
  read_at: v.optional(v.nullable(v.string())),
  // Wave 205 SW9 — serialize_message (the new_message broadcast) emits edited_at/
  // deleted_at (null on a fresh message). Declared optional+nullable so the wire
  // value passes + threads into the cache; without these they'd be silently
  // stripped as unknown keys.
  edited_at: v.optional(v.nullable(v.string())),
  deleted_at: v.optional(v.nullable(v.string())),
  // Optional attachment list — just validate shape, not individual entries
  attachments: v.optional(v.array(v.record(v.string(), v.unknown()))),
  // Wave 205 SW9 — serialize_message emits sender:null when the Message.sender
  // relationship isn't eager-loaded (e.g. the outbox handle_message_sent path,
  // which db.get's the message with lazy="noload" sender). MUST be nullable, not
  // just optional: v.optional alone accepts `undefined` but REJECTS `null`, so a
  // new_message frame with "sender": null was dropped by parseWsMessage as invalid
  // (the whole reason new_message never rendered live until this fix).
  sender: v.optional(v.nullable(v.record(v.string(), v.unknown()))),
  // Wave 207 — reply/quote preview (the lean ReplyPreview the backend's
  // serialize_message embeds when this message replies to an earlier one).
  // optional+nullable per the W205 pattern: serialize_message emits "reply_to":
  // null on a non-reply frame (v.optional alone REJECTS null). The inner
  // sender_name + deleted_at are always-present keys with possibly-null values,
  // so they're v.nullable (not optional). content matches the message content cap.
  reply_to: v.optional(
    v.nullable(
      v.object({
        id: UuidString,
        sender_id: UuidString,
        sender_name: v.nullable(v.string()),
        content: v.pipe(v.string(), v.maxLength(32_768)),
        deleted_at: v.nullable(v.string()),
      })
    )
  ),
})

export type ParsedMessage = v.InferOutput<typeof MessageSchema>

// ── Per-type variant schemas ──────────────────────────────────────────────────

const PongSchema = v.object({ type: v.literal("pong") })

const ErrorSchema = v.object({
  type: v.literal("error"),
  // Wave 204 SW3 — ws-hub control frames carry a `code` (e.g. "message_too_large")
  // alongside detail (services/ws-hub client.go:158-162). Optional so plain
  // backend error frames without a code still validate.
  code: v.optional(v.pipe(v.string(), v.maxLength(256))),
  detail: v.optional(v.pipe(v.string(), v.maxLength(1024))),
})

// Wave 204 SW3 — ws-hub emits this directly to the client socket when a client
// exceeds its outgoing message rate (client.go:178). Acknowledged in the union
// so the hook stops logging it as an invalid frame; no handler action today.
const RateLimitExceededSchema = v.object({ type: v.literal("rate_limit_exceeded") })

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

// Wave 203 SW5 — chat-level read receipt. The reader (user_id) marked the whole
// chat read at read_at; the per-message message_id field is gone (the backend
// bulk-marks + broadcasts one chat-level frame — see mark_read / dispatcher).
const ReadSchema = v.object({
  type: v.literal("read"),
  chat_id: UuidString,
  user_id: UuidString,
  read_at: v.nullable(v.string()),
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

// Wave 205 — REST-initiated server→client broadcasts (the author edited / soft-deleted
// a message). The frame field is `message_id` (NOT `id`); the cache-update matches on
// it. No self-echo guard needed: the author already updated optimistically and the
// cache-update is idempotent (the echo just reconciles to the server value).
const MessageEditedSchema = v.object({
  type: v.literal("message_edited"),
  chat_id: UuidString,
  message_id: UuidString,
  content: v.pipe(v.string(), v.maxLength(32_768)),
  edited_at: NonEmptyString,
})

const MessageDeletedSchema = v.object({
  type: v.literal("message_deleted"),
  chat_id: UuidString,
  message_id: UuidString,
  deleted_at: NonEmptyString,
})

// Wave 206 — DELTA reaction frame (the W203 read-frame archetype): carries the
// actor (user_id) + the change, NOT the resolved aggregate (reacted_by_me is
// per-viewer, so it can never travel in a broadcast). applyReactionChangedFrame
// patches the matched message's emoji count ±1; the case-handler's self-echo
// guard skips the actor (already patched optimistically). A missed/duplicate
// delta self-heals on the next GET /messages (the persisted aggregate wins).
const ReactionChangedSchema = v.object({
  type: v.literal("reaction_changed"),
  chat_id: UuidString,
  message_id: UuidString,
  user_id: UuidString,
  emoji: NonEmptyString,
  action: v.picklist(["added", "removed"]),
})

// ── Discriminated union of all valid server→client frames ─────────────────────

export const WsServerMessageSchema = v.variant("type", [
  PongSchema,
  ErrorSchema,
  RateLimitExceededSchema,
  NewMessageSchema,
  TypingSchema,
  ReadSchema,
  OnlineSchema,
  PresenceSchema,
  MessageEditedSchema,
  MessageDeletedSchema,
  ReactionChangedSchema,
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
  // Wave 204 SW3 — ws-hub fans out the `{type, room, payload}` envelope
  // (services/ws-hub hub.go:323 marshals the whole Message struct), where
  // `payload` is the flat frame the backend published to chat.{chat_id}.
  // Unwrap it before validation so the existing discriminated-union schema
  // keeps validating the flat frames unchanged. ws-hub ALSO sends flat control
  // frames straight to the client socket ({type:"error",code}, {type:
  // "rate_limit_exceeded"}) — those have no `payload`, so we validate them
  // as-is. Key off `payload` PRESENCE (not the outer `type`) so ws-hub's
  // notifications-sub re-typing (hub.go:501) doesn't matter here.
  const frame =
    parsed !== null &&
    typeof parsed === "object" &&
    "payload" in parsed &&
    typeof (parsed as { payload?: unknown }).payload === "object" &&
    (parsed as { payload?: unknown }).payload !== null
      ? (parsed as { payload: unknown }).payload
      : parsed
  const result = v.safeParse(WsServerMessageSchema, frame)
  if (!result.success) {
    return null
  }
  return result.output
}
