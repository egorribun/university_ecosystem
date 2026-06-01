import { useEffect, type ReactNode } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"
import type { LessonTypeConfig } from "@/components/schedule/scheduleUtils"
import { ScheduleDialogs } from "./ScheduleDialogs"

// Wave 199 SW1 — ScheduleDialogs composite (CONTEXT-tier, no infra).
//
// Thin orchestrator that renders LessonDetailsDialog + AddLessonDialog +
// EditLessonDialog, each gated on SchedulePageContext.activeDialog. The harness
// opens the "add" dialog via the real <SchedulePageProvider> + openDialog("add")
// mount-effect (W197 AddLessonDialog pattern). The settings Dialog portals to
// document.body and animates with `m.div` → default-theme only, layout
// "fullscreen", LazyMotion required. api submit-path won't fire without Save.
//
// Variants: Default (Add dialog open).

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
  <LazyMotion features={domAnimation}>
    <SchedulePageProvider>
      <OpenDialogHarness>
        <Story />
      </OpenDialogHarness>
    </SchedulePageProvider>
  </LazyMotion>
)

const meta: Meta<typeof ScheduleDialogs> = {
  title: "Schedule/ScheduleDialogs",
  component: ScheduleDialogs,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withDialog],
  args: {
    user: null,
    selectedGroup: "g1",
    defaultLessonType: "lecture",
    lessonTypeOptions: LESSON_TYPE_OPTIONS,
    lessonTypeConfigs: LESSON_TYPE_CONFIGS,
    refresh: () => {},
    rawSchedule: [],
    toBackendLessonType: (value?: string | null) => value ?? "",
    applyScheduleUpdate: () => {},
    getLessonTypeColor: () => "var(--lt-lecture-badge)",
    getLessonTypeLabel: (value?: string | null) => value ?? "Lesson",
  },
}

export default meta
type Story = StoryObj<typeof ScheduleDialogs>

export const Default: Story = {}
