/**
 * features/activity barrel — Wave 112 SW2.
 *
 * Re-exports the orchestrator + the typed contracts so the rest of the app
 * imports from a single stable surface (`@/features/activity`) instead of
 * reaching into internals.
 */
export { ActivityFeature } from "./ActivityFeature"
export type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
  PeriodKey,
  TimelineEntry,
} from "./types"
export { PERIOD_VALUES, isPeriodKey } from "./types"
