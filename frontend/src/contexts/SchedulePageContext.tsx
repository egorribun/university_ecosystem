import { createContext, useContext, useState, useRef, ReactNode, useCallback, useMemo } from "react"
import type { Lesson } from "@/components/schedule/scheduleUtils"

type DialogType = "details" | "edit" | "add" | null
type SnackbarSeverity = "success" | "error"

interface SchedulePageContextType {
  // Dialog State
  activeDialog: DialogType
  dialogSessionId: number
  isDialogSessionCurrent: (sessionId: number) => boolean
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
  const [dialogSessionId, setDialogSessionId] = useState(0)
  const dialogSessionRef = useRef(0)
  const [selectedLesson, setSelectedLesson] = useState<Lesson | null>(null)
  const [snackbarMessage, setSnackbarMessage] = useState<string | null>(null)
  const [snackbarSeverity, setSnackbarSeverity] = useState<SnackbarSeverity>("success")
  const [addDay, setAddDay] = useState<string | null>(null)

  const advanceDialogSession = useCallback(() => {
    const nextSessionId = dialogSessionRef.current + 1
    dialogSessionRef.current = nextSessionId
    setDialogSessionId(nextSessionId)
  }, [])

  const isDialogSessionCurrent = useCallback(
    (sessionId: number) => dialogSessionRef.current === sessionId,
    []
  )

  const openDialog = useCallback(
    (type: DialogType, lesson: Lesson | null = null) => {
      advanceDialogSession()
      setActiveDialog(type)
      if (lesson) setSelectedLesson(lesson)
      // If opening 'add', we might rely on addDay being set separately or passed here if we refactor further
    },
    [advanceDialogSession]
  )

  const closeDialog = useCallback(() => {
    advanceDialogSession()
    setActiveDialog(null)
    setSelectedLesson(null)
    setAddDay(null)
  }, [advanceDialogSession])

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
      dialogSessionId,
      isDialogSessionCurrent,
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
      dialogSessionId,
      isDialogSessionCurrent,
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
