import { describe, it, expect } from "vitest"

import { parseWsMessage } from "./wsMessage"

const CHAT_ID = "11111111-1111-1111-1111-111111111111"
const USER_ID = "22222222-2222-2222-2222-222222222222"
const MSG_ID = "33333333-3333-3333-3333-333333333333"
const SENDER_ID = "44444444-4444-4444-4444-444444444444"
const READ_AT = "2026-05-30T14:32:00+00:00"
const MESSAGE_LIMIT = 32_768

function messageWithContent(content: string) {
  return {
    id: MSG_ID,
    chat_id: CHAT_ID,
    sender_id: SENDER_ID,
    content,
    created_at: "2026-05-30T14:30:00+00:00",
    read_status: false,
  }
}

describe("parseWsMessage — canonical message content boundary", () => {
  it.each([MESSAGE_LIMIT - 1, MESSAGE_LIMIT])(
    "accepts a new_message with %s Unicode code points",
    (size) => {
      const content = "😀".repeat(size)
      const frame = parseWsMessage(
        JSON.stringify({
          type: "new_message",
          chat_id: CHAT_ID,
          message: messageWithContent(content),
        })
      )

      expect(frame).not.toBeNull()
    }
  )

  it("rejects content above the canonical limit without truncating it", () => {
    const content = "x".repeat(MESSAGE_LIMIT + 1)

    expect(
      parseWsMessage(
        JSON.stringify({
          type: "new_message",
          chat_id: CHAT_ID,
          message: messageWithContent(content),
        })
      )
    ).toBeNull()
  })
})

describe("parseWsMessage — edited message content boundary", () => {
  it.each([MESSAGE_LIMIT - 1, MESSAGE_LIMIT])(
    "accepts message_edited content with %s Unicode code points",
    (size) => {
      const frame = parseWsMessage(
        JSON.stringify({
          type: "message_edited",
          chat_id: CHAT_ID,
          message_id: MSG_ID,
          content: "😀".repeat(size),
          edited_at: READ_AT,
        })
      )

      expect(frame).not.toBeNull()
      expect(frame?.type).toBe("message_edited")
    }
  )

  it("rejects message_edited content above the canonical limit", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "message_edited",
          chat_id: CHAT_ID,
          message_id: MSG_ID,
          content: "x".repeat(MESSAGE_LIMIT + 1),
          edited_at: READ_AT,
        })
      )
    ).toBeNull()
  })
})

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

  it("rejects a new_message with a malformed created_at timestamp", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        chat_id: CHAT_ID,
        message: { ...baseMessage, created_at: "not-a-timestamp" },
      })
    )

    expect(frame).toBeNull()
  })

  it("exposes a validated JetStream sequence from the ws-hub envelope", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        room: CHAT_ID,
        payload: { type: "new_message", chat_id: CHAT_ID, message: baseMessage },
        seq: 42,
        resume_token: "signed-resume-token-42",
        replayed: true,
      })
    ) as ReturnType<typeof parseWsMessage> & {
      stream_seq?: number
      replayed?: boolean
    }

    expect(frame).not.toBeNull()
    expect(frame?.stream_seq).toBe(42)
    expect(frame?.replayed).toBe(true)
  })

  it.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, "42"])(
    "rejects an unsafe JetStream sequence %s instead of silently ignoring it",
    (seq) => {
      expect(
        parseWsMessage(
          JSON.stringify({
            type: "new_message",
            room: CHAT_ID,
            payload: { type: "new_message", chat_id: CHAT_ID, message: baseMessage },
            seq,
            resume_token: "signed-resume-token",
          })
        )
      ).toBeNull()
    }
  )

  it("rejects a sequenced envelope whose authorized room disagrees with the payload chat", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "new_message",
          room: USER_ID,
          payload: { type: "new_message", chat_id: CHAT_ID, message: baseMessage },
          seq: 42,
          resume_token: "signed-resume-token-42",
        })
      )
    ).toBeNull()
  })

  it("rejects a flat frame that tries to forge a durable stream sequence", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "new_message",
          chat_id: CHAT_ID,
          message: baseMessage,
          seq: 42,
          resume_token: "signed-resume-token-42",
        })
      )
    ).toBeNull()
  })

  it("rejects replay metadata without its mandatory durable sequence", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "new_message",
          room: CHAT_ID,
          payload: { type: "new_message", chat_id: CHAT_ID, message: baseMessage },
          replayed: true,
        })
      )
    ).toBeNull()
  })

  it("rejects a durable sequence without its signed resume token", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "new_message",
          room: CHAT_ID,
          payload: { type: "new_message", chat_id: CHAT_ID, message: baseMessage },
          seq: 42,
        })
      )
    ).toBeNull()
  })

  it("rejects a resume token without its durable sequence", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "new_message",
          room: CHAT_ID,
          payload: { type: "new_message", chat_id: CHAT_ID, message: baseMessage },
          resume_token: "signed-resume-token",
        })
      )
    ).toBeNull()
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

  it("preserves the backend direct-route error message field", () => {
    const frame = parseWsMessage(JSON.stringify({ type: "error", message: "Access denied" }))
    expect(frame).toEqual({ type: "error", message: "Access denied" })
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

  it("accepts an enveloped replay checkpoint for a terminal poison event", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "replay_checkpoint",
        room: CHAT_ID,
        seq: 42,
        resume_token: "signed-resume-token-42",
        replayed: true,
        payload: { type: "replay_checkpoint", chat_id: CHAT_ID },
      })
    )

    expect(frame).toEqual({
      type: "replay_checkpoint",
      chat_id: CHAT_ID,
      stream_seq: 42,
      replayed: true,
      resume_token: "signed-resume-token-42",
    })
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

  it("rejects JSON primitives before envelope validation", () => {
    expect(parseWsMessage("42")).toBeNull()
  })

  it.each([
    ["replayed", "yes"],
    ["resume_token", ""],
  ])("rejects invalid %s stream metadata", (field, value) => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "read",
          room: CHAT_ID,
          seq: 42,
          resume_token: "signed-resume-token-42",
          replayed: true,
          payload: {
            type: "read",
            chat_id: CHAT_ID,
            user_id: USER_ID,
            read_at: READ_AT,
          },
          [field]: value,
        })
      )
    ).toBeNull()
  })

  it("rejects sequenced envelopes whose payload has no chat identity", () => {
    expect(
      parseWsMessage(
        JSON.stringify({
          type: "rate_limit_exceeded",
          room: CHAT_ID,
          seq: 42,
          resume_token: "signed-resume-token-42",
          payload: { type: "rate_limit_exceeded" },
        })
      )
    ).toBeNull()
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

describe("parseWsMessage — new_message with sender:null (Wave 205 SW9 live-new-message fix)", () => {
  // serialize_message (the outbox new_message broadcast) emits sender:null when
  // Message.sender is lazy="noload" (the handle_message_sent db.get path), plus
  // edited_at/deleted_at:null on a fresh message. Pre-fix, MessageSchema.sender was
  // v.optional(v.record(...)) which REJECTS null → the whole new_message frame was
  // dropped by parseWsMessage → new_message never rendered live. These guard the
  // schema staying nullable for those fields.
  const outboxMessage = {
    id: MSG_ID,
    chat_id: CHAT_ID,
    sender_id: SENDER_ID,
    content: "live message",
    created_at: "2026-05-30T22:48:00+00:00",
    read_status: false,
    read_at: null,
    edited_at: null,
    deleted_at: null,
    sender: null,
    sender_presence: null,
    attachments: [],
  }

  it("accepts a new_message whose message has sender:null (the exact dropped frame)", () => {
    const frame = parseWsMessage(
      JSON.stringify({ type: "new_message", chat_id: CHAT_ID, message: outboxMessage })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.id).toBe(MSG_ID)
      expect(frame.message.sender).toBeNull()
    }
  })

  it("still accepts a new_message whose message carries a sender record (enriched)", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        chat_id: CHAT_ID,
        message: { ...outboxMessage, sender: { id: SENDER_ID, full_name: "Bob" } },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.sender).toEqual({ id: SENDER_ID, full_name: "Bob" })
    }
  })

  it("unwraps an enveloped new_message with sender:null (W204 envelope + outbox path)", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        room: CHAT_ID,
        payload: { type: "new_message", chat_id: CHAT_ID, message: outboxMessage },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.sender).toBeNull()
    }
  })
})

describe("parseWsMessage — new_message with forwarded_from_name (Wave 211)", () => {
  const baseMessage = {
    id: MSG_ID,
    chat_id: CHAT_ID,
    sender_id: SENDER_ID,
    content: "forwarded message content",
    created_at: "2026-05-30T22:48:00+00:00",
    read_status: false,
    read_at: null,
  }

  it("preserves forwarded_from_name string when present on new_message", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        chat_id: CHAT_ID,
        message: { ...baseMessage, forwarded_from_name: "Alice Sender" },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.forwarded_from_name).toBe("Alice Sender")
    }
  })

  it("accepts forwarded_from_name: null when present on non-forwarded or reset message", () => {
    const frame = parseWsMessage(
      JSON.stringify({
        type: "new_message",
        chat_id: CHAT_ID,
        message: { ...baseMessage, forwarded_from_name: null },
      })
    )
    expect(frame).not.toBeNull()
    if (frame?.type === "new_message") {
      expect(frame.message.forwarded_from_name).toBeNull()
    }
  })
})
