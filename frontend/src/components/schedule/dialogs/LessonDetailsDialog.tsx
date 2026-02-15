import { useTranslation } from "react-i18next"
import { Clock as AccessTimeIcon, MapPin as RoomIcon, User as TeacherIcon } from "lucide-react"
import { Badge, Button } from "@/components/ui"
import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import { getTimeStr, getEndTimeStr } from "@/components/schedule/scheduleUtils"
import { useSchedulePage } from "@/contexts/SchedulePageContext"

interface LessonDetailsDialogProps {
  userRole?: string
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (type?: string | null) => string
}

export function LessonDetailsDialog({
  userRole,
  getLessonTypeColor,
  getLessonTypeLabel,
}: LessonDetailsDialogProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { activeDialog, closeDialog, selectedLesson, openDialog } = useSchedulePage()

  const isOpen = activeDialog === "details"
  const lesson = selectedLesson

  if (!lesson) return null

  return (
    <Dialog open={isOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
      <DialogTitle>{lesson.subject || t("schedule:dialog.detailsFallback")}</DialogTitle>
      <DialogContent className="space-y-4 pt-2">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold opacity-strong uppercase tracking-wider">
              {t("schedule:dialog.typeLabel")}:
            </span>
            <Badge
              style={{
                background: getLessonTypeColor(lesson.lesson_type),
                color: "white",
              }}
            >
              {getLessonTypeLabel(lesson.lesson_type)}
            </Badge>
          </div>
          <div className="space-y-1.5">
            <span className="text-xs font-bold opacity-strong uppercase tracking-wider text-text-secondary">
              {t("schedule:dialog.timeLabel")}:
            </span>
            <div className="flex">
              <Badge
                variant="outline"
                leadingIcon={<AccessTimeIcon size={16} />}
                className="font-medium border-brand/(--opacity-dim) bg-brand-subtle-bg text-brand"
              >
                {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
              </Badge>
            </div>
          </div>
          <div className="space-y-1.5">
            <span className="text-xs font-bold opacity-strong uppercase tracking-wider text-text-secondary">
              {t("schedule:dialog.roomLabel")}:
            </span>
            <div className="flex">
              <Badge
                variant="outline"
                leadingIcon={<RoomIcon size={16} className="text-(--primary-main)" />}
                className="font-medium text-(--text-primary) border-glass-border bg-surface/(--opacity-dim)"
              >
                {lesson.room || "—"}
              </Badge>
            </div>
          </div>
          <div className="space-y-1.5">
            <span className="text-xs font-bold opacity-strong uppercase tracking-wider text-text-secondary">
              {t("schedule:dialog.teacherLabel")}:
            </span>
            <div className="flex">
              <Badge
                variant="outline"
                leadingIcon={<TeacherIcon size={16} className="text-(--primary-main)" />}
                className="font-medium text-(--text-primary) border-glass-border bg-surface/(--opacity-dim)"
              >
                {lesson.teacher || "—"}
              </Badge>
            </div>
          </div>
        </div>
      </DialogContent>
      <DialogActions>
        {(userRole === "admin" || userRole === "teacher") && (
          <Button
            id="lesson-details-edit"
            variant="outline"
            onClick={() => {
              openDialog("edit", lesson)
            }}
          >
            {t("common:buttons.edit")}
          </Button>
        )}
        <Button id="lesson-details-close" variant="ghost" onClick={closeDialog}>
          {t("common:buttons.close")}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
