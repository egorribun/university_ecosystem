import type { RxJsonSchema } from "rxdb"

export interface ScheduleDoc {
  id: string
  group_id: string
  subject: string
  teacher?: string
  room?: string
  building?: string
  weekday: string
  start_time: string
  end_time: string
  parity?: string
  lesson_type?: string
  updated_at?: string
}

export const scheduleSchema: RxJsonSchema<ScheduleDoc> = {
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
}
