/**
 * Schedule Feature
 *
 * Handles class schedule: week view, day view, lesson details.
 */

// Re-export hooks from existing locations
export { useScheduleData } from "@/hooks/useScheduleData"
export { useDashboardSchedule } from "@/hooks/useDashboardSchedule"
export { useClassReminders } from "@/hooks/useClassReminders"

// Store
export { useScheduleUIStore, useWeekOffset, useViewMode } from "@/stores"

// Components will be added as migration progresses
// export { ScheduleCard } from './components/ScheduleCard'
