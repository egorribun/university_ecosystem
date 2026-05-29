import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useEffect, type ReactNode } from "react"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { EditLessonDialog } from "./EditLessonDialog"

// Wave 197 SW6 — EditLessonDialog Storybook fixture (CONTEXT-tier, medium).
//
// Opened via <SchedulePageProvider> + a mount-effect harness that calls
// openDialog("edit", lesson) (isOpen = activeDialog === "edit", form seeded from
// selectedLesson). The settings Dialog portals to document.body → default theme
// only. Submit-path won't fire without Save.
//
// Variants: Default (open, editing a lecture).

const SAMPLE_LESSON: Lesson = {
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

const LESSON_TYPE_OPTIONS = [
  { value: "lecture", label: "Лекция" },
  { value: "practice", label: "Практика" },
  { value: "lab", label: "Лабораторная" },
  { value: "seminar", label: "Семинар" },
]

function OpenDialogHarness({ children }: { children: ReactNode }) {
  const { openDialog } = useSchedulePage()
  useEffect(() => {
    openDialog("edit", SAMPLE_LESSON)
  }, [openDialog])
  return <>{children}</>
}

const withDialog: Decorator = (Story) => (
  <SchedulePageProvider>
    <OpenDialogHarness>
      <Story />
    </OpenDialogHarness>
  </SchedulePageProvider>
)

const meta: Meta<typeof EditLessonDialog> = {
  title: "Schedule/EditLessonDialog",
  component: EditLessonDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withDialog],
  args: {
    schedule: [SAMPLE_LESSON],
    lessonTypeOptions: LESSON_TYPE_OPTIONS,
    toBackendLessonType: (val) => val ?? "lecture",
    applyScheduleUpdate: () => {},
    refresh: () => {},
  },
}

export default meta
type Story = StoryObj<typeof EditLessonDialog>

export const Default: Story = {}
