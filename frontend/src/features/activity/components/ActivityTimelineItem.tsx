import { memo, type CSSProperties } from "react"
import { useTranslation } from "react-i18next"
import {
  CalendarCheck as AttendanceIcon,
  GraduationCap as GradeIcon,
  Award as ParticipationIcon,
} from "lucide-react"
import type { TimelineEntry } from "../types"

const DOT_COLORS: Record<string, string> = {
  "attendance-present": "var(--activity-present-accent)",
  "attendance-late": "var(--activity-late-accent)",
  "attendance-absent": "var(--activity-absent-accent)",
  grade: "var(--activity-grade-accent)",
  participation: "var(--activity-participation-accent)",
}
const FALLBACK_DOT_COLOR = "var(--text-tertiary)"

function getDotColor(entry: TimelineEntry): string {
  if (entry.type === "attendance") {
    return DOT_COLORS[`attendance-${entry.status}`] ?? FALLBACK_DOT_COLOR
  }
  return DOT_COLORS[entry.type]!
}

function getIcon(entry: TimelineEntry) {
  if (entry.type === "attendance") return <AttendanceIcon size={14} aria-hidden="true" />
  if (entry.type === "grade") return <GradeIcon size={14} aria-hidden="true" />
  return <ParticipationIcon size={14} aria-hidden="true" />
}

type ActivityTimelineItemProps = {
  entry: TimelineEntry
  formatDate: (date: string) => string
  attendanceStatusLabel: (status: "present" | "absent" | "late") => string
  staggerIndex: number
}

export const ActivityTimelineItem = memo(function ActivityTimelineItem({
  entry,
  formatDate,
  attendanceStatusLabel,
  staggerIndex,
}: ActivityTimelineItemProps) {
  const { t } = useTranslation(["activity"])
  const dotColor = getDotColor(entry)

  const title = (() => {
    if (entry.type === "attendance") {
      return t("activity:timeline.attendanceEntry", {
        course: entry.course ?? t("activity:sections.attendance.lessonFallback"),
        status: attendanceStatusLabel(entry.status),
      })
    }
    if (entry.type === "grade") {
      const scoreDisplay = entry.max ? `${entry.score}/${entry.max}` : String(entry.score)
      return t("activity:timeline.gradeEntry", { course: entry.course, score: scoreDisplay })
    }
    return t("activity:timeline.participationEntry", { title: entry.title })
  })()

  const subtitle = (() => {
    if (entry.type === "participation" && entry.role) return entry.role
    return null
  })()

  return (
    <div
      className="activity-stagger-item relative flex gap-3 pb-4 pl-10"
      style={{ "--stagger-index": staggerIndex } as CSSProperties}
      role="article"
    >
      {/* Dot — color alone must not convey status (WCAG 1.4.1) */}
      <div
        className="activity-timeline-dot absolute left-[14px] top-1.5"
        style={{ backgroundColor: dotColor }}
        aria-hidden="true"
      />
      <span className="sr-only">
        {entry.type === "attendance"
          ? attendanceStatusLabel(entry.status)
          : entry.type === "grade"
            ? t("activity:timeline.gradeType")
            : t("activity:timeline.participationType")}
      </span>

      {/* Content */}
      <div className="flex min-w-0 flex-1 items-start gap-2">
        <span className="mt-0.5 text-text-secondary" style={{ color: dotColor }}>
          {getIcon(entry)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          {subtitle && <p className="text-xs text-text-secondary">{subtitle}</p>}
          <p className="text-xs text-text-tertiary">{formatDate(entry.date)}</p>
        </div>
      </div>
    </div>
  )
})
