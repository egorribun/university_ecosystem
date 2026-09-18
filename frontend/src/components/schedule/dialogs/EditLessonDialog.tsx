import { useState, useEffect, type ChangeEvent, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import api from "@/api/client"
import { logError } from "@/app/logger"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Select } from "@/components/ui/Select"
import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import {
  type Lesson,
  type LessonParity,
  getTimeStr,
  getEndTimeStr,
} from "@/components/schedule/scheduleUtils"
import { useSchedulePage } from "@/contexts/SchedulePageContext"

interface EditLessonDialogProps {
  schedule: Lesson[]
  lessonTypeOptions: { value: string; label: string }[]
  toBackendLessonType: (val?: string | null) => string
  applyScheduleUpdate: (updater: (prev: Lesson[]) => Lesson[]) => void
  refresh: () => void
}

export function isEditLessonFormValid(
  lesson: Pick<Lesson, "subject" | "start_time" | "end_time"> | null
): boolean {
  return !!lesson?.subject?.trim() && !!lesson?.start_time && !!lesson?.end_time
}

export function getLessonDatePart(value: string | null | undefined, now: Date): string {
  return value?.includes("T") ? value.split("T")[0]! : now.toISOString().split("T")[0]!
}

export type EditableLessonField = "subject" | "teacher" | "room"
export type EditableLessonTimeField = "start_time" | "end_time"

export function updateLessonField(
  lesson: Lesson,
  field: EditableLessonField,
  value: string
): Lesson {
  return { ...lesson, [field]: value }
}

export function updateLessonTimeField(
  lesson: Lesson,
  field: EditableLessonTimeField,
  value: string,
  now: Date
): Lesson {
  const datePart = getLessonDatePart(lesson[field], now)
  return { ...lesson, [field]: `${datePart}T${value}:00` }
}

export function updateLessonChoice(lesson: Lesson, value: string): Lesson {
  return { ...lesson, lesson_type: value }
}

export function updateLessonParity(lesson: Lesson, value: string): Lesson {
  return { ...lesson, parity: value as LessonParity }
}

export function replaceLessonById(
  lessons: Lesson[],
  lessonId: string,
  updatedLesson: Lesson
): Lesson[] {
  return lessons.map((lesson) => (lesson.id === lessonId ? updatedLesson : lesson))
}

export function createLessonFieldUpdater(
  field: EditableLessonField,
  value: string
): (lesson: Lesson | null) => Lesson | null {
  return function updateField(lesson: Lesson | null): Lesson | null {
    return lesson ? updateLessonField(lesson, field, value) : lesson
  }
}

export function createLessonTimeUpdater(
  field: EditableLessonTimeField,
  value: string,
  now: Date
): (lesson: Lesson | null) => Lesson | null {
  return function updateTime(lesson: Lesson | null): Lesson | null {
    return lesson ? updateLessonTimeField(lesson, field, value, now) : lesson
  }
}

export function createLessonChoiceUpdater(value: string): (lesson: Lesson | null) => Lesson | null {
  return function updateChoice(lesson: Lesson | null): Lesson | null {
    return lesson ? updateLessonChoice(lesson, value) : lesson
  }
}

export function createLessonParityUpdater(value: string): (lesson: Lesson | null) => Lesson | null {
  return function updateParity(lesson: Lesson | null): Lesson | null {
    return lesson ? updateLessonParity(lesson, value) : lesson
  }
}

export function createOptimisticLessonUpdater(
  lessonId: string,
  updatedLesson: Lesson
): (lessons: Lesson[]) => Lesson[] {
  return function updateOptimistically(lessons: Lesson[]): Lesson[] {
    return replaceLessonById(lessons, lessonId, updatedLesson)
  }
}

export function createRollbackUpdater(backup: Lesson[]): (lessons: Lesson[]) => Lesson[] {
  return function rollback(_lessons: Lesson[]): Lesson[] {
    return backup
  }
}

export function EditLessonDialog({
  schedule,
  lessonTypeOptions,
  toBackendLessonType,
  applyScheduleUpdate,
  refresh,
}: EditLessonDialogProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { activeDialog, closeDialog, selectedLesson, showSnackbar } = useSchedulePage()

  const isOpen = activeDialog === "edit"
  const [editLesson, setEditLesson] = useState<Lesson | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const isFormValid = isEditLessonFormValid(editLesson)

  useEffect(() => {
    if (isOpen && selectedLesson) {
      setEditLesson(selectedLesson)
    }
  }, [isOpen, selectedLesson])

  const handleSave = async (lesson: Lesson) => {
    const optimisticId = lesson.id
    const backup = schedule.map((lesson) => ({ ...lesson }))
    const backendLessonType = toBackendLessonType(lesson.lesson_type)
    const updatedLesson = { ...lesson, lesson_type: backendLessonType }

    // Optimistic update
    applyScheduleUpdate(createOptimisticLessonUpdater(optimisticId, updatedLesson))
    closeDialog()

    try {
      setIsSaving(true)
      await api.patch(`/schedule/${optimisticId}`, {
        ...lesson,
        lesson_type: backendLessonType,
      })
      showSnackbar(t("schedule:snackbar.updated"))
      refresh()
    } catch (err) {
      logError("Failed to update lesson", err)
      showSnackbar(t("schedule:snackbar.updateError"), "error")
      // Revert optimistic update
      applyScheduleUpdate(createRollbackUpdater(backup))
    } finally {
      setIsSaving(false)
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (editLesson && isFormValid && !isSaving) {
      void handleSave(editLesson)
    }
  }

  function handleSubjectChange(event: ChangeEvent<HTMLInputElement>) {
    setEditLesson(createLessonFieldUpdater("subject", event.target.value))
  }

  function handleTeacherChange(event: ChangeEvent<HTMLInputElement>) {
    setEditLesson(createLessonFieldUpdater("teacher", event.target.value))
  }

  function handleRoomChange(event: ChangeEvent<HTMLInputElement>) {
    setEditLesson(createLessonFieldUpdater("room", event.target.value))
  }

  function handleLessonTypeChange(value: string) {
    setEditLesson(createLessonChoiceUpdater(value))
  }

  function handleStartTimeChange(event: ChangeEvent<HTMLInputElement>) {
    setEditLesson(createLessonTimeUpdater("start_time", event.target.value, new Date()))
  }

  function handleEndTimeChange(event: ChangeEvent<HTMLInputElement>) {
    setEditLesson(createLessonTimeUpdater("end_time", event.target.value, new Date()))
  }

  function handleParityChange(value: string) {
    setEditLesson(createLessonParityUpdater(value))
  }

  return (
    <Dialog open={isOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
      <DialogTitle>{t("schedule:dialog.editTitle")}</DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent className="space-y-5 pt-4">
          {editLesson && (
            <div className="space-y-5">
              <div>
                <label
                  htmlFor="edit-lesson-subject"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.subject")}
                </label>
                <Input
                  id="edit-lesson-subject"
                  type="text"
                  value={editLesson.subject || ""}
                  onChange={handleSubjectChange}
                  fullWidth
                />
              </div>
              <div>
                <label
                  htmlFor="edit-lesson-teacher"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.teacher")}
                </label>
                <Input
                  id="edit-lesson-teacher"
                  type="text"
                  value={editLesson.teacher || ""}
                  onChange={handleTeacherChange}
                  fullWidth
                />
              </div>
              <div>
                <label
                  htmlFor="edit-lesson-room"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.room")}
                </label>
                <Input
                  id="edit-lesson-room"
                  type="text"
                  value={editLesson.room || ""}
                  onChange={handleRoomChange}
                  fullWidth
                />
              </div>
              <div>
                <label
                  htmlFor="edit-lesson-type"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.lessonType")}
                </label>
                <Select
                  id="edit-lesson-type"
                  value={editLesson.lesson_type || ""}
                  onValueChange={handleLessonTypeChange}
                  options={lessonTypeOptions}
                  placeholder={t("schedule:form.lessonType")}
                />
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label
                    htmlFor="edit-lesson-start-time"
                    className="mb-2 block text-sm font-semibold opacity-strong"
                  >
                    {t("schedule:form.startTime")}
                  </label>
                  <Input
                    id="edit-lesson-start-time"
                    type="time"
                    value={getTimeStr(editLesson)}
                    onChange={handleStartTimeChange}
                    fullWidth
                  />
                </div>
                <div className="flex-1">
                  <label
                    htmlFor="edit-lesson-end-time"
                    className="mb-2 block text-sm font-semibold opacity-strong"
                  >
                    {t("schedule:form.endTime")}
                  </label>
                  <Input
                    id="edit-lesson-end-time"
                    type="time"
                    value={getEndTimeStr(editLesson)}
                    onChange={handleEndTimeChange}
                    fullWidth
                  />
                </div>
              </div>
              <div>
                <label
                  htmlFor="edit-lesson-parity"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.week")}
                </label>
                <Select
                  id="edit-lesson-parity"
                  value={editLesson.parity}
                  onValueChange={handleParityChange}
                  options={[
                    { value: "both", label: t("schedule:week.both") },
                    { value: "odd", label: t("schedule:week.odd") },
                    { value: "even", label: t("schedule:week.even") },
                  ]}
                  placeholder={t("schedule:form.week")}
                />
              </div>
            </div>
          )}
        </DialogContent>
        <DialogActions>
          <Button id="edit-lesson-cancel" variant="ghost" type="button" onClick={closeDialog}>
            {t("common:buttons.cancel")}
          </Button>
          <Button
            id="edit-lesson-submit"
            variant="solid"
            type="submit"
            loading={isSaving}
            disabled={!isFormValid}
          >
            {t("common:buttons.save")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
