import { createContext, useContext, useState, ReactNode, useCallback, useMemo } from "react"
import type { Lesson } from "@/components/schedule/scheduleUtils"

type DialogType = "details" | "edit" | "add" | null
type SnackbarSeverity = "success" | "error"

/** Stable view data shared across schedule components (FIX-68-07: reduces prop drilling). */
export interface ScheduleViewData {
  schedule: Lesson[]
  weekdayBackend: readonly string[]
  weekdayLabels: readonly string[]
  hasToday: boolean
  todayIdx: number
  rawSchedule: Lesson[]
  refresh: () => void
  user: { role?: string; group_id?: string | null } | null
  conflictedIds: Set<string>
  isOnline: boolean
  onDeleteLesson: (id: string) => void
  getLessonTypeColor: (type?: string | null) => string
  currentLesson: Lesson | null
  notesMap: Map<string, boolean>
}

interface SchedulePageContextType {
  // Dialog State
  activeDialog: DialogType
  selectedLesson: Lesson | null
  openDialog: (type: DialogType, lesson?: Lesson | null) => void
  closeDialog: () => void

  // Optimistic UI / Snackbars
  snackbarMessage: string | null
  snackbarSeverity: SnackbarSeverity
  showSnackbar: (msg: string, severity?: SnackbarSeverity) => void
  hideSnackbar: () => void

  // Shared State
  addDay: string | null
  setAddDay: (day: string | null) => void
}

const SchedulePageContext = createContext<SchedulePageContextType | null>(null)

export function SchedulePageProvider({ children }: { children: ReactNode }) {
  const [activeDialog, setActiveDialog] = useState<DialogType>(null)
  const [selectedLesson, setSelectedLesson] = useState<Lesson | null>(null)
  const [snackbarMessage, setSnackbarMessage] = useState<string | null>(null)
  const [snackbarSeverity, setSnackbarSeverity] = useState<SnackbarSeverity>("success")
  const [addDay, setAddDay] = useState<string | null>(null)

  const openDialog = useCallback((type: DialogType, lesson: Lesson | null = null) => {
    setActiveDialog(type)
    if (lesson) setSelectedLesson(lesson)
    // If opening 'add', we might rely on addDay being set separately or passed here if we refactor further
  }, [])

  const closeDialog = useCallback(() => {
    setActiveDialog(null)
    setSelectedLesson(null)
    setAddDay(null)
  }, [])

  const showSnackbar = useCallback((msg: string, severity: SnackbarSeverity = "success") => {
    setSnackbarMessage(msg)
    setSnackbarSeverity(severity)
  }, [])

  const hideSnackbar = useCallback(() => {
    setSnackbarMessage(null)
  }, [])

  const value = useMemo(
    () => ({
      activeDialog,
      selectedLesson,
      openDialog,
      closeDialog,
      snackbarMessage,
      snackbarSeverity,
      showSnackbar,
      hideSnackbar,
      addDay,
      setAddDay,
    }),
    [
      activeDialog,
      selectedLesson,
      openDialog,
      closeDialog,
      snackbarMessage,
      snackbarSeverity,
      showSnackbar,
      hideSnackbar,
      addDay,
      setAddDay,
    ]
  )

  return <SchedulePageContext.Provider value={value}>{children}</SchedulePageContext.Provider>
}

export function useSchedulePage() {
  const context = useContext(SchedulePageContext)
  if (!context) {
    throw new Error("useSchedulePage must be used within a SchedulePageProvider")
  }
  return context
}

