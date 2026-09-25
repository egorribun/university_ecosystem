import { useState, useEffect, type ChangeEvent, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import api from "@/api/client"
import { logError } from "@/app/logger"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { Select } from "@/components/ui/Select"
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

export function isAddLessonFormValid(
  fields: Pick<AddLessonFields, "subject" | "startTime" | "endTime">
): boolean {
  return fields.subject.trim() !== "" && fields.startTime !== "" && fields.endTime !== ""
}

export function resolveBackendLessonType(
  lessonType: string,
  lessonTypeConfigs: LessonTypeConfig[]
): string {
  const match = lessonTypeConfigs.find((config) => config.id === lessonType)
  return match ? (match.backend[0] ?? lessonType) : lessonType
}

export type AddLessonTextField = "subject" | "teacher" | "room" | "startTime" | "endTime"

export function updateAddLessonField(
  fields: AddLessonFields,
  field: AddLessonTextField,
  value: string
): AddLessonFields {
  return { ...fields, [field]: value }
}

export function createAddLessonFieldUpdater(
  field: AddLessonTextField,
  value: string
): (fields: AddLessonFields) => AddLessonFields {
  return function updateField(fields: AddLessonFields): AddLessonFields {
    return updateAddLessonField(fields, field, value)
  }
}

export function updateAddLessonChoice(
  fields: AddLessonFields,
  field: "lessonType" | "parity",
  value: string
): AddLessonFields {
  return { ...fields, [field]: value }
}

export function createAddLessonChoiceUpdater(
  field: "lessonType" | "parity",
  value: string
): (fields: AddLessonFields) => AddLessonFields {
  return function updateChoice(fields: AddLessonFields): AddLessonFields {
    return updateAddLessonChoice(fields, field, value)
  }
}

export function resetAddLessonTextFields(fields: AddLessonFields): AddLessonFields {
  return { ...fields, subject: "", teacher: "", room: "" }
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

  const isFormValid = isAddLessonFormValid(addFields)

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
    const backendType = resolveBackendLessonType(addFields.lessonType, lessonTypeConfigs)

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
      setAddFields(resetAddLessonTextFields)
    } catch (e) {
      logError("Failed to add lesson", e)
      showSnackbar(t("schedule:snackbar.addError"), "error")
    } finally {
      setIsAdding(false)
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (isFormValid && !isAdding) {
      handleAddLesson()
    }
  }

  function handleSubjectChange(event: ChangeEvent<HTMLInputElement>) {
    setAddFields(createAddLessonFieldUpdater("subject", event.target.value))
  }

  function handleTeacherChange(event: ChangeEvent<HTMLInputElement>) {
    setAddFields(createAddLessonFieldUpdater("teacher", event.target.value))
  }

  function handleRoomChange(event: ChangeEvent<HTMLInputElement>) {
    setAddFields(createAddLessonFieldUpdater("room", event.target.value))
  }

  function handleStartTimeChange(event: ChangeEvent<HTMLInputElement>) {
    setAddFields(createAddLessonFieldUpdater("startTime", event.target.value))
  }

  function handleEndTimeChange(event: ChangeEvent<HTMLInputElement>) {
    setAddFields(createAddLessonFieldUpdater("endTime", event.target.value))
  }

  function handleLessonTypeChange(value: string) {
    setAddFields(createAddLessonChoiceUpdater("lessonType", value))
  }

  function handleParityChange(value: string) {
    setAddFields(createAddLessonChoiceUpdater("parity", value as LessonParity))
  }

  return (
    <Dialog open={isOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
      <DialogTitle>{t("schedule:dialog.addTitle")}</DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent className="space-y-5 pt-4">
          <div className="space-y-5" role="presentation">
            <div>
              <label
                htmlFor="add-lesson-subject"
                className="mb-2 block text-sm font-semibold opacity-strong"
              >
                {t("schedule:form.subject")}
              </label>
              <Input
                id="add-lesson-subject"
                value={addFields.subject}
                onChange={handleSubjectChange}
                fullWidth
              />
            </div>
            <div>
              <label
                htmlFor="add-lesson-teacher"
                className="mb-2 block text-sm font-semibold opacity-strong"
              >
                {t("schedule:form.teacher")}
              </label>
              <Input
                id="add-lesson-teacher"
                value={addFields.teacher}
                onChange={handleTeacherChange}
                fullWidth
              />
            </div>
            <div>
              <label
                htmlFor="add-lesson-room"
                className="mb-2 block text-sm font-semibold opacity-strong"
              >
                {t("schedule:form.room")}
              </label>
              <Input
                id="add-lesson-room"
                value={addFields.room}
                onChange={handleRoomChange}
                fullWidth
              />
            </div>
            <div>
              <label
                htmlFor="add-lesson-type"
                className="mb-2 block text-sm font-semibold opacity-strong"
              >
                {t("schedule:form.lessonType")}
              </label>
              <Select
                id="add-lesson-type"
                value={addFields.lessonType}
                onValueChange={handleLessonTypeChange}
                options={lessonTypeOptions}
                placeholder={t("schedule:form.lessonType")}
              />
            </div>
            <div className="flex gap-4">
              <div className="flex-1">
                <label
                  htmlFor="add-lesson-start-time"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.startTime")}
                </label>
                <Input
                  id="add-lesson-start-time"
                  type="time"
                  value={addFields.startTime}
                  onChange={handleStartTimeChange}
                  fullWidth
                />
              </div>
              <div className="flex-1">
                <label
                  htmlFor="add-lesson-end-time"
                  className="mb-2 block text-sm font-semibold opacity-strong"
                >
                  {t("schedule:form.endTime")}
                </label>
                <Input
                  id="add-lesson-end-time"
                  type="time"
                  value={addFields.endTime}
                  onChange={handleEndTimeChange}
                  fullWidth
                />
              </div>
            </div>
            <div>
              <label
                htmlFor="add-lesson-parity"
                className="mb-2 block text-sm font-semibold opacity-strong"
              >
                {t("schedule:form.week")}
              </label>
              <Select
                id="add-lesson-parity"
                value={addFields.parity}
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
