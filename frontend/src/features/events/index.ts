/**
 * Events Feature
 *
 * Handles university events: listing, detail view, registration, editing.
 */

// Re-export components from existing locations
export { default as EventCard } from "@/components/EventCard"
export { default as EventDetail } from "@/components/EventDetail"
export { EventEditDialog } from "@/components/events/EventEditDialog"
export { EventQrDialog } from "@/components/events/EventQrDialog"

// Hooks
export { useDashboardEvents } from "@/hooks/useDashboardEvents"

// Types
export type { Event } from "@/types/Event"




