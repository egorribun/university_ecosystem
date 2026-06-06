import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ActivityTrendChart } from "@/features/activity/components/ActivityTrendChart"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// See ActivityBarChart.test.tsx for the render-helper rationale. The trend chart
// needs >= 2 points to draw; fewer falls back to the empty state.

describe("ActivityTrendChart", () => {
  it("renders the trend svg + sr-only table with >= 2 points", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityTrendChart
          ariaLabel="Attendance trend"
          data={[
            { date: "2026-06-01", value: 80 },
            { date: "2026-06-02", value: 90 },
            { date: "2026-06-03", value: 85 },
          ]}
        />
      ),
      authProvider: false,
    })

    expect(screen.getByRole("img", { name: "Attendance trend" })).toBeInTheDocument()

    // sr-only <table>: 1 thead row + 1 row per point.
    expect(screen.getAllByRole("row")).toHaveLength(4)

    // Full ISO date is unique to the table's row header (the SVG x-axis renders
    // the truncated "MM-DD" form).
    expect(screen.getByText("2026-06-02")).toBeInTheDocument()

    // The table cell carries the raw value.
    expect(screen.getByText("90")).toBeInTheDocument()
  })

  it("applies formatDate to the labels when provided", async () => {
    // 3 points so the SVG x-axis indices [first, middle, last] stay distinct —
    // with exactly 2 points they collapse to [0,1,1] and the component emits a
    // duplicate-React-key warning (a pre-existing edge case, out of scope here).
    await renderWithRouter({
      ui: () => (
        <ActivityTrendChart
          ariaLabel="Trend"
          formatDate={(d) => `D:${d.slice(-2)}`}
          data={[
            { date: "2026-06-01", value: 80 },
            { date: "2026-06-02", value: 90 },
            { date: "2026-06-03", value: 85 },
          ]}
        />
      ),
      authProvider: false,
    })

    // formatDate output appears in both the SVG x-axis and the sr-only table.
    expect(screen.getAllByText("D:01").length).toBeGreaterThanOrEqual(1)
  })

  it("renders the empty state (no svg) with fewer than 2 points", async () => {
    await renderWithRouter({
      ui: () => <ActivityTrendChart ariaLabel="Empty" data={[{ date: "2026-06-01", value: 1 }]} />,
      authProvider: false,
    })

    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })
})
