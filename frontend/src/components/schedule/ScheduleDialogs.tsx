import { useScheduleData } from "@/hooks/useScheduleData"
import { LessonDetailsDialog } from "./dialogs/LessonDetailsDialog"
import { AddLessonDialog } from "./dialogs/AddLessonDialog"
import { EditLessonDialog } from "./dialogs/EditLessonDialog"

type ScheduleDialogsProps = Pick<
  ReturnType<typeof useScheduleData>,
  | "user"
  | "selectedGroup"
  | "defaultLessonType"
  | "lessonTypeOptions"
  | "lessonTypeConfigs"
  | "refresh"
  | "rawSchedule"
  | "toBackendLessonType"
  | "applyScheduleUpdate"
  | "getLessonTypeColor"
> & {
  // Add mapped helpers if needed
  getLessonTypeLabel: (val?: string | null) => string
}

export function ScheduleDialogs({
  user,
  selectedGroup,
  defaultLessonType,
  lessonTypeOptions,
  lessonTypeConfigs,
  refresh,
  rawSchedule,
  toBackendLessonType,
  applyScheduleUpdate,
  getLessonTypeColor,
  getLessonTypeLabel,
}: ScheduleDialogsProps) {
  return (
    <>
      <LessonDetailsDialog
        userRole={user?.role}
        getLessonTypeColor={getLessonTypeColor}
        getLessonTypeLabel={getLessonTypeLabel}
      />
      <AddLessonDialog
        selectedGroupId={selectedGroup}
        defaultLessonType={defaultLessonType}
        lessonTypeOptions={lessonTypeOptions}
        lessonTypeConfigs={lessonTypeConfigs}
        refresh={refresh}
      />
      <EditLessonDialog
        schedule={rawSchedule}
        lessonTypeOptions={lessonTypeOptions}
        toBackendLessonType={toBackendLessonType}
        applyScheduleUpdate={applyScheduleUpdate}
        refresh={refresh}
      />
    </>
  )
}
