import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import api from "@/api/client"
import { logError } from "@/app/logger"
import { Button, Input, Select } from "@/components/ui"
import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import {
  type LessonParity,
  type AddLessonFields,
  type LessonTypeConfig,
} from "@/components/schedule/scheduleUtils"
import { useSchedulePage } from "@/contexts/SchedulePageContext"

interface AddLessonDialogProps {
  selectedGroupId: string | null
  defaultLessonType: string
  lessonTypeOptions: { value: string; label: string }[]
  lessonTypeConfigs: LessonTypeConfig[]
  refresh: () => void
}

export function AddLessonDialog({
  selectedGroupId,
  defaultLessonType,
  lessonTypeOptions,
  lessonTypeConfigs,
  refresh,
}: AddLessonDialogProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { activeDialog, closeDialog, showSnackbar, addDay } = useSchedulePage()

  const isOpen = activeDialog === "add"

  const [addFields, setAddFields] = useState<AddLessonFields>({
    subject: "",
    teacher: "",
    room: "",
    lessonType: defaultLessonType,
    startTime: "",
    endTime: "",
    parity: "both",
  })

  const [isAdding, setIsAdding] = useState(false)

  const isFormValid =
    addFields.subject.trim() !== "" && addFields.startTime !== "" && addFields.endTime !== ""

  // Sync default lesson type
  useEffect(() => {
    if (!defaultLessonType) return
    setAddFields((prev) => {
      // If current type is valid, keep it, else reset
      if (lessonTypeOptions.some((option) => option.value === prev.lessonType)) return prev
      return { ...prev, lessonType: defaultLessonType }
    })
  }, [defaultLessonType, lessonTypeOptions])

  const handleAddLesson = async () => {
    if (!selectedGroupId || !addDay) return

    // Resolve backend lesson type
    const backendType = (() => {
      const match = lessonTypeConfigs.find((c) => c.id === addFields.lessonType)
      return match ? (match.backend[0] ?? addFields.lessonType) : addFields.lessonType
    })()

    const payload = {
      subject: addFields.subject,
      teacher: addFields.teacher,
      room: addFields.room,
      lesson_type: backendType,
      start_time: `${addDay}T${addFields.startTime}:00`,
      end_time: `${addDay}T${addFields.endTime}:00`,
      weekday: addDay,
      parity: addFields.parity,
      group_id: selectedGroupId,
    }

    try {
      setIsAdding(true)
      await api.post("/schedule", payload)
      showSnackbar(t("schedule:snackbar.added"))
      closeDialog()
      refresh()
      // Reset fields partially?
      setAddFields((prev) => ({ ...prev, subject: "", teacher: "", room: "" }))
    } catch (e) {
      logError("Failed to add lesson", e)
      showSnackbar(t("schedule:snackbar.addError"))
    } finally {
      setIsAdding(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (isFormValid && !isAdding) {
      handleAddLesson()
    }
  }

  return (
    <Dialog open={isOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
      <DialogTitle>{t("schedule:dialog.addTitle")}</DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent className="space-y-5 pt-4">
          <div className="space-y-5" role="presentation">
            <div>
              <label className="mb-2 block text-sm font-semibold opacity-strong">
                {t("schedule:form.subject")}
              </label>
              <Input
                id="add-lesson-subject"
                value={addFields.subject}
                onChange={(event) => setAddFields({ ...addFields, subject: event.target.value })}
                fullWidth
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold opacity-strong">
                {t("schedule:form.teacher")}
              </label>
              <Input
                id="add-lesson-teacher"
                value={addFields.teacher}
                onChange={(event) => setAddFields({ ...addFields, teacher: event.target.value })}
                fullWidth
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold opacity-strong">
                {t("schedule:form.room")}
              </label>
              <Input
                id="add-lesson-room"
                value={addFields.room}
                onChange={(event) => setAddFields({ ...addFields, room: event.target.value })}
                fullWidth
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold opacity-strong">
                {t("schedule:form.lessonType")}
              </label>
              <Select
                id="add-lesson-type"
                value={addFields.lessonType}
                onValueChange={(val) => setAddFields({ ...addFields, lessonType: val })}
                options={lessonTypeOptions}
                placeholder={t("schedule:form.lessonType")}
              />
            </div>
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="mb-2 block text-sm font-semibold opacity-strong">
                  {t("schedule:form.startTime")}
                </label>
                <Input
                  id="add-lesson-start-time"
                  type="time"
                  value={addFields.startTime}
                  onChange={(event) =>
                    setAddFields({ ...addFields, startTime: event.target.value })
                  }
                  fullWidth
                />
              </div>
              <div className="flex-1">
                <label className="mb-2 block text-sm font-semibold opacity-strong">
                  {t("schedule:form.endTime")}
                </label>
                <Input
                  id="add-lesson-end-time"
                  type="time"
                  value={addFields.endTime}
                  onChange={(event) => setAddFields({ ...addFields, endTime: event.target.value })}
                  fullWidth
                />
              </div>
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold opacity-strong">
                {t("schedule:form.week")}
              </label>
              <Select
                id="add-lesson-parity"
                value={addFields.parity}
                onValueChange={(val) => setAddFields({ ...addFields, parity: val as LessonParity })}
                options={[
                  { value: "both", label: t("schedule:week.both") },
                  { value: "odd", label: t("schedule:week.odd") },
                  { value: "even", label: t("schedule:week.even") },
                ]}
                placeholder={t("schedule:form.week")}
              />
            </div>
          </div>
        </DialogContent>
        <DialogActions>
          <Button id="add-lesson-cancel" variant="ghost" type="button" onClick={closeDialog}>
            {t("common:buttons.cancel")}
          </Button>
          <Button
            id="add-lesson-submit"
            variant="solid"
            type="submit"
            loading={isAdding}
            disabled={!isFormValid}
          >
            {t("schedule:buttons.add")}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
