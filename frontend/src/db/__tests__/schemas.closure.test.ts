import { describe, expect, it } from "vitest"
import { messagesSchema } from "@/db/schemas/messages"
import { notesSchema } from "@/db/schemas/notes"
import { scheduleSchema } from "@/db/schemas/schedule"

describe("RxDB persisted schema contracts", () => {
  it("keeps the message document keys, bounds, required fields, and indexes stable", () => {
    expect(messagesSchema).toEqual({
      version: 0,
      primaryKey: "id",
      type: "object",
      properties: {
        id: { type: "string", maxLength: 100 },
        chat_id: { type: "string", maxLength: 100 },
        sender_id: { type: "string" },
        content: { type: "string" },
        created_at: { type: "string", maxLength: 50 },
        read_status: { type: "boolean" },
        read_at: { type: ["string", "null"] },
        edited_at: { type: ["string", "null"] },
        deleted_at: { type: ["string", "null"] },
        attachments: { type: "array" },
        reactions: { type: "array" },
        sync_status: { type: "string" },
      },
      required: ["id", "chat_id", "sender_id", "content", "created_at"],
      indexes: ["chat_id", "created_at", ["chat_id", "created_at"]],
    })
  })

  it("keeps the note document sync and timestamp constraints stable", () => {
    expect(notesSchema).toEqual({
      version: 0,
      primaryKey: "id",
      type: "object",
      properties: {
        id: { type: "string", maxLength: 100 },
        lesson_id: { type: "string", maxLength: 100 },
        text: { type: "string" },
        updated_at: { type: "number", minimum: 0, maximum: 10000000000000, multipleOf: 1 },
        is_synced: { type: "boolean" },
      },
      required: ["id", "lesson_id", "text", "updated_at"],
      indexes: ["lesson_id", "updated_at"],
    })
  })

  it("keeps the offline schedule identity, fields, and compound index stable", () => {
    expect(scheduleSchema).toEqual({
      version: 0,
      primaryKey: "id",
      type: "object",
      properties: {
        id: { type: "string", maxLength: 100 },
        group_id: { type: "string", maxLength: 100 },
        subject: { type: "string" },
        teacher: { type: "string" },
        room: { type: "string" },
        building: { type: "string" },
        weekday: { type: "string", maxLength: 20 },
        start_time: { type: "string" },
        end_time: { type: "string" },
        parity: { type: "string" },
        lesson_type: { type: "string" },
        updated_at: { type: "string" },
      },
      required: ["id", "group_id", "subject", "weekday", "start_time", "end_time"],
      indexes: ["group_id", "weekday", ["group_id", "weekday"]],
    })
  })
})
