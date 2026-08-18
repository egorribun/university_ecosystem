/**
 * Events Feature — barrel exports
 *
 * Architecture mirrors features/news/:
 * - EventsFeature: central orchestrator
 * - categories: event type → color mapping
 * - types: local types and form state
 */

// Feature orchestrator
export { EventsFeature } from "./EventsFeature"

// Category system (renamed to avoid collision with news/categories in features/index.ts barrel)
export {
  inferEventCategory,
  getCategoryMeta as getEventCategoryMeta,
  ALL_EVENT_CATEGORIES,
} from "./categories"
export type { EventCategory } from "./categories"

// Types
export type { EventSortMode, EventTabKey, EventFormState } from "./types"

// Re-export legacy components still in use
export { default as EventCard } from "@/components/events/EventCard/EventCard"
export { EventEditDialog } from "@/components/events/EventEditDialog"
export { EventQrDialog } from "@/components/events/EventQrDialog"
export { useDashboardEvents } from "@/hooks/useDashboardEvents"
export type { Event } from "@/types/Event"
