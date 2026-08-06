import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ActivityHeatmap } from "@/features/activity/components/ActivityHeatmap"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// See ActivityBarChart.test.tsx for the render-helper rationale. The heatmap also
// reads useLanguage() (LanguageProvider, supplied by renderWithRouter). It has no
// empty-state branch — it always renders the date grid + a 5-swatch legend, each
// cell/swatch carrying role="img".

function todayIso(): string {
  const today = new Date()
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, "0")
  const d = String(today.getDate()).padStart(2, "0")
  return `${y}-${m}-${d}`
}

function dateOffset(offset: number): string {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, "0")
  const d = String(date.getDate()).padStart(2, "0")
  return `${y}-${m}-${d}`
}

describe("ActivityHeatmap", () => {
  it("renders heat cells + legend swatches as role=img", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityHeatmap
          ariaLabel="Activity heatmap"
          period="30d"
          data={
            new Map([
              [todayIso(), 4],
              [dateOffset(-1), 1],
              [dateOffset(-2), 2],
              [dateOffset(-3), 3],
            ])
          }
        />
      ),
      authProvider: false,
    })

    // Legend = 5 swatches; in-range day cells add more. All role="img".
    expect(screen.getAllByRole("img").length).toBeGreaterThanOrEqual(5)
  })

  it("renders without throwing when the data map is empty", async () => {
    await renderWithRouter({
      ui: () => <ActivityHeatmap ariaLabel="Empty heatmap" period="30d" data={new Map()} />,
      authProvider: false,
    })

    expect(screen.getAllByRole("img").length).toBeGreaterThanOrEqual(5)
  })
})
