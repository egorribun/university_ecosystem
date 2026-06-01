import { useMemo } from "react"
import { m } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { motion as motionTokens } from "@/theme/tokens"

type BarData = { label: string; value: number; max?: number }

type ActivityBarChartProps = {
  data: BarData[]
  colorVar?: string
  ariaLabel: string
  title?: string
}

const BAR_HEIGHT = 24
const GAP = 8
const LABEL_WIDTH = 80
const VALUE_WIDTH = 40
const PADDING = { top: 8, right: 8, bottom: 8, left: 8 }

export function ActivityBarChart({
  data,
  colorVar = "var(--activity-grade-accent)",
  ariaLabel,
  title,
}: ActivityBarChartProps) {
  const { t } = useTranslation(["activity"])
  const reduce = useMediaQuery("(prefers-reduced-motion: reduce)")

  const { bars, svgHeight, barAreaWidth } = useMemo(() => {
    if (data.length === 0) return { bars: [], svgHeight: 0, barAreaWidth: 0 }

    const maxVal = Math.max(
      ...data.map((d) => {
        const v = d.max ?? d.value
        return Number.isFinite(v) ? v : 0 // NaN guard (L1)
      }),
      1
    )
    const svgWidth = 400 // viewBox width
    const barAreaWidth = svgWidth - PADDING.left - LABEL_WIDTH - VALUE_WIDTH - PADDING.right
    const svgHeight = PADDING.top + data.length * (BAR_HEIGHT + GAP) - GAP + PADDING.bottom

    const bars = data.map((d, i) => {
      const y = PADDING.top + i * (BAR_HEIGHT + GAP)
      const width = (d.value / maxVal) * barAreaWidth
      return {
        label: d.label,
        value: d.value,
        max: d.max,
        y,
        width: Math.max(width, 2),
        x: PADDING.left + LABEL_WIDTH,
      }
    })

    return { bars, svgHeight, barAreaWidth }
  }, [data])

  if (data.length === 0) {
    return (
      <div
        className="activity-chart-card flex items-center justify-center"
        style={{ minHeight: "var(--activity-chart-min-h, 120px)" }}
      >
        <p className="text-sm text-text-secondary">{t("activity:charts.noChartData")}</p>
      </div>
    )
  }

  return (
    <div className="activity-chart-card">
      <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-tertiary">
        {title ?? t("activity:charts.gradesBySubject")}
      </h3>
      <svg
        viewBox={`0 0 400 ${svgHeight}`}
        className="block w-full"
        role="img"
        aria-label={ariaLabel}
      >
        {bars.map((bar, i) => (
          <g key={bar.label}>
            {/* Subject label */}
            <text
              x={PADDING.left + LABEL_WIDTH - 8}
              y={bar.y + BAR_HEIGHT / 2 + 4}
              textAnchor="end"
              fill="var(--activity-chart-label)"
              fontSize={11}
              fontWeight={600}
            >
              {bar.label.length > 10 ? `${bar.label.slice(0, 10)}…` : bar.label}
            </text>

            {/* Background track */}
            <rect
              x={bar.x}
              y={bar.y}
              width={barAreaWidth}
              height={BAR_HEIGHT}
              rx={6}
              fill="var(--activity-chart-grid)"
            />

            {/* Value bar */}
            <m.rect
              x={bar.x}
              y={bar.y}
              height={BAR_HEIGHT}
              rx={6}
              fill={colorVar}
              initial={reduce ? { width: bar.width } : { width: 0 }}
              animate={{ width: bar.width }}
              transition={{
                duration: reduce ? 0 : motionTokens.durationLazy,
                delay: reduce ? 0 : i * 0.08,
                ease: "easeOut",
              }}
            />

            {/* Value text */}
            <text
              x={bar.x + barAreaWidth + 8}
              y={bar.y + BAR_HEIGHT / 2 + 4}
              textAnchor="start"
              fill="var(--text-primary)"
              fontSize={12}
              fontWeight={700}
            >
              {bar.max ? `${bar.value.toFixed(1)}/${bar.max}` : bar.value.toFixed(1)}
            </text>
          </g>
        ))}
      </svg>

      {/*
        Wave 112 SW4 — sr-only data table mirror (WCAG 1.1.1 + 1.3.1).
        SVG carries the chart purpose, table carries the values for AT.
      */}
      <table className="sr-only">
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            <th scope="col">{t("activity:charts.tableHeaders.subject")}</th>
            <th scope="col">{t("activity:charts.tableHeaders.value")}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((bar) => (
            <tr key={bar.label}>
              <th scope="row">{bar.label}</th>
              <td>{bar.max ? `${bar.value.toFixed(1)} / ${bar.max}` : bar.value.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
