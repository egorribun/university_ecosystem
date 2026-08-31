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

/** Canonical backend message-content limit (Unicode code points). */
export const CHAT_MESSAGE_MAX_LENGTH = 32_768

const UuidString = v.pipe(v.string(), v.uuid())
const NonEmptyString = v.pipe(v.string(), v.minLength(1), v.maxLength(4096))
const IsoTimestampString = v.pipe(NonEmptyString, v.isoTimestamp())
// JavaScript's String#length counts UTF-16 code units, while the backend and
// database contract count Unicode code points.  Use an explicit code-point
// check so astral characters do not consume two message slots in the browser.
const MessageContent = v.pipe(
  v.string(),
  v.check(
    (value) => [...value].length <= CHAT_MESSAGE_MAX_LENGTH,
    `Message content must be at most ${CHAT_MESSAGE_MAX_LENGTH} Unicode code points`
  )
)

// Mirrors the backend Message schema — only the fields the FE actually uses.
const MessageSchema = v.object({
  id: UuidString,
  chat_id: UuidString,
  sender_id: UuidString,
  content: MessageContent,
  created_at: IsoTimestampString,
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
  // Wave 211 — forwarded message attribution name. optional+nullable so real-time
  // new_message frames for forwarded messages preserve forwarded_from_name upon
  // parsing without being stripped.
  forwarded_from_name: v.optional(v.nullable(v.string())),
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
        content: MessageContent,
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
  room: v.optional(v.pipe(v.string(), v.minLength(1), v.maxLength(512))),
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

// Legacy backend admin presence response.  Keep it in the current catalog so
// parseWsMessage does not drop a valid frame emitted by MessageDispatcher.
const OnlineListSchema = v.object({
  type: v.literal("online_list"),
  users: v.array(UuidString),
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
  content: MessageContent,
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

// A terminal replay checkpoint lets ws-hub advance the durable browser cursor
// past a permanently malformed JetStream event without exposing its payload.
const ReplayCheckpointSchema = v.object({
  type: v.literal("replay_checkpoint"),
  chat_id: UuidString,
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
  OnlineListSchema,
  PresenceSchema,
  MessageEditedSchema,
  MessageDeletedSchema,
  ReactionChangedSchema,
  ReplayCheckpointSchema,
])

type WsServerMessagePayload = v.InferOutput<typeof WsServerMessageSchema>

export type WsServerMessage = WsServerMessagePayload & {
  stream_seq?: number
  replayed?: boolean
  resume_token?: string
}

const StreamSequenceSchema = v.pipe(v.number(), v.safeInteger(), v.minValue(1))

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
  const parsedRecord =
    parsed !== null && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null
  const hasEnvelopePayload =
    parsedRecord !== null &&
    "payload" in parsedRecord &&
    typeof parsedRecord.payload === "object" &&
    parsedRecord.payload !== null
  const frame = hasEnvelopePayload ? parsedRecord.payload : parsed
  const result = v.safeParse(WsServerMessageSchema, frame)
  if (!result.success) {
    return null
  }

  let streamMetadata: { sequence: number; source: Record<string, unknown> } | undefined
  let replayed: boolean | undefined
  let resumeToken: string | undefined
  if (parsedRecord && "seq" in parsedRecord) {
    const sequenceResult = v.safeParse(StreamSequenceSchema, parsedRecord.seq)
    if (!sequenceResult.success) return null
    streamMetadata = { sequence: sequenceResult.output, source: parsedRecord }
  }
  if (parsedRecord && "replayed" in parsedRecord) {
    const replayedResult = v.safeParse(v.boolean(), parsedRecord.replayed)
    if (!replayedResult.success) return null
    replayed = replayedResult.output
  }
  if (parsedRecord && "resume_token" in parsedRecord) {
    const tokenResult = v.safeParse(
      v.pipe(v.string(), v.minLength(1), v.maxLength(4096)),
      parsedRecord.resume_token
    )
    if (!tokenResult.success) return null
    resumeToken = tokenResult.output
  }

  if (streamMetadata !== undefined && !hasEnvelopePayload) return null
  if (replayed !== undefined && streamMetadata === undefined) return null
  if ((streamMetadata === undefined) !== (resumeToken === undefined)) return null

  if (streamMetadata !== undefined) {
    if (!("chat_id" in result.output)) return null
    // The guard above already rejects sequenced flat frames, so a sequenced
    // result is necessarily an envelope and its room must bind to chat_id.
    const roomResult = v.safeParse(UuidString, streamMetadata.source.room)
    if (!roomResult.success || roomResult.output !== result.output.chat_id) return null
  }

  return {
    ...result.output,
    ...(streamMetadata === undefined ? {} : { stream_seq: streamMetadata.sequence }),
    ...(replayed === undefined ? {} : { replayed }),
    ...(resumeToken === undefined ? {} : { resume_token: resumeToken }),
  }
}
