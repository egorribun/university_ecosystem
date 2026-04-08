export type EventSortMode = "newest" | "popular" | "upcoming"

export type EventTabKey = "active" | "archive" | "my"

export type EventFormState = {
  title: string
  description: string
  title_en: string
  description_en: string
  event_type: string
  event_type_en: string
  location: string
  location_en: string
  speaker: string
  starts_at: string
  ends_at: string
}

export const initialEventFormState: EventFormState = {
  title: "",
  description: "",
  title_en: "",
  description_en: "",
  event_type: "",
  event_type_en: "",
  location: "",
  location_en: "",
  speaker: "",
  starts_at: "",
  ends_at: "",
}
