import type { components } from "@/api/generated/schema"

export type Event = components["schemas"]["EventOut"]
export type EventFile = components["schemas"]["EventFileOut"]

export type EventEditDraft = {
  title: string
  title_en: string
  description: string
  description_en: string
  event_type: string
  event_type_en: string
  location: string
  location_en: string
  starts_at: string
  ends_at: string
  speaker: string
  image_url: string
}

