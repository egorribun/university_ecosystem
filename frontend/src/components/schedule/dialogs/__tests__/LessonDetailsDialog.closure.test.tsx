import type { ReactNode } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { mockUseSchedulePage } = vi.hoisted(() => ({ mockUseSchedulePage: vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "schedule:dialog.detailsFallback": "Details",
        "schedule:dialog.typeLabel": "Type",
        "schedule:dialog.timeLabel": "Time",
        "schedule:dialog.roomLabel": "Room",
        "schedule:dialog.teacherLabel": "Teacher",
        "common:buttons.edit": "Edit",
        "common:buttons.close": "Close",
      })[key] ?? key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@/contexts/SchedulePageContext", () => ({ useSchedulePage: mockUseSchedulePage }))
vi.mock("@/components/settings", () => ({
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
  DialogActions: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}))
vi.mock("@/components/ui", () => ({
  Badge: ({ children, leadingIcon }: { children: ReactNode; leadingIcon?: ReactNode }) => (
    <span>
      {leadingIcon}
      {children}
    </span>
  ),
  Button: ({
    children,
    id,
    onClick,
  }: {
    children: ReactNode
    id?: string
    onClick?: () => void
  }) => (
    <button type="button" id={id} onClick={onClick}>
      {children}
    </button>
  ),
}))

import { LessonDetailsDialog } from "../LessonDetailsDialog"

const baseLesson = {
  id: "lesson-1",
  subject: "Algorithms",
  lesson_type: "lecture",
  weekday: "monday",
  start_time: "09:00",
  end_time: "10:30",
  room: "A-101",
  teacher: "Ada Lovelace",
}

const createContext = (selectedLesson: unknown, activeDialog: string | null = "details") => ({
  activeDialog,
  closeDialog: vi.fn(),
  selectedLesson,
  openDialog: vi.fn(),
})

const renderDialog = (context: ReturnType<typeof createContext>, userRole?: string) => {
  mockUseSchedulePage.mockReturnValue(context)
  const getLessonTypeColor = vi.fn(() => "#123456")
  const getLessonTypeLabel = vi.fn((type?: string | null) => type ?? "Unknown")
  render(
    <LessonDetailsDialog
      userRole={userRole}
      getLessonTypeColor={getLessonTypeColor}
      getLessonTypeLabel={getLessonTypeLabel}
    />
  )
  return { getLessonTypeColor, getLessonTypeLabel }
}

beforeEach(() => {
  mockUseSchedulePage.mockReset()
})

describe("LessonDetailsDialog closure", () => {
  it("renders nothing without a selected lesson or when another dialog is active", () => {
    const emptyContext = createContext(null)
    renderDialog(emptyContext)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    const closedContext = createContext(baseLesson, "edit")
    renderDialog(closedContext)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders fallbacks for missing lesson fields and closes for regular users", () => {
    const context = createContext({
      ...baseLesson,
      subject: "",
      lesson_type: null,
      room: "",
      teacher: "",
    })
    const { getLessonTypeColor, getLessonTypeLabel } = renderDialog(context, "student")

    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Details" })).toBeInTheDocument()
    expect(screen.getAllByText("—")).toHaveLength(2)
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument()
    expect(getLessonTypeColor).toHaveBeenCalledWith(null)
    expect(getLessonTypeLabel).toHaveBeenCalledWith(null)

    fireEvent.click(screen.getByRole("button", { name: "Close" }))
    expect(context.closeDialog).toHaveBeenCalledOnce()
  })

  it("opens the edit dialog for an administrator and a teacher", () => {
    const adminContext = createContext(baseLesson)
    renderDialog(adminContext, "admin")
    fireEvent.click(screen.getByRole("button", { name: "Edit" }))
    expect(adminContext.openDialog).toHaveBeenCalledWith("edit", baseLesson)

    cleanup()
    const teacherContext = createContext(baseLesson)
    renderDialog(teacherContext, "teacher")
    fireEvent.click(screen.getByRole("button", { name: "Edit" }))
    expect(teacherContext.openDialog).toHaveBeenCalledWith("edit", baseLesson)
  })
})
