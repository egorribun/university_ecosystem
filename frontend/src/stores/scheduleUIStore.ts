/**
 * Schedule UI Store
 *
 * Manages schedule display preferences and UI state.
 * Persists view preferences to localStorage.
 */

import { create } from "zustand"
import { devtools, persist } from "zustand/middleware"

import type { ScheduleViewMode } from "./types"

interface ScheduleUIState {
  /** Current week offset from today (0 = current week) */
  weekOffset: number

  /** Active view mode */
  viewMode: ScheduleViewMode

  /** Hidden weekday indices (0 = Monday, 6 = Sunday) */
  hiddenWeekdays: number[]

  /** Whether to show past lessons */
  showPastLessons: boolean

  /** Whether to use compact card layout */
  compactMode: boolean

  /** Set week offset */
  setWeekOffset: (offset: number) => void

  /** Navigate to next week */
  nextWeek: () => void

  /** Navigate to previous week */
  previousWeek: () => void

  /** Reset to current week */
  goToCurrentWeek: () => void

  /** Set view mode */
  setViewMode: (mode: ScheduleViewMode) => void

  /** Toggle weekday visibility */
  toggleWeekday: (day: number) => void

  /** Set hidden weekdays */
  setHiddenWeekdays: (days: number[]) => void

  /** Toggle past lessons visibility */
  togglePastLessons: () => void

  /** Toggle compact mode */
  toggleCompactMode: () => void

  /** Reset all preferences to defaults */
  resetPreferences: () => void
}

const DEFAULT_STATE = {
  weekOffset: 0,
  viewMode: "week" as ScheduleViewMode,
  hiddenWeekdays: [] as number[],
  showPastLessons: true,
  compactMode: false,
}

export const useScheduleUIStore = create<ScheduleUIState>()(
  devtools(
    persist(
      (set) => ({
        ...DEFAULT_STATE,

        setWeekOffset: (offset) => set({ weekOffset: offset }, false, "setWeekOffset"),

        nextWeek: () => set((state) => ({ weekOffset: state.weekOffset + 1 }), false, "nextWeek"),

        previousWeek: () =>
          set((state) => ({ weekOffset: state.weekOffset - 1 }), false, "previousWeek"),

        goToCurrentWeek: () => set({ weekOffset: 0 }, false, "goToCurrentWeek"),

        setViewMode: (mode) => set({ viewMode: mode }, false, "setViewMode"),

        toggleWeekday: (day) =>
          set(
            (state) => ({
              hiddenWeekdays: state.hiddenWeekdays.includes(day)
                ? state.hiddenWeekdays.filter((d) => d !== day)
                : [...state.hiddenWeekdays, day],
            }),
            false,
            "toggleWeekday"
          ),

        setHiddenWeekdays: (days) => set({ hiddenWeekdays: [...days] }, false, "setHiddenWeekdays"),

        togglePastLessons: () =>
          set((state) => ({ showPastLessons: !state.showPastLessons }), false, "togglePastLessons"),

        toggleCompactMode: () =>
          set((state) => ({ compactMode: !state.compactMode }), false, "toggleCompactMode"),

        resetPreferences: () => set({ ...DEFAULT_STATE }, false, "resetPreferences"),
      }),
      {
        name: "schedule-ui-preferences",
        partialize: (state) => ({
          viewMode: state.viewMode,
          hiddenWeekdays: state.hiddenWeekdays,
          showPastLessons: state.showPastLessons,
          compactMode: state.compactMode,
        }),
      }
    ),
    { name: "ScheduleUIStore" }
  )
)

/** Selector hooks for optimized re-renders */
export const useWeekOffset = () => useScheduleUIStore((state) => state.weekOffset)

export const useViewMode = () => useScheduleUIStore((state) => state.viewMode)

export const useHiddenWeekdays = () => useScheduleUIStore((state) => state.hiddenWeekdays)

export const useScheduleDisplayPreferences = () =>
  useScheduleUIStore((state) => ({
    showPastLessons: state.showPastLessons,
    compactMode: state.compactMode,
  }))

export const useScheduleUIActions = () =>
  useScheduleUIStore((state) => ({
    setWeekOffset: state.setWeekOffset,
    nextWeek: state.nextWeek,
    previousWeek: state.previousWeek,
    goToCurrentWeek: state.goToCurrentWeek,
    setViewMode: state.setViewMode,
    toggleWeekday: state.toggleWeekday,
    setHiddenWeekdays: state.setHiddenWeekdays,
    togglePastLessons: state.togglePastLessons,
    toggleCompactMode: state.toggleCompactMode,
    resetPreferences: state.resetPreferences,
  }))
