import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useEffect, type ReactNode } from "react"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { LessonTypeConfig } from "@/components/schedule/scheduleUtils"
import { AddLessonDialog } from "./AddLessonDialog"

// Wave 197 SW6 — AddLessonDialog Storybook fixture (CONTEXT-tier, medium).
//
// Opened via the real <SchedulePageProvider> + a mount-effect harness that calls
// openDialog("add") (isOpen = activeDialog === "add"). The settings Dialog portals
// to document.body, so it shows in the default theme only (EventQrDialog pattern).
// The api submit-path won't fire without Save.
//
// Variants: Default (open).

const LESSON_TYPE_OPTIONS = [
  { value: "lecture", label: "Лекция" },
  { value: "practice", label: "Практика" },
  { value: "lab", label: "Лабораторная" },
  { value: "seminar", label: "Семинар" },
]

const LESSON_TYPE_CONFIGS: LessonTypeConfig[] = [
  {
    id: "lecture",
    backend: ["lecture", "лекция"],
    label: "Лекция",
    color: "var(--lt-lecture-badge)",
  },
  {
    id: "practice",
    backend: ["practice", "практика"],
    label: "Практика",
    color: "var(--lt-practice-badge)",
  },
]

function OpenDialogHarness({ children }: { children: ReactNode }) {
  const { openDialog } = useSchedulePage()
  useEffect(() => {
    openDialog("add")
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

const meta: Meta<typeof AddLessonDialog> = {
  title: "Schedule/AddLessonDialog",
  component: AddLessonDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withDialog],
  args: {
    selectedGroupId: "g1",
    defaultLessonType: "lecture",
    lessonTypeOptions: LESSON_TYPE_OPTIONS,
    lessonTypeConfigs: LESSON_TYPE_CONFIGS,
    refresh: () => {},
  },
}

export default meta
type Story = StoryObj<typeof AddLessonDialog>

export const Default: Story = {}
