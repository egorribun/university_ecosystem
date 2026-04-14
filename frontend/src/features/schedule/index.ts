/**
 * Schedule Feature
 *
 * Handles class schedule: week view, day view, list view, lesson details.
 */

// Hooks
export { useScheduleData } from "@/hooks/useScheduleData"
export { useDashboardSchedule } from "@/hooks/useDashboardSchedule"
export { useClassReminders } from "@/hooks/useClassReminders"

// Store
export { useScheduleUIStore, useWeekOffset, useViewMode } from "@/stores"

// Components
export { ScheduleDesktopTable } from "@/components/schedule/ScheduleDesktopTable"
export { ScheduleMobileView } from "@/components/schedule/ScheduleMobileView"
export { ScheduleListView } from "@/components/schedule/ScheduleListView"
export { LessonCard } from "@/components/schedule/LessonCard"
export { ScheduleSettingsPanel } from "@/components/schedule/ScheduleSettingsPanel"
