import { memo, useRef, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { fmtTime, parseMinutes } from "@/utils/scheduleUtils"
import type { DashboardLesson } from "@/hooks/useDashboardSchedule"
import { useCountUp } from "@/hooks/useCountUp"

interface ScheduleTimelineProps {
  lessons: DashboardLesson[]
  minutesNow: number
  currentLesson: DashboardLesson | null
  nextLesson: DashboardLesson | null
}

/** Timeline range: 8:00 (480min) to 20:00 (1200min) = 720 minutes */
const RANGE_START = 480
const RANGE_END = 1200
const MOUNT_ONLY_TOKEN = Symbol("schedule-timeline-mount")

/** Keep the mount-only effect dependency contract stable and directly testable. */
export function getInitialEffectDeps(): readonly [symbol] {
  return [MOUNT_ONLY_TOKEN]
}

/** Normalize parsed lesson endpoints before any geometry or coercion occurs. */
export function normalizeLessonRange(
  startMin: number | null,
  endMin: number | null
): readonly [number, number] | null {
  if (startMin == null) return null
  if (endMin == null) return null
  return [startMin, endMin]
}

/** Keep derived geometry and marker data evaluated with the rendered timeline. */
function getTimelineRangeSpan(): number {
  return RANGE_END - RANGE_START
}

function getHourMarkers(): readonly number[] {
  return [8, 10, 12, 14, 16, 18, 20]
}

function minutesToPercent(minutes: number): number {
  return ((minutes - RANGE_START) / getTimelineRangeSpan()) * 100
}

/**
 * ScheduleTimeline — Horizontal interactive timeline for today's lessons (Wave 46)
 *
 * Renders a proportional time axis (8:00–20:00) with lesson blocks, current time
 * indicator, and hover tooltips. Auto-scrolls to "now" on mount.
 */
export const ScheduleTimeline = memo(function ScheduleTimeline({
  lessons,
  minutesNow,
  currentLesson,
  nextLesson,
}: ScheduleTimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const nowRef = useRef<HTMLDivElement>(null)
  const [hoveredId, setHoveredId] = useState<string | number | null>(null)
  // A state-backed sentinel keeps the mount-only dependency explicit to the
  // hooks linter without making the effect react to changing schedule props.
  const [mountOnlyToken] = useState<symbol>(() => getInitialEffectDeps()[0])

  // Auto-scroll to "now" indicator on mount only — don't fight user scroll
  useEffect(() => {
    // Small delay to ensure DOM layout is complete
    const timer = setTimeout(() => {
      if (nowRef.current && scrollRef.current) {
        const scrollContainer = scrollRef.current
        const nowEl = nowRef.current
        const containerWidth = scrollContainer.clientWidth
        const nowLeft = nowEl.offsetLeft

        scrollContainer.scrollTo({
          left: Math.max(0, nowLeft - containerWidth / 3),
          behavior: "smooth",
        })
      }
    }, 100)
    return () => clearTimeout(timer)
  }, [mountOnlyToken])

  // Position lessons on the timeline
  const positionedLessons = useMemo(() => {
    return lessons.flatMap((l) => {
      const parsedRange = normalizeLessonRange(parseMinutes(l.start_time), parseMinutes(l.end_time))

      // Reject malformed lessons before doing any numeric/coercive geometry.
      // Keeping this guard as the first return makes invalid input impossible
      // to leak into the rendered timeline (and avoids NaN CSS values).
      if (parsedRange === null) return []
      const [startMin, endMin] = parsedRange

      // A lesson must have positive duration. Reversed or zero-length ranges
      // cannot be represented faithfully on the horizontal timeline and must
      // not degrade into a misleading minimum-width block.
      if (endMin <= startMin) return []

      // Lessons wholly outside the visible axis do not need a DOM node.
      if (endMin <= RANGE_START || startMin >= RANGE_END) return []

      const left = minutesToPercent(Math.max(startMin, RANGE_START))
      const endPercent = minutesToPercent(Math.min(endMin, RANGE_END))

      return [
        {
          ...l,
          startMin,
          endMin,
          left: Math.max(0, left),
          width: Math.max(2, endPercent - left),
          isCurrent: currentLesson?.id === l.id,
          isNext: nextLesson?.id === l.id,
        },
      ]
    })
  }, [lessons, currentLesson, nextLesson])

  const nowPercent = minutesToPercent(Math.max(RANGE_START, Math.min(minutesNow, RANGE_END)))
  const showNowLine = minutesNow >= RANGE_START && minutesNow <= RANGE_END

  return (
    <div className="space-y-2">
      {/* Scrollable timeline container */}
      <div ref={scrollRef} className="overflow-x-auto scroll-smooth scrollbar-none">
        <div className="relative" style={{ height: "5.5rem", minWidth: "100%" }}>
          {/* Track background */}
          <div
            className="absolute left-0 right-0 rounded-xl bg-(--bg-matte-list) border border-(--border-matte)"
            style={{ top: "0.75rem", height: "3rem" }}
          />

          {/* Hour markers */}
          {getHourMarkers().map((hour) => {
            const percent = minutesToPercent(hour * 60)
            return (
              <div
                key={hour}
                className="absolute flex flex-col items-center"
                style={{ left: `${percent}%`, top: 0 }}
              >
                <div
                  className="h-2 w-px bg-(--text-tertiary) opacity-dim"
                  style={{ marginTop: "0.75rem" }}
                />
                <span
                  className="mt-0.5 font-mono text-[0.625rem] font-medium text-(--text-tertiary) select-none"
                  style={{ transform: "translateX(-50%)", position: "absolute", top: "3.75rem" }}
                >
                  {`${hour}:00`}
                </span>
              </div>
            )
          })}

          {/* Lesson blocks */}
          {positionedLessons.map((l) => (
            <div
              key={l.id}
              className={cn(
                "absolute cursor-pointer rounded-lg border transition-all duration-base",
                "hover:z-10 hover:shadow-premium hover:-translate-y-0.5",
                l.isCurrent
                  ? "border-brand bg-brand/(--opacity-subtle) shadow-sm z-[2]"
                  : l.isNext
                    ? "border-brand/(--opacity-soft) bg-brand/(--opacity-faint) z-[1]"
                    : "border-(--border-matte) bg-(--bg-matte-list) hover:border-brand/(--opacity-dim)"
              )}
              style={{
                left: `${l.left}%`,
                width: `${l.width}%`,
                top: "0.875rem",
                height: "2.75rem",
                minWidth: "2.5rem",
              }}
              onMouseEnter={() => setHoveredId(l.id)}
              onMouseLeave={() => setHoveredId(null)}
              onFocus={() => setHoveredId(l.id)}
              onBlur={() => setHoveredId(null)}
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- focusable for keyboard tooltip reveal
              tabIndex={0}
              role="img"
              aria-label={`${l.subject} ${fmtTime(l.start_time)}–${fmtTime(l.end_time)}`}
            >
              {/* Lesson label (truncated) */}
              <div className="flex h-full items-center gap-1.5 overflow-hidden px-2">
                {l.isCurrent && (
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand animate-pulse" />
                )}
                <span className="truncate text-xs font-semibold text-text-primary leading-tight">
                  {l.subject}
                </span>
              </div>

              {/* Hover tooltip — clamped horizontally to avoid viewport clipping */}
              {hoveredId === l.id && (
                <div
                  className={cn(
                    "absolute z-20 rounded-xl px-3 py-2",
                    "glass-layer-floating glass-noise",
                    "pointer-events-none shadow-premium min-w-40"
                  )}
                  style={{
                    bottom: "calc(100% + 0.5rem)",
                    left: l.left < 15 ? 0 : l.left > 80 ? "auto" : "50%",
                    right: l.left > 80 ? 0 : "auto",
                    transform: l.left < 15 || l.left > 80 ? "none" : "translateX(-50%)",
                  }}
                >
                  <p className="text-sm font-bold text-text-primary leading-tight mb-1">
                    {l.subject}
                  </p>
                  <p className="font-mono text-xs font-medium text-brand">
                    {fmtTime(l.start_time)}–{fmtTime(l.end_time)}
                  </p>
                  {l.teacher && (
                    <p className="text-xs text-(--text-secondary) mt-0.5 truncate">{l.teacher}</p>
                  )}
                  {l.room && <p className="text-xs text-(--text-tertiary) truncate">{l.room}</p>}
                  {/* Tooltip arrow — positioned relative to tooltip alignment */}
                  <div
                    className="absolute h-2 w-2 rotate-45 bg-(--bg-surface)"
                    style={{
                      bottom: "-0.25rem",
                      left: l.left < 15 ? "1rem" : l.left > 80 ? "auto" : "50%",
                      right: l.left > 80 ? "1rem" : "auto",
                      transform: l.left < 15 || l.left > 80 ? "none" : "translateX(-50%)",
                      borderRight: "1px solid var(--glass-border)",
                      borderBottom: "1px solid var(--glass-border)",
                    }}
                  />
                </div>
              )}
            </div>
          ))}

          {/* Current time indicator */}
          {showNowLine && (
            <div
              ref={nowRef}
              className="absolute z-[5] flex flex-col items-center"
              style={{ left: `${nowPercent}%`, top: "0.375rem", transform: "translateX(-50%)" }}
            >
              {/* Top dot */}
              <div className="h-2 w-2 rounded-full bg-brand shadow-sm shadow-brand/(--opacity-dim)" />
              {/* Vertical line */}
              <div className="w-0.5 bg-brand opacity-heavy" style={{ height: "3rem" }} />
              {/* Pulse ring */}
              <div className="absolute top-0 h-2 w-2 rounded-full bg-brand animate-ping opacity-dim" />
            </div>
          )}
        </div>
      </div>

      {/* Legend — Wave 48: animated counter for lesson count */}
      <LessonCountLegend count={positionedLessons.length} />
    </div>
  )
})

/** Extracted legend with animated counter */
function LessonCountLegend({ count }: { count: number }) {
  const { t } = useTranslation(["dashboard"])
  const { ref: countRef, value: animatedCount } = useCountUp(count)

  return (
    <div className="flex flex-wrap items-center gap-3 text-[0.6875rem] text-(--text-tertiary)">
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-brand" />
        {t("dashboard:now")}
      </span>
      {count > 0 && (
        <span ref={countRef} className="opacity-dim tabular-nums">
          {animatedCount} {t("dashboard:timeline.lessonCount", { count })}
        </span>
      )}
    </div>
  )
}

export default ScheduleTimeline
