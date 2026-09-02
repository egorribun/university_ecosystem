import { useId, useMemo, type CSSProperties } from "react"
import { m } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { motion as motionTokens } from "@/theme/tokens"

type TrendPoint = { date: string; value: number }

type ActivityTrendChartProps = {
  data: TrendPoint[]
  colorVar?: string
  height?: number
  ariaLabel: string
  formatDate?: (date: string) => string
}

const PADDING = { top: 12, right: 12, bottom: 28, left: 36 }
const GRID_LINES = 4

export function ActivityTrendChart({
  data,
  colorVar = "var(--activity-present-accent)",
  height = 180,
  ariaLabel,
  formatDate,
}: ActivityTrendChartProps) {
  const { t } = useTranslation(["activity"])
  const reduce = useMediaQuery("(prefers-reduced-motion: reduce)")
  const gradientId = useId() // unique per instance (L3) — must be before early return

  const chartWidth = 400 // SVG viewBox width; responsive via CSS width:100%

  const { points, yLabels, xLabels, areaPath } = useMemo(() => {
    if (data.length < 2) return { points: "", yLabels: [], xLabels: [], areaPath: "" }

    const values = data.map((d) => d.value)
    const rawMin = Math.min(...values)
    const rawMax = Math.max(...values)
    const padding10 = (rawMax - rawMin) * 0.1 || 5
    const yMin = Math.max(0, Math.floor(rawMin - padding10))
    const yMax = Math.ceil(rawMax + padding10)

    const plotW = chartWidth - PADDING.left - PADDING.right
    const plotH = height - PADDING.top - PADDING.bottom

    const pts = data.map((d, i) => {
      const x = PADDING.left + (i / (data.length - 1)) * plotW
      const y = PADDING.top + plotH - ((d.value - yMin) / (yMax - yMin)) * plotH
      return { x, y }
    })

    const pointsStr = pts.map((p) => `${p.x},${p.y}`).join(" ")

    // Area fill path (line + close to bottom). Guarded by data.length >= 2 below.
    const firstX = pts[0]!.x
    const lastX = pts[pts.length - 1]!.x
    const bottomY = PADDING.top + plotH
    const areaPath = `M${firstX},${bottomY} L${pointsStr} L${lastX},${bottomY} Z`

    // Y-axis labels
    const yLabels = Array.from({ length: GRID_LINES + 1 }, (_, i) => {
      const val = yMin + ((yMax - yMin) * i) / GRID_LINES
      const y = PADDING.top + plotH - (i / GRID_LINES) * plotH
      return { label: Math.round(val).toString(), y }
    })

    // X-axis labels: first, middle, last
    const indices = [0, Math.floor(data.length / 2), data.length - 1]
    const xLabels = indices.map((idx) => {
      const datum = data[idx]!
      const pt = pts[idx]!
      return {
        label: formatDate?.(datum.date) ?? datum.date.slice(5),
        x: pt.x,
      }
    })

    return { points: pointsStr, yLabels, xLabels, areaPath }
  }, [data, height, formatDate])

  if (data.length < 2) {
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
        {t("activity:charts.attendanceTrend")}
      </h3>
      <svg
        viewBox={`0 0 ${chartWidth} ${height}`}
        className="block w-full"
        role="img"
        aria-label={ariaLabel}
        style={{ "--_chart-color": colorVar } as CSSProperties}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorVar} stopOpacity={0.2} />
            <stop offset="100%" stopColor={colorVar} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {yLabels.map((yl) => (
          <line
            key={yl.label}
            x1={PADDING.left}
            y1={yl.y}
            x2={chartWidth - PADDING.right}
            y2={yl.y}
            stroke="var(--activity-chart-grid)"
            strokeWidth={1}
          />
        ))}

        {/* Area fill */}
        <path d={areaPath} fill={`url(#${gradientId})`} />

        {/* Trend line */}
        <m.polyline
          points={points}
          fill="none"
          stroke={colorVar}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={reduce ? undefined : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: reduce ? 0 : motionTokens.durationLazy, ease: "easeOut" }}
        />

        {/* Y-axis labels */}
        {yLabels.map((yl) => (
          <text
            key={`y-${yl.label}`}
            x={PADDING.left - 6}
            y={yl.y + 4}
            textAnchor="end"
            fill="var(--activity-chart-label)"
            fontSize={10}
          >
            {yl.label}
          </text>
        ))}

        {/* X-axis labels */}
        {xLabels.map((xl) => (
          <text
            key={`x-${xl.label}`}
            x={xl.x}
            y={height - 4}
            textAnchor="middle"
            fill="var(--activity-chart-label)"
            fontSize={10}
          >
            {xl.label}
          </text>
        ))}
      </svg>

      {/*
        Wave 112 SW4 — sr-only data table for screen readers (WCAG 1.1.1
        non-text content + WCAG 1.3.1 info-and-relationships). The SVG above
        carries `role="img"` + `aria-label`, which announces the chart's
        purpose; this table announces the actual values.
      */}
      <table className="sr-only">
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            <th scope="col">{t("activity:chartTableHeaders.date")}</th>
            <th scope="col">{t("activity:chartTableHeaders.value")}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.date}>
              <th scope="row">{formatDate ? formatDate(point.date) : point.date}</th>
              <td>{point.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
