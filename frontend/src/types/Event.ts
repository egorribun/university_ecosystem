import type { EventFileOut, EventOut, EventUpdate } from "@/api/generated"

export type Event = EventOut
export type EventFile = EventFileOut

export type EventEditDraft = EventUpdate & {
  id?: string
}
