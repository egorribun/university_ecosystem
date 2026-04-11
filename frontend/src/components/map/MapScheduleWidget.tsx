import { useTranslation } from "react-i18next"
import { BookOpen, Clock, Navigation } from "lucide-react"
import type { BuildingLetter } from "@/data/campusBuildings"

interface NextLessonInfo {
  building: BuildingLetter
  floor: number
  roomId: string
  subject: string
  timeLeft: string
  room: string
}

interface MapScheduleWidgetProps {
  nextLesson: NextLessonInfo | null
  onNavigate: (letter: BuildingLetter, floor: number, roomId: string) => void
}

/**
 * MapScheduleWidget — next lesson indicator with "Show on map" action.
 * role="status" + aria-live="polite" for screen readers.
 */
export function MapScheduleWidget({ nextLesson, onNavigate }: MapScheduleWidgetProps) {
  const { t } = useTranslation("map")

  if (!nextLesson) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="map-schedule-widget p-3 flex items-center gap-2 text-xs text-[var(--text-tertiary)]"
      >
        <BookOpen className="h-4 w-4 opacity-50" />
        <span className="font-medium">{t("schedule.noUpcoming")}</span>
      </div>
    )
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="map-schedule-widget p-3"
    >
      <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)] mb-1.5">
        {t("schedule.widgetTitle")}
      </p>
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-text-primary truncate">
            {nextLesson.subject}
          </p>
          <div className="flex items-center gap-3 mt-1 text-xs text-[var(--text-secondary)]">
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3" />
              {t("schedule.room", { room: nextLesson.room })}
            </span>
            <span className="flex items-center gap-1 font-mono">
              <Clock className="h-3 w-3" />
              {t("schedule.inTime", { time: nextLesson.timeLeft })}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => onNavigate(nextLesson.building, nextLesson.floor, nextLesson.roomId)}
          className="map-category-chip flex items-center gap-1.5 text-xs font-bold shrink-0"
          data-active="true"
        >
          <Navigation className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{t("schedule.showOnMap")}</span>
        </button>
      </div>
    </div>
  )
}
