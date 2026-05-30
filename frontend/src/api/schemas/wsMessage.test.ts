import { describe, it, expect } from "vitest"

import { parseWsMessage } from "./wsMessage"

const CHAT_ID = "11111111-1111-1111-1111-111111111111"
const USER_ID = "22222222-2222-2222-2222-222222222222"
const MSG_ID = "33333333-3333-3333-3333-333333333333"
const SENDER_ID = "44444444-4444-4444-4444-444444444444"
const READ_AT = "2026-05-30T14:32:00+00:00"

describe("parseWsMessage — read frame (Wave 203 SW5 chat-level)", () => {
  it("accepts a chat-level read frame with read_at", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "read", chat_id: CHAT_ID, user_id: USER_ID, read_at: READ_AT })
    )
    expect(frame).not.toBeNull()
    expect(frame?.type).toBe("read")
    if (frame?.type === "read") {
      expect(frame.chat_id).toBe(CHAT_ID)
      expect(frame.user_id).toBe(USER_ID)
      expect(frame.read_at).toBe(READ_AT)
    }
  })

  it("accepts a read frame with read_at: null", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "read", chat_id: CHAT_ID, user_id: USER_ID, read_at: null })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "read") {
      expect(frame.read_at).toBeNull()
    }
  })

  it("rejects the legacy per-message read frame (message_id + no read_at)", () => {
    // read_at is now a required (nullable) key — the pre-W203 frame fails.
    const frame = parseWsMessage(
      JSON.stringify({ type: "read", chat_id: CHAT_ID, message_id: MSG_ID, user_id: USER_ID })
    )
    expect(frame).toBeNull()
  })
})

describe("parseWsMessage — new_message MessageSchema.read_at (Wave 203 SW5)", () => {
  const baseMessage = {
    id: MSG_ID,
    chat_id: CHAT_ID,
    sender_id: SENDER_ID,
    content: "hi",
    created_at: "2026-05-30T14:30:00+00:00",
    read_status: true,
  }

  it("accepts a new_message whose message carries read_at", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        chat_id: CHAT_ID,
        message: { ...baseMessage, read_at: READ_AT },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.read_at).toBe(READ_AT)
    }
  })

  it("accepts a new_message whose message OMITS read_at (optional — backward compat)", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "new_message", chat_id: CHAT_ID, message: baseMessage })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.read_at).toBeUndefined()
    }
  })

  it("accepts a new_message whose message read_at is null", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        chat_id: CHAT_ID,
        message: { ...baseMessage, read_at: null },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.read_at).toBeNull()
    }
  })
})

describe("parseWsMessage — Wave 204 SW3 ws-hub envelope unwrap + control frames", () => {
  const message = {
    id: MSG_ID,
    chat_id: CHAT_ID,
    sender_id: SENDER_ID,
    content: "hi",
    created_at: "2026-05-30T14:30:00+00:00",
    read_status: false,
    read_at: null,
  }

  it("unwraps an enveloped new_message frame to the inner flat frame", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        room: CHAT_ID,
        payload: { type: "new_message", chat_id: CHAT_ID, message },
        from: "backend",
      })
    )
    expect(frame).not.toBeNull()
    expect(frame?.type).toBe("new_message")
    if (frame?.type === "new_message") {
      expect(frame.chat_id).toBe(CHAT_ID)
      expect(frame.message.id).toBe(MSG_ID)
    }
  })

  it("unwraps an enveloped read frame to the inner flat frame", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "read",
        room: CHAT_ID,
        payload: { type: "read", chat_id: CHAT_ID, user_id: USER_ID, read_at: READ_AT },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "read") {
      expect(frame.user_id).toBe(USER_ID)
      expect(frame.read_at).toBe(READ_AT)
    }
  })

  it("still accepts a flat (non-enveloped) frame — backward compat", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "read", chat_id: CHAT_ID, user_id: USER_ID, read_at: null })
    )
    expect(frame?.type).toBe("read")
  })

  it("accepts a flat ws-hub error control frame with code", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "error",
        code: "message_too_large",
        detail: "message exceeds 60 KB limit",
      })
    )
    expect(frame).not.toBeNull()
    expect(frame?.type).toBe("error")
  })

  it("accepts a flat rate_limit_exceeded control frame", () => {
    const frame = parseWsMessage(JSON.stringify({ type: "rate_limit_exceeded" }))
    expect(frame).not.toBeNull()
    expect(frame?.type).toBe("rate_limit_exceeded")
  })

  it("returns null for an enveloped frame whose inner payload is malformed", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "new_message", room: CHAT_ID, payload: { type: "new_message" } })
    )
    expect(frame).toBeNull()
  })

  it("returns null for a non-object payload envelope (validates outer, which fails)", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "new_message", room: CHAT_ID, payload: "not-an-object" })
    )
    expect(frame).toBeNull()
  })

  it("returns null on JSON garbage", () => {
    expect(parseWsMessage("{not json")).toBeNull()
  })
})

describe("parseWsMessage — message_edited / message_deleted (Wave 205)", () => {
  const EDITED_AT = "2026-05-30T15:00:00+00:00"
  const DELETED_AT = "2026-05-30T15:01:00+00:00"

  it("accepts a message_edited frame (message_id, content, edited_at)", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "message_edited",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        content: "edited text",
        edited_at: EDITED_AT,
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "message_edited") {
      expect(frame.message_id).toBe(MSG_ID)
      expect(frame.content).toBe("edited text")
      expect(frame.edited_at).toBe(EDITED_AT)
    }
  })

  it("rejects a message_edited frame missing content", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "message_edited",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        edited_at: EDITED_AT,
      })
    )
    expect(frame).toBeNull()
  })

  it("accepts a message_deleted frame (message_id, deleted_at)", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "message_deleted",
        chat_id: CHAT_ID,
        message_id: MSG_ID,
        deleted_at: DELETED_AT,
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "message_deleted") {
      expect(frame.message_id).toBe(MSG_ID)
      expect(frame.deleted_at).toBe(DELETED_AT)
    }
  })

  it("rejects a message_deleted frame missing deleted_at", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "message_deleted", chat_id: CHAT_ID, message_id: MSG_ID })
    )
    expect(frame).toBeNull()
  })

  it("unwraps an enveloped message_edited frame (W204 envelope)", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "message_edited",
        room: CHAT_ID,
        payload: {
          type: "message_edited",
          chat_id: CHAT_ID,
          message_id: MSG_ID,
          content: "via envelope",
          edited_at: EDITED_AT,
        },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "message_edited") {
      expect(frame.message_id).toBe(MSG_ID)
      expect(frame.content).toBe("via envelope")
    }
  })
})
