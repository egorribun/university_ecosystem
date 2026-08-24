import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useLanguage, getLocaleForLanguage } from "@/contexts/LanguageContext"
import { periodDayCount, type PeriodKey } from "../types"
import CardShell from "./CardShell"

type ActivityHeatmapProps = {
  data: Map<string, number>
  period: PeriodKey
  ariaLabel: string
}

const HEAT_LEVELS = [
  "var(--activity-heat-0)",
  "var(--activity-heat-1)",
  "var(--activity-heat-2)",
  "var(--activity-heat-3)",
  "var(--activity-heat-4)",
] as const

function getHeatLevel(count: number, maxCount: number): number {
  if (count === 0) return 0
  const ratio = count / maxCount
  if (ratio <= 0.25) return 1
  if (ratio <= 0.5) return 2
  if (ratio <= 0.75) return 3
  return 4
}

/** Build a grid of dates going back `days` from today */
function buildDateGrid(days: number) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const startDate = new Date(today)
  startDate.setDate(startDate.getDate() - days + 1)

  // Align start to the nearest previous Monday (ISO week start)
  const dayOfWeek = startDate.getDay()
  // ISO Monday offset without a Sunday-only branch: Mon -> 0, Sun -> -6.
  const mondayOffset = -((dayOfWeek + 6) % 7)
  startDate.setDate(startDate.getDate() + mondayOffset)

  const cells: Array<{ date: string; dayOfWeek: number; weekIndex: number; isInRange: boolean }> =
    []
  const cursor = new Date(startDate)

  const rangeStart = new Date(today)
  rangeStart.setDate(rangeStart.getDate() - days + 1)

  let weekIndex = 0
  while (cursor <= today) {
    const dateStr = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}-${String(cursor.getDate()).padStart(2, "0")}`
    const dow = cursor.getDay() === 0 ? 6 : cursor.getDay() - 1 // Monday = 0
    const isInRange = cursor >= rangeStart && cursor <= today
    cells.push({ date: dateStr, dayOfWeek: dow, weekIndex, isInRange })

    cursor.setDate(cursor.getDate() + 1)
    if (cursor.getDay() === 1 && cursor <= today) weekIndex++
  }

  return { cells, totalWeeks: weekIndex + 1 }
}

/** Extract month labels positioned at the first Monday of each month */
function getMonthLabels(
  cells: Array<{ date: string; dayOfWeek: number; weekIndex: number }>,
  locale: string
) {
  const seen = new Set<string>()
  const labels: Array<{ label: string; weekIndex: number }> = []
  for (const cell of cells) {
    if (cell.dayOfWeek !== 0) continue // only check Mondays
    const month = cell.date.slice(0, 7)
    if (!seen.has(month)) {
      seen.add(month)
      const date = new Date(cell.date + "T00:00:00")
      labels.push({
        label: new Intl.DateTimeFormat(locale, { month: "short" }).format(date),
        weekIndex: cell.weekIndex,
      })
    }
  }
  return labels
}

export function ActivityHeatmap({ data, period, ariaLabel }: ActivityHeatmapProps) {
  const { t } = useTranslation(["activity", "common"])
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)

  const days = periodDayCount(period)
  const maxCount = useMemo(() => Math.max(...data.values(), 1), [data])

  const { cells, totalWeeks } = useMemo(() => buildDateGrid(days), [days])

  const monthLabels = useMemo(() => getMonthLabels(cells, locale), [cells, locale])

  // Day-of-week labels (Mon, Wed, Fri)
  const dayLabels = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(locale, { weekday: "short" })
    // Monday=0 → indices 0,2,4 (Mon, Wed, Fri)
    return [0, 2, 4].map((dow) => {
      const d = new Date(2024, 0, dow + 1) // 2024-01-01 is Monday
      return { label: fmt.format(d), row: dow }
    })
  }, [locale])

  return (
    <CardShell tone="neutral" aria-label={ariaLabel}>
      <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-tertiary">
        {t("activity:heatmap.title")}
      </h3>
      <div className="activity-heatmap-container overflow-x-auto">
        <div
          className="inline-grid gap-[3px]"
          style={{
            gridTemplateRows: `auto repeat(7, 1fr)`,
            gridTemplateColumns: `auto repeat(${totalWeeks}, 1fr)`,
          }}
        >
          {/* Month labels row */}
          <div /> {/* empty corner cell */}
          {Array.from({ length: totalWeeks }, (_, wi) => {
            const monthLabel = monthLabels.find((m) => m.weekIndex === wi)
            return (
              <div
                key={`month-${wi}`}
                className="text-[10px] text-text-tertiary text-center leading-tight"
              >
                {monthLabel?.label ?? ""}
              </div>
            )
          })}
          {/* Day rows */}
          {Array.from({ length: 7 }, (_, dow) => {
            const dayLabel = dayLabels.find((d) => d.row === dow)
            return [
              <div
                key={`dl-${dow}`}
                className="flex items-center pr-1 text-[10px] text-text-tertiary"
              >
                {dayLabel?.label ?? ""}
              </div>,
              ...Array.from({ length: totalWeeks }, (_, wi) => {
                const cell = cells.find((c) => c.dayOfWeek === dow && c.weekIndex === wi)
                if (!cell || !cell.isInRange) {
                  return <div key={`e-${dow}-${wi}`} />
                }
                const count = data.get(cell.date) ?? 0
                const level = getHeatLevel(count, maxCount)
                return (
                  <div
                    key={cell.date}
                    className="activity-heatmap-cell"
                    role="img"
                    style={{ backgroundColor: HEAT_LEVELS[level] }}
                    title={t("activity:heatmap.cellLabel", { date: cell.date, count })}
                    aria-label={t("activity:heatmap.cellLabel", { date: cell.date, count })}
                  />
                )
              }),
            ]
          }).flat()}
        </div>

        {/* Legend */}
        <div className="mt-3 flex items-center justify-end gap-1 text-[10px] text-text-tertiary">
          <span>{t("activity:heatmap.legendLess")}</span>
          {HEAT_LEVELS.map((color, i) => (
            <div
              key={i}
              className="activity-heatmap-cell"
              role="img"
              aria-label={t("activity:heatmap.legendLevel", { level: i })}
              style={{ backgroundColor: color }}
            />
          ))}
          <span>{t("activity:heatmap.legendMore")}</span>
        </div>
      </div>
    </CardShell>
  )
}
