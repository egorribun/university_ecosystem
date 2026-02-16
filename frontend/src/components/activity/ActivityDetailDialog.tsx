import { useTranslation } from "react-i18next"
import { Button, ProgressBar } from "@/components/ui"
import Dialog from "@/components/Dialog"
import type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
  DetailSection,
  PeriodKey,
} from "@/components/activity/activityTypes"

type ActivityDetailDialogProps = {
  detail: string
  onClose: () => void
  detailSection: DetailSection
  attendance?: AttendanceStats | null
  grades?: GradeStats | null
  participation?: ParticipationStats | null
  labelByPeriod: (period: PeriodKey) => string
  period: PeriodKey
  attendanceStatusLabel: (status: "present" | "absent" | "late") => string
  formatDate: (date: string) => string
  separator: string
}

export function ActivityDetailDialog({
  detail,
  onClose,
  detailSection,
  attendance,
  grades,
  participation,
  labelByPeriod,
  period,
  attendanceStatusLabel,
  formatDate,
  separator,
}: ActivityDetailDialogProps) {
  const { t } = useTranslation(["activity"])

  return (
    <Dialog
      open={detail !== ""}
      onClose={onClose}
      title={
        detailSection ? t(`activity:sections.${detailSection}.dialogTitle`) : ""
      }
      size="md"
    >
      {detail === "attendance" && (
        <div className="space-y-4">
          <p className="text-base text-text-primary">
            {t("activity:sections.attendance.dialogTotal", {
              present: attendance?.present ?? 0,
              total: attendance?.total ?? 0,
              period: attendance?.periodLabel || labelByPeriod(period),
            })}
          </p>
          <ProgressBar
            value={Math.max(0, Math.min(100, attendance?.percent ?? 0))}
            className="h-2.5 rounded-lg"
            barClassName="bg-(--success-text) rounded-lg"
          />
          <div className="space-y-2">
            {(attendance?.recent ?? []).map((r, i) => (
              <div
                key={`${r.date}-${r.course}-${r.status}-${i}`}
                className="space-y-0.5"
              >
                <p className="text-sm font-semibold text-text-primary">
                  {`${r.course} — ${attendanceStatusLabel(r.status)}`}
                </p>
                <p className="text-xs text-(--text-caption)">
                  {formatDate(r.date)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
      {detail === "grades" && (
        <div className="space-y-4">
          <p className="text-base font-semibold text-text-primary">
            {grades?.scale === "gpa"
              ? `GPA ${(grades?.average ?? 0).toFixed(2)}`
              : grades?.scale === "100"
                ? `${Math.round(grades?.average ?? 0)}/100`
                : `${(grades?.average ?? 0).toFixed(1)}/5`}
          </p>
          <div className="space-y-2">
            {(grades?.recent ?? []).map((r, i) => (
              <div
                key={`${r.date}-${r.course}-${r.score}-${i}`}
                className="space-y-0.5"
              >
                <p className="text-sm font-semibold text-text-primary">
                  {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                </p>
                <p className="text-xs text-(--text-caption)">
                  {formatDate(r.date)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
      {detail === "participation" && (
        <div className="space-y-4">
          <p className="text-base text-text-primary">
            {[
              t("activity:sections.participation.eventsCount", {
                value: String(participation?.events ?? 0),
                count: participation?.events ?? 0,
              }),
              participation?.hours != null
                ? t("activity:sections.participation.summaryHours", {
                    count: participation.hours ?? 0,
                  })
                : null,
              participation?.groups != null
                ? t("activity:sections.participation.summaryGroups", {
                    count: participation.groups ?? 0,
                  })
                : null,
            ]
              .filter(Boolean)
              .join(separator)}
          </p>
          <div className="space-y-2">
            {(participation?.recent ?? []).map((r, i) => (
              <div
                key={`${r.date}-${r.title}-${r.role}-${i}`}
                className="space-y-0.5"
              >
                <p className="text-sm font-semibold text-text-primary">
                  {r.title}
                </p>
                <p className="text-xs text-(--text-caption)">
                  {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
      {/* Recent List Variants - these match what was in the original file */}
      {detail === "attendance_recent" && (
        <div className="space-y-2">
          {(attendance?.recent ?? []).map((r, i) => (
            <div
              key={`${r.date}-${r.course}-${r.status}-${i}-recent`}
              className="space-y-0.5"
            >
              <p className="text-sm font-semibold text-text-primary">
                {`${r.course} — ${attendanceStatusLabel(r.status)}`}
              </p>
              <p className="text-xs text-(--text-caption)">
                {formatDate(r.date)}
              </p>
            </div>
          ))}
        </div>
      )}
      {detail === "grades_recent" && (
        <div className="space-y-2">
          {(grades?.recent ?? []).map((r, i) => (
            <div
              key={`${r.date}-${r.course}-${r.score}-${i}-recent`}
              className="space-y-0.5"
            >
              <p className="text-sm font-semibold text-text-primary">
                {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
              </p>
              <p className="text-xs text-(--text-caption)">
                {formatDate(r.date)}
              </p>
            </div>
          ))}
        </div>
      )}
      {detail === "participation_recent" && (
        <div className="space-y-2">
          {(participation?.recent ?? []).map((r, i) => (
            <div
              key={`${r.date}-${r.title}-${r.role}-${i}-recent`}
              className="space-y-0.5"
            >
              <p className="text-sm font-semibold text-text-primary">
                {r.title}
              </p>
              <p className="text-xs text-(--text-caption)">
                {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
              </p>
            </div>
          ))}
        </div>
      )}
      <div className="mt-6 flex justify-end">
        <Button variant="outline" onClick={onClose}>
          {t("activity:dialog.close")}
        </Button>
      </div>
    </Dialog>
  )
}
