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
