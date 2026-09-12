import { afterEach, describe, expect, it, vi } from "vitest"
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
  afterEach(() => {
    vi.useRealTimers()
  })

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

  it("renders exact heat levels, boundaries, labels, and legend semantics", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityHeatmap
          ariaLabel="Detailed activity heatmap"
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

    expect(screen.getByLabelText("Detailed activity heatmap")).toBeInTheDocument()
    const cells = document.querySelectorAll<HTMLElement>(".activity-heatmap-cell[title]")
    expect(cells).toHaveLength(30)
    const populatedCells = [...cells].filter(
      (cell) => cell.style.backgroundColor !== "var(--activity-heat-0)"
    )
    expect(populatedCells).toHaveLength(4)
    expect(populatedCells.map((cell) => cell.style.backgroundColor)).toEqual(
      expect.arrayContaining([
        "var(--activity-heat-4)",
        "var(--activity-heat-1)",
        "var(--activity-heat-2)",
        "var(--activity-heat-3)",
      ])
    )
    expect(populatedCells.map((cell) => cell.getAttribute("aria-label"))).toEqual(
      expect.arrayContaining([
        expect.stringContaining(todayIso()),
        expect.stringContaining(dateOffset(-1)),
        expect.stringContaining(dateOffset(-2)),
        expect.stringContaining(dateOffset(-3)),
      ])
    )

    const legend = screen.getAllByRole("img").filter((element) => !element.hasAttribute("title"))
    expect(legend).toHaveLength(5)
    expect(legend.map((element) => element.getAttribute("aria-label"))).toEqual([
      expect.stringContaining("0"),
      expect.stringContaining("1"),
      expect.stringContaining("2"),
      expect.stringContaining("3"),
      expect.stringContaining("4"),
    ])
  })

  it("normalizes today to midnight and includes both date-range boundaries", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2024-01-07T15:12:00")) // Sunday with a non-midnight clock
    const offsetDate = (offset: number): string => {
      const date = new Date()
      date.setDate(date.getDate() + offset)
      const year = date.getFullYear()
      const month = String(date.getMonth() + 1).padStart(2, "0")
      const day = String(date.getDate()).padStart(2, "0")
      return `${year}-${month}-${day}`
    }

    const { container } = await renderWithRouter({
      ui: () => (
        <ActivityHeatmap
          ariaLabel="Sunday activity heatmap"
          period="30d"
          data={
            new Map([
              [offsetDate(0), 2],
              [offsetDate(-29), 1],
              [offsetDate(-30), 4], // outside the inclusive range
            ])
          }
        />
      ),
      authProvider: false,
    })

    const cells = container.querySelectorAll<HTMLElement>(".activity-heatmap-cell[title]")
    expect(cells).toHaveLength(30)
    const populatedCells = [...cells].filter(
      (cell) => cell.style.backgroundColor !== "var(--activity-heat-0)"
    )
    expect(populatedCells).toHaveLength(2)
    expect(populatedCells.map((cell) => cell.getAttribute("title"))).toEqual(
      expect.arrayContaining([
        expect.stringContaining(offsetDate(0)),
        expect.stringContaining(offsetDate(-29)),
      ])
    )
    expect(populatedCells.map((cell) => cell.style.backgroundColor)).toEqual(
      expect.arrayContaining(["var(--activity-heat-2)", "var(--activity-heat-1)"])
    )

    const grid = container.querySelector<HTMLElement>(".inline-grid")
    expect(grid?.style.gridTemplateRows).toBe("auto repeat(7, 1fr)")
    expect(grid?.style.gridTemplateColumns).toBe("auto repeat(5, 1fr)")
  })
})
