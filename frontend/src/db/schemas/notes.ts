import type { RxJsonSchema } from "rxdb"

export interface NoteDoc {
  id: string
  lesson_id: string
  text: string
  updated_at: number
  is_synced?: boolean
}

export const notesSchema: RxJsonSchema<NoteDoc> = {
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
}
