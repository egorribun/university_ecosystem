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
