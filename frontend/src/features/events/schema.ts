import * as v from "valibot"

export const eventsSearchSchema = v.object({
  tab: v.optional(v.string()),
  q: v.optional(v.string()),
  dr: v.optional(v.string()),
  loc: v.optional(v.string()),
  sort: v.optional(v.string()),
  cat: v.optional(v.string()),
})

export type EventsSearch = v.InferOutput<typeof eventsSearchSchema>
