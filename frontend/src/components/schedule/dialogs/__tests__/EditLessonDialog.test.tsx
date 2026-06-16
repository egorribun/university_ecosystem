import { useEffect, type ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

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

function renderDialog(props = baseProps) {
  return render(
    <SchedulePageProvider>
      <OpenEditHarness>
        <EditLessonDialog {...props} />
      </OpenEditHarness>
    </SchedulePageProvider>
  )
}

describe("EditLessonDialog", () => {
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
})
