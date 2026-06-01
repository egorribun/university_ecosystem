import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useEffect, type ReactNode } from "react"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { Lesson } from "@/components/schedule/scheduleUtils"
import { LessonDetailsDialog } from "./LessonDetailsDialog"

// Wave 197 SW6 — LessonDetailsDialog Storybook fixture (CONTEXT-tier, medium).
//
// Opened via <SchedulePageProvider> + a mount-effect harness that calls
// openDialog("details", lesson) (isOpen = activeDialog === "details", body from
// selectedLesson). The settings Dialog portals to document.body → default theme
// only.
//
// Variants: Default (student view) / AdminView (admin → delete affordance).

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

function OpenDialogHarness({ children }: { children: ReactNode }) {
  const { openDialog } = useSchedulePage()
  useEffect(() => {
    openDialog("details", SAMPLE_LESSON)
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

const meta: Meta<typeof LessonDetailsDialog> = {
  title: "Schedule/LessonDetailsDialog",
  component: LessonDetailsDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withDialog],
  args: {
    getLessonTypeColor: () => "var(--lt-lecture-badge)",
    getLessonTypeLabel: (val) => val ?? "Лекция",
  },
}

export default meta
type Story = StoryObj<typeof LessonDetailsDialog>

export const Default: Story = {
  args: { userRole: "student" },
}

export const AdminView: Story = {
  args: { userRole: "admin" },
}
