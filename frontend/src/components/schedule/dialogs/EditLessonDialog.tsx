import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import api from "@/api/client"
import { logError } from "@/app/logger"
import { Button, Input, Select } from "@/components/ui"
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

  const isFormValid =
    !!editLesson?.subject?.trim() && !!editLesson?.start_time && !!editLesson?.end_time

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
    applyScheduleUpdate((prev) =>
      prev.map((lesson) => (lesson.id === optimisticId ? updatedLesson : lesson))
    )
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
      applyScheduleUpdate(() => backup)
    } finally {
      setIsSaving(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (editLesson && isFormValid && !isSaving) {
      void handleSave(editLesson)
    }
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
                  onChange={(event) =>
                    setEditLesson((prev) => ({ ...prev!, subject: event.target.value }))
                  }
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
                  onChange={(event) =>
                    setEditLesson((prev) => ({ ...prev!, teacher: event.target.value }))
                  }
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
                  onChange={(event) =>
                    setEditLesson((prev) => ({ ...prev!, room: event.target.value }))
                  }
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
                  onValueChange={(val) =>
                    setEditLesson((prev) => ({ ...prev!, lesson_type: val }))
                  }
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
                    onChange={(event) =>
                      setEditLesson((prev) => {
                        const datePart = prev!.start_time?.includes("T")
                          ? prev!.start_time.split("T")[0]
                          : new Date().toISOString().split("T")[0]
                        return {
                          ...prev!,
                          start_time: `${datePart}T${event.target.value}:00`,
                        }
                      })
                    }
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
                    onChange={(event) =>
                      setEditLesson((prev) => {
                        const datePart = prev!.end_time?.includes("T")
                          ? prev!.end_time.split("T")[0]
                          : new Date().toISOString().split("T")[0]
                        return {
                          ...prev!,
                          end_time: `${datePart}T${event.target.value}:00`,
                        }
                      })
                    }
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
                  onValueChange={(val) =>
                    setEditLesson((prev) => ({ ...prev!, parity: val as LessonParity }))
                  }
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
