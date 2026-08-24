import { useEffect, type ReactNode } from "react"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const apiMocks = vi.hoisted(() => ({
  post: vi.fn(() => Promise.resolve({ data: {} })),
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    default: { post: apiMocks.post },
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

import { AddLessonDialog } from "@/components/schedule/dialogs/AddLessonDialog"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { LessonTypeConfig } from "@/components/schedule/scheduleUtils"
import { logError } from "@/app/logger"

const LESSON_TYPE_OPTIONS = [
  { value: "lecture", label: "Лекция" },
  { value: "practice", label: "Практика" },
]

const LESSON_TYPE_CONFIGS: LessonTypeConfig[] = [
  { id: "lecture", backend: ["LECTURE", "lec"], label: "Лекция", color: "#111" },
  { id: "practice", backend: ["PRACTICE"], label: "Практика", color: "#222" },
  // Config with an empty backend array — exercises the `?? addFields.lessonType`
  // fallback in the backend-type resolver.
  { id: "seminar", backend: [], label: "Семинар", color: "#333" },
]

function makeBaseProps(overrides: Partial<Parameters<typeof AddLessonDialog>[0]> = {}) {
  return {
    selectedGroupId: "g1" as string | null,
    defaultLessonType: "lecture",
    lessonTypeOptions: LESSON_TYPE_OPTIONS,
    lessonTypeConfigs: LESSON_TYPE_CONFIGS,
    refresh: vi.fn(),
    ...overrides,
  }
}

/**
 * Opens the "add" dialog and seeds `addDay` so the submit path is reachable.
 * Pass `addDay = null` to exercise the early-return guard in `handleAddLesson`.
 */
function OpenAddHarness({
  addDay = "monday",
  children,
}: {
  addDay?: string | null
  children: ReactNode
}) {
  const { openDialog, setAddDay } = useSchedulePage()
  useEffect(() => {
    openDialog("add")
    setAddDay(addDay)
  }, [openDialog, setAddDay, addDay])
  return <>{children}</>
}

function renderDialog(
  props: ReturnType<typeof makeBaseProps> = makeBaseProps(),
  addDay: string | null = "monday"
) {
  return render(
    <SchedulePageProvider>
      <OpenAddHarness addDay={addDay}>
        <AddLessonDialog {...props} />
      </OpenAddHarness>
    </SchedulePageProvider>
  )
}

/** Fills the 3 required fields so `isFormValid` becomes true. */
function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText("schedule:form.subject"), {
    target: { value: "Линейная алгебра" },
  })
  fireEvent.change(screen.getByLabelText("schedule:form.startTime"), {
    target: { value: "09:00" },
  })
  fireEvent.change(screen.getByLabelText("schedule:form.endTime"), {
    target: { value: "10:30" },
  })
}

describe("AddLessonDialog", () => {
  beforeEach(() => {
    apiMocks.post.mockClear()
    apiMocks.post.mockResolvedValue({ data: {} })
    vi.mocked(logError).mockClear()
  })

  it("renders the add form when the 'add' dialog is active", () => {
    renderDialog()
    expect(screen.getByText("schedule:dialog.addTitle")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "schedule:buttons.add" })).toBeInTheDocument()
  })

  it("disables the submit button until all required fields are filled (isFormValid)", () => {
    renderDialog()
    const submit = screen.getByRole("button", { name: "schedule:buttons.add" })
    expect(submit).toBeDisabled()

    fillRequiredFields()
    expect(submit).toBeEnabled()
  })

  it("keeps submit disabled when only some required fields are filled", () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText("schedule:form.subject"), {
      target: { value: "X" },
    })
    // start/end times still empty.
    expect(screen.getByRole("button", { name: "schedule:buttons.add" })).toBeDisabled()
    fireEvent.submit(screen.getByRole("button", { name: "schedule:buttons.add" }).closest("form")!)
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it("submits successfully: posts mapped payload, success snackbar, refresh, close", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props)

    fillRequiredFields()
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(1))
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/schedule",
      expect.objectContaining({
        subject: "Линейная алгебра",
        // lecture config -> backend[0] = "LECTURE"
        lesson_type: "LECTURE",
        start_time: "mondayT09:00:00",
        end_time: "mondayT10:30:00",
        weekday: "monday",
        parity: "both",
        group_id: "g1",
      })
    )
    await waitFor(() => expect(props.refresh).toHaveBeenCalledTimes(1))
    // Dialog closed on success.
    expect(screen.queryByText("schedule:dialog.addTitle")).not.toBeInTheDocument()
    expect(logError).not.toHaveBeenCalled()
  })

  it("submits selected lesson type and parity values", async () => {
    const user = userEvent.setup()
    renderDialog(makeBaseProps())
    fillRequiredFields()

    const [lessonType, parity] = screen.getAllByRole("combobox")
    await user.click(lessonType!)
    await user.click(await screen.findByRole("option", { name: "Практика" }))
    await user.click(parity!)
    await user.click(await screen.findByRole("option", { name: "schedule:week.odd" }))
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    await waitFor(() =>
      expect(apiMocks.post).toHaveBeenCalledWith(
        "/schedule",
        expect.objectContaining({ lesson_type: "PRACTICE", parity: "odd" })
      )
    )
  })

  it("falls back to addFields.lessonType when the matched config has an empty backend array", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps({
      defaultLessonType: "seminar",
      lessonTypeOptions: [...LESSON_TYPE_OPTIONS, { value: "seminar", label: "Семинар" }],
    })
    renderDialog(props)

    fillRequiredFields()
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(1))
    // seminar config has backend: [] -> resolver falls back to the id itself.
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/schedule",
      expect.objectContaining({ lesson_type: "seminar" })
    )
  })

  it("uses the raw lessonType when no config matches", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps({
      defaultLessonType: "unknown-type",
      lessonTypeOptions: [...LESSON_TYPE_OPTIONS, { value: "unknown-type", label: "Unknown" }],
    })
    renderDialog(props)

    fillRequiredFields()
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(1))
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/schedule",
      expect.objectContaining({ lesson_type: "unknown-type" })
    )
  })

  it("shows the error snackbar and logs when the POST fails", async () => {
    const user = userEvent.setup()
    apiMocks.post.mockRejectedValueOnce(new Error("network"))
    const props = makeBaseProps()
    renderDialog(props)

    fillRequiredFields()
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    await waitFor(() =>
      expect(logError).toHaveBeenCalledWith("Failed to add lesson", expect.any(Error))
    )
    // Refresh not fired on failure; dialog stays open.
    expect(props.refresh).not.toHaveBeenCalled()
    expect(screen.getByText("schedule:dialog.addTitle")).toBeInTheDocument()
  })

  it("does not submit when selectedGroupId is null (early-return guard)", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps({ selectedGroupId: null })
    renderDialog(props)

    fillRequiredFields()
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    // handleAddLesson returns early -> no POST.
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it("does not submit when addDay is null (early-return guard)", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props, null)

    fillRequiredFields()
    await user.click(screen.getByRole("button", { name: "schedule:buttons.add" }))

    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it("submits via form Enter and resets the text fields after success", async () => {
    const user = userEvent.setup()
    const props = makeBaseProps()
    renderDialog(props)

    fillRequiredFields()
    // also fill teacher/room so the reset is observable
    fireEvent.change(screen.getByLabelText("schedule:form.teacher"), {
      target: { value: "Иванова Е.А." },
    })
    fireEvent.change(screen.getByLabelText("schedule:form.room"), {
      target: { value: "ГУК-305" },
    })

    screen.getByLabelText("schedule:form.subject").focus()
    await user.keyboard("{Enter}")

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(1))
    // After a successful add the dialog closes; the text fields are reset in state.
    expect(screen.queryByText("schedule:dialog.addTitle")).not.toBeInTheDocument()
  })

  it("does not render the form when the 'add' dialog is not active", () => {
    render(
      <SchedulePageProvider>
        <AddLessonDialog {...makeBaseProps()} />
      </SchedulePageProvider>
    )
    expect(screen.queryByText("schedule:dialog.addTitle")).not.toBeInTheDocument()
  })

  it("resets lessonType to the new defaultLessonType when current type is no longer valid (sync effect)", () => {
    const props = makeBaseProps()
    const { rerender } = renderDialog(props)

    // Re-render with a different defaultLessonType + an options list that no
    // longer contains the current "lecture" value -> effect resets to default.
    const nextProps = makeBaseProps({
      defaultLessonType: "practice",
      lessonTypeOptions: [{ value: "practice", label: "Практика" }],
    })
    rerender(
      <SchedulePageProvider>
        <OpenAddHarness addDay="monday">
          <AddLessonDialog {...nextProps} />
        </OpenAddHarness>
      </SchedulePageProvider>
    )

    // The lesson-type select now reflects the new default's label.
    const comboboxes = screen.getAllByRole("combobox")
    expect(comboboxes[0]!).toHaveTextContent("Практика")
  })

  it("keeps the current lessonType when it is still valid after a prop change (sync effect no-op)", () => {
    const props = makeBaseProps()
    const { rerender } = renderDialog(props)

    // defaultLessonType changes but "lecture" is still a valid option -> effect
    // returns prev unchanged.
    const nextProps = makeBaseProps({ defaultLessonType: "practice" })
    rerender(
      <SchedulePageProvider>
        <OpenAddHarness addDay="monday">
          <AddLessonDialog {...nextProps} />
        </OpenAddHarness>
      </SchedulePageProvider>
    )

    const comboboxes = screen.getAllByRole("combobox")
    expect(comboboxes[0]!).toHaveTextContent("Лекция")
  })

  it("does nothing in the sync effect when defaultLessonType is empty", () => {
    const props = makeBaseProps({ defaultLessonType: "" })
    renderDialog(props)
    // Empty default -> effect returns early; dialog still renders.
    expect(screen.getByText("schedule:dialog.addTitle")).toBeInTheDocument()
  })

  it("closes the dialog via the cancel button", async () => {
    const user = userEvent.setup()
    renderDialog()
    expect(screen.getByText("schedule:dialog.addTitle")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.queryByText("schedule:dialog.addTitle")).not.toBeInTheDocument()
  })
})
