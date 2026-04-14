/**
 * Valibot schemas for event forms (create + edit).
 * Valibot only per CLAUDE.md — no Zod.
 */
import * as v from "valibot"

export const eventFormSchema = v.pipe(
  v.object({
    title: v.pipe(v.string(), v.minLength(1, "events:form.errors.titleRequired")),
    description: v.optional(v.string(), ""),
    title_en: v.optional(v.string(), ""),
    description_en: v.optional(v.string(), ""),
    event_type: v.optional(v.string(), ""),
    event_type_en: v.optional(v.string(), ""),
    location: v.optional(v.string(), ""),
    location_en: v.optional(v.string(), ""),
    speaker: v.optional(v.string(), ""),
    starts_at: v.pipe(v.string(), v.minLength(1, "events:form.errors.startRequired")),
    ends_at: v.pipe(v.string(), v.minLength(1, "events:form.errors.endRequired")),
  }),
  v.check(
    (data) => !data.starts_at || !data.ends_at || new Date(data.ends_at) > new Date(data.starts_at),
    "events:form.errors.endsBeforeStarts"
  )
)

export type EventFormSchema = v.InferOutput<typeof eventFormSchema>
