import { useEffect, type ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import api from "@/api/client"
import * as logger from "@/app/logger"
import {
  createRollbackUpdater,
  EditLessonDialog,
} from "@/components/schedule/dialogs/EditLessonDialog"
import { LessonDetailsDialog } from "@/components/schedule/dialogs/LessonDetailsDialog"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { Lesson } from "@/components/schedule/scheduleUtils"

const SAMPLE: Lesson = {
  id: "l1",
  weekday: "monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  subject: "Линейная алгебра",
  teacher: "Иванова Е.А.",
  room: "ГУК-305",
  lesson_type: "lecture",
  group_id: "g1",
}

const baseProps = {
  schedule: [SAMPLE],
  lessonTypeOptions: [
    { value: "lecture", label: "Лекция" },
    { value: "practice", label: "Практика" },
  ],
  toBackendLessonType: (v?: string | null) => v ?? "lecture",
  applyScheduleUpdate: vi.fn(),
  refresh: vi.fn(),
}

function OpenEditHarness({ children }: { children: ReactNode }) {
  const { openDialog } = useSchedulePage()
  useEffect(() => {
    openDialog("edit", SAMPLE)
  }, [openDialog])
  return <>{children}</>
}

function OpenDetailsHarness({ lesson, children }: { lesson: Lesson; children: ReactNode }) {
  const { openDialog } = useSchedulePage()
  useEffect(() => {
    openDialog("details", lesson)
  }, [openDialog, lesson])
  return <>{children}</>
}

function renderDialog(props = baseProps) {
  return render(
    <SchedulePageProvider>
      <OpenEditHarness>
        <EditLessonDialog {...props} />
      </OpenEditHarness>
    </SchedulePageProvider>
  )
}

function SnackbarProbe() {
  const { snackbarMessage, snackbarSeverity } = useSchedulePage()
  return snackbarMessage ? (
    <div role={snackbarSeverity === "error" ? "alert" : "status"}>{snackbarMessage}</div>
  ) : null
}

describe("EditLessonDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("renders the edit form seeded from the selected lesson when open", () => {
    renderDialog()
    expect(screen.getByText("schedule:dialog.editTitle")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Линейная алгебра")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Иванова Е.А.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeInTheDocument()
  })

  it("closes the dialog when cancel is clicked", async () => {
    const user = userEvent.setup()
    renderDialog()
    expect(screen.getByText("schedule:dialog.editTitle")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.queryByText("schedule:dialog.editTitle")).not.toBeInTheDocument()
  })

  it("names the edit dialog from its visible title", () => {
    renderDialog()

    expect(screen.getByRole("dialog", { name: "schedule:dialog.editTitle" })).toBeInTheDocument()
  })

  it("leaves the schedule unchanged when no previous lesson was captured", () => {
    const optimisticLesson = { ...SAMPLE, subject: "Updated algebra" }
    const currentSchedule = [optimisticLesson]
    const rollback = createRollbackUpdater(optimisticLesson, undefined)

    expect(rollback(currentSchedule)).toBe(currentSchedule)
  })

  it("reports a failed save without an optimistic cache result", async () => {
    const user = userEvent.setup()
    const applyScheduleUpdate = vi.fn(() => undefined)
    const saveError = new Error("No active schedule")
    const patchSpy = vi.spyOn(api, "patch").mockRejectedValueOnce(saveError)
    const logErrorSpy = vi.spyOn(logger, "logError").mockImplementation(() => undefined)

    render(
      <SchedulePageProvider>
        <OpenEditHarness>
          <EditLessonDialog {...baseProps} applyScheduleUpdate={applyScheduleUpdate} />
          <SnackbarProbe />
        </OpenEditHarness>
      </SchedulePageProvider>
    )

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("schedule:snackbar.updateError")
    expect(patchSpy).toHaveBeenCalledWith(
      "/schedule/l1",
      expect.objectContaining({ ...SAMPLE, lesson_type: "lecture" })
    )
    expect(applyScheduleUpdate).toHaveBeenCalledTimes(1)
    expect(applyScheduleUpdate).toHaveBeenCalledWith(expect.any(Function))
    expect(logErrorSpy).toHaveBeenCalledWith("Failed to update lesson", saveError)
  })

  it.each([
    ["Линейная алгебра", "Линейная алгебра"],
    ["", "schedule:dialog.detailsFallback"],
  ])("names lesson details for subject %j", (subject, name) => {
    const lesson = { ...SAMPLE, subject }
    render(
      <SchedulePageProvider>
        <OpenDetailsHarness lesson={lesson}>
          <LessonDetailsDialog
            userRole="student"
            getLessonTypeColor={() => "#123456"}
            getLessonTypeLabel={(value) => value ?? ""}
          />
        </OpenDetailsHarness>
      </SchedulePageProvider>
    )

    expect(screen.getByRole("dialog", { name })).toBeInTheDocument()
  })
})
