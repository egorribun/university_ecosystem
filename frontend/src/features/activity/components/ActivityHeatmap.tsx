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

type HeatmapCell = {
  date: string
  day: Date
  dayOfWeek: number
  weekIndex: number
  isInRange: boolean
}

function toIsoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

/**
 * Build a grid of dates going back `days` from today (inclusive). The grid
 * starts on the ISO Monday on or before the first day of the range; the
 * leading days before the range are kept as out-of-range placeholders.
 * Dates are derived from calendar components, so the local clock time and
 * DST transitions never shift a cell.
 */
function buildDateGrid(days: number) {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth()
  const firstDay = now.getDate() - days + 1
  // ISO Monday offset: Mon -> 0, Sun -> 6.
  const leading = (new Date(year, month, firstDay).getDay() + 6) % 7
  const total = leading + days

  const cells = Array.from({ length: total }, (_, index): HeatmapCell => {
    const day = new Date(year, month, firstDay - leading + index)
    return {
      date: toIsoDate(day),
      day,
      dayOfWeek: index % 7,
      weekIndex: Math.floor(index / 7),
      isInRange: index >= leading,
    }
  })

  return { cells, totalWeeks: Math.ceil(total / 7) }
}

/** Extract month labels positioned at the first Monday of each month */
function getMonthLabels(cells: readonly HeatmapCell[], locale: string) {
  const labels = new Map<string, { label: string; weekIndex: number }>()
  for (const cell of cells) {
    if (cell.dayOfWeek !== 0) continue // only check Mondays
    const month = cell.date.slice(0, 7)
    if (!labels.has(month)) {
      labels.set(month, {
        label: new Intl.DateTimeFormat(locale, { month: "short" }).format(cell.day),
        weekIndex: cell.weekIndex,
      })
    }
  }
  return [...labels.values()]
}

export function ActivityHeatmap({ data, period, ariaLabel }: ActivityHeatmapProps) {
  const { t } = useTranslation("activity")
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
        {t("heatmap.title")}
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
                    title={t("heatmap.cellLabel", { date: cell.date, count })}
                    aria-label={t("heatmap.cellLabel", { date: cell.date, count })}
                  />
                )
              }),
            ]
          }).flat()}
        </div>

        {/* Legend */}
        <div className="mt-3 flex items-center justify-end gap-1 text-[10px] text-text-tertiary">
          <span>{t("heatmap.legendLess")}</span>
          {HEAT_LEVELS.map((color, i) => (
            <div
              key={i}
              className="activity-heatmap-cell"
              role="img"
              aria-label={t("heatmap.legendLevel", { level: i })}
              style={{ backgroundColor: color }}
            />
          ))}
          <span>{t("heatmap.legendMore")}</span>
        </div>
      </div>
      <table className="sr-only">
        <caption>{t("heatmap.title")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("chartTableHeaders.date")}</th>
            <th scope="col">{t("title")}</th>
          </tr>
        </thead>
        <tbody>
          {cells
            .filter((cell) => cell.isInRange)
            .map((cell) => (
              <tr key={cell.date}>
                <th scope="row">{cell.date}</th>
                <td>{data.get(cell.date) ?? 0}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </CardShell>
  )
}
