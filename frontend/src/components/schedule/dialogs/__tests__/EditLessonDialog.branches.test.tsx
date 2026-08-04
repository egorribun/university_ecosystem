import { useEffect, type ReactNode } from "react"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const apiMocks = vi.hoisted(() => ({
  patch: vi.fn(() => Promise.resolve({ data: {} })),
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    default: { patch: apiMocks.patch },
  }
})
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EditLessonDialog } from "@/components/schedule/dialogs/EditLessonDialog"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { logError } from "@/app/logger"

// Lesson with bare HH:MM start/end (no "T") — exercises the else-branch in the
// time onChange handlers (datePart from `new Date()`).
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

// Lesson with ISO datetime start/end — exercises the "T"-includes branch in the
// time onChange handlers (datePart from the existing ISO string).
const ISO_SAMPLE: Lesson = {
  ...SAMPLE,
  id: "l2",
  start_time: "2026-01-15T09:00:00",
  end_time: "2026-01-15T10:30:00",
}

function makeBaseProps() {
  return {
    schedule: [SAMPLE],
    lessonTypeOptions: [
      { value: "lecture", label: "Лекция" },
      { value: "practice", label: "Практика" },
    ],
    toBackendLessonType: (v?: string | null) => v ?? "lecture",
    applyScheduleUpdate: vi.fn((updater: (prev: Lesson[]) => Lesson[]) => updater([SAMPLE])),
    refresh: vi.fn(),
  }
}

function OpenEditHarness({ lesson, children }: { lesson: Lesson; children: ReactNode }) {
  const { openDialog } = useSchedulePage()
  useEffect(() => {
    openDialog("edit", lesson)
  }, [openDialog, lesson])
  return <>{children}</>
}

function renderDialog(props: ReturnType<typeof makeBaseProps>, lesson: Lesson = SAMPLE) {
  return render(
    <SchedulePageProvider>
      <OpenEditHarness lesson={lesson}>
        <EditLessonDialog {...props} />
      </OpenEditHarness>
    </SchedulePageProvider>
  )
}

describe("EditLessonDialog — branches", () => {
  beforeEach(() => {
    apiMocks.patch.mockClear()
    apiMocks.patch.mockResolvedValue({ data: {} })
    vi.mocked(logError).mockClear()
  })

  it("edits every text field (subject/teacher/room) via change handlers", () => {
    const props = makeBaseProps()
    renderDialog(props)

    const subject = screen.getByDisplayValue("Линейная алгебра")
    fireEvent.change(subject, { target: { value: "Дискретная математика" } })
    expect(screen.getByDisplayValue("Дискретная математика")).toBeInTheDocument()

    const teacher = screen.getByDisplayValue("Иванова Е.А.")
    fireEvent.change(teacher, { target: { value: "Петров В.П." } })
    expect(screen.getByDisplayValue("Петров В.П.")).toBeInTheDocument()

    const room = screen.getByDisplayValue("ГУК-305")
    fireEvent.change(room, { target: { value: "ЛК-201" } })
    expect(screen.getByDisplayValue("ЛК-201")).toBeInTheDocument()
  })

  it("renders empty values for nullable lesson metadata", () => {
    const nullableLesson = {
      ...SAMPLE,
      subject: null,
      teacher: null,
      room: null,
      lesson_type: null,
    } as unknown as Lesson

    renderDialog(makeBaseProps(), nullableLesson)

    expect(screen.getByLabelText("schedule:form.subject")).toHaveValue("")
    expect(screen.getByLabelText("schedule:form.teacher")).toHaveValue("")
    expect(screen.getByLabelText("schedule:form.room")).toHaveValue("")
    expect(screen.getAllByRole("combobox")[0]).toHaveTextContent("schedule:form.lessonType")
  })

  it("edits start/end time on a bare HH:MM lesson (Date() datePart else-branch)", () => {
    const props = makeBaseProps()
    renderDialog(props)

    const start = screen.getByDisplayValue("09:00")
    fireEvent.change(start, { target: { value: "11:15" } })
    expect(screen.getByDisplayValue("11:15")).toBeInTheDocument()

    const end = screen.getByDisplayValue("10:30")
    fireEvent.change(end, { target: { value: "12:45" } })
    expect(screen.getByDisplayValue("12:45")).toBeInTheDocument()
  })

  it("edits start/end time on an ISO datetime lesson (existing-datePart branch)", () => {
    const props = makeBaseProps()
    renderDialog(props, ISO_SAMPLE)

    const start = screen.getByDisplayValue("09:00")
    fireEvent.change(start, { target: { value: "08:30" } })
    expect(screen.getByDisplayValue("08:30")).toBeInTheDocument()

    const end = screen.getByDisplayValue("10:30")
    fireEvent.change(end, { target: { value: "11:00" } })
    expect(screen.getByDisplayValue("11:00")).toBeInTheDocument()
  })

  it("changes the lesson type via the Select onValueChange handler", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props)

    // First combobox is the lesson-type select (Лекция currently selected).
    const comboboxes = screen.getAllByRole("combobox")
    await user.click(comboboxes[0]!)
    await user.click(screen.getByRole("option", { name: "Практика" }))
    expect(comboboxes[0]!).toHaveTextContent("Практика")
  })

  it("changes the parity via the parity Select onValueChange handler", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props)

    // Last combobox is the week/parity select.
    const comboboxes = screen.getAllByRole("combobox")
    await user.click(comboboxes[comboboxes.length - 1]!)
    await user.click(screen.getByRole("option", { name: "schedule:week.odd" }))
    expect(comboboxes[comboboxes.length - 1]!).toHaveTextContent("schedule:week.odd")
  })

  it("saves successfully: optimistic update, PATCH, success snackbar, refresh, close", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props)

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledTimes(1))
    expect(apiMocks.patch).toHaveBeenCalledWith(
      "/schedule/l1",
      expect.objectContaining({ subject: "Линейная алгебра", lesson_type: "lecture" })
    )
    // Optimistic update applied + refresh fired on success.
    expect(props.applyScheduleUpdate).toHaveBeenCalled()
    await waitFor(() => expect(props.refresh).toHaveBeenCalledTimes(1))
    // Dialog closed during the optimistic path.
    expect(screen.queryByText("schedule:dialog.editTitle")).not.toBeInTheDocument()
    expect(logError).not.toHaveBeenCalled()
  })

  it("reverts the optimistic update and logs on PATCH failure", async () => {
    const user = userEvent.setup()
    apiMocks.patch.mockRejectedValueOnce(new Error("network"))
    const props = makeBaseProps()
    renderDialog(props)

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() =>
      expect(logError).toHaveBeenCalledWith("Failed to update lesson", expect.any(Error))
    )
    // applyScheduleUpdate called twice: once for the optimistic write, once for the revert.
    await waitFor(() => expect(props.applyScheduleUpdate).toHaveBeenCalledTimes(2))
    expect(props.refresh).not.toHaveBeenCalled()
  })

  it("submits via form Enter (handleSubmit preventDefault path)", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props)

    const subject = screen.getByDisplayValue("Линейная алгебра")
    subject.focus()
    await user.keyboard("{Enter}")

    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledTimes(1))
  })

  it("does not render the form body when there is no selected lesson", () => {
    // Render the dialog WITHOUT opening it — editLesson stays null, fields absent.
    const props = makeBaseProps()
    render(
      <SchedulePageProvider>
        <EditLessonDialog {...props} />
      </SchedulePageProvider>
    )
    expect(screen.queryByText("schedule:dialog.editTitle")).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue("Линейная алгебра")).not.toBeInTheDocument()
  })
})
