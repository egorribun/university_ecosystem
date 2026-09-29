import { useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react"

import { useLanguage } from "@/contexts/LanguageContext"
import { ActivityHeatmap } from "@/features/activity/components/ActivityHeatmap"
import type { PeriodKey } from "@/features/activity/types"
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

// Wednesday 2024-03-13 with a non-midnight clock. For the 30-day period the
// inclusive range is Tue 2024-02-13 .. Wed 2024-03-13; the grid starts on the
// ISO Monday 2024-02-12 (one leading blank) and spans five weeks.
const WEDNESDAY = new Date(2024, 2, 13, 15, 12)

function gridOf(container: HTMLElement): HTMLElement {
  const grid = container.querySelector<HTMLElement>(".inline-grid")
  if (!grid) throw new Error("heatmap grid not rendered")
  return grid
}

function gridTexts(container: HTMLElement): string[] {
  return [...gridOf(container).children].map((child) => child.textContent ?? "")
}

/** Month header row (without the empty corner cell). */
function monthHeader(container: HTMLElement): string[] {
  const weeks = Number(
    /repeat\((\d+), 1fr\)$/u.exec(gridOf(container).style.gridTemplateColumns)?.[1]
  )
  return gridTexts(container).slice(1, 1 + weeks)
}

/** Day-label column: the first child of each of the seven day rows. */
function dayColumn(container: HTMLElement): string[] {
  const weeks = Number(
    /repeat\((\d+), 1fr\)$/u.exec(gridOf(container).style.gridTemplateColumns)?.[1]
  )
  const texts = gridTexts(container)
  return Array.from({ length: 7 }, (_, row) => {
    const text = texts[1 + weeks + row * (weeks + 1)]
    if (text === undefined) throw new Error(`heatmap day-label row ${row} not rendered`)
    return text
  })
}

function heatOf(date: string): string | null {
  const cell = document.querySelector<HTMLElement>(`[title^="${date}:"]`)
  return cell ? cell.style.backgroundColor : null
}

function monthName(locale: string, year: number, month: number): string {
  return new Intl.DateTimeFormat(locale, { month: "short" }).format(new Date(year, month, 1))
}

function weekdayName(locale: string, day: number): string {
  // 2024-01-01 is a Monday.
  return new Intl.DateTimeFormat(locale, { weekday: "short" }).format(new Date(2024, 0, day))
}

function Harness() {
  const { setLanguage } = useLanguage()
  const [period, setPeriod] = useState<PeriodKey>("30d")
  const [data, setData] = useState(() => new Map([["2024-03-13", 4]]))
  return (
    <>
      <button type="button" onClick={() => setPeriod("90d")}>
        period-90
      </button>
      <button
        type="button"
        onClick={() =>
          setData(
            new Map([
              ["2024-03-13", 4],
              ["2024-03-12", 16],
            ])
          )
        }
      >
        more-data
      </button>
      <button type="button" onClick={() => setLanguage("ru")}>
        russian
      </button>
      <ActivityHeatmap ariaLabel="Harness heatmap" period={period} data={data} />
    </>
  )
}

describe("ActivityHeatmap grid geometry and labels", () => {
  beforeEach(() => {
    window.localStorage.setItem("ue:language", "en")
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(WEDNESDAY)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("renders the translated title, legend text and exact legend swatches", async () => {
    await renderWithRouter({
      ui: () => <ActivityHeatmap ariaLabel="Legend heatmap" period="30d" data={new Map()} />,
      authProvider: false,
    })

    const card = screen.getByRole("group", { name: "Legend heatmap" })
    expect(within(card).getByRole("heading", { level: 3 })).toHaveTextContent("Activity Calendar")
    expect(within(card).getByText("Less")).toBeInTheDocument()
    expect(within(card).getByText("More")).toBeInTheDocument()

    const swatches = [0, 1, 2, 3, 4].map((level) =>
      within(card).getByRole("img", { name: `Activity level ${level}` })
    )
    expect(swatches.map((swatch) => swatch.style.backgroundColor)).toEqual([
      "var(--activity-heat-0)",
      "var(--activity-heat-1)",
      "var(--activity-heat-2)",
      "var(--activity-heat-3)",
      "var(--activity-heat-4)",
    ])
  })

  it("aligns the range to an ISO Monday and labels months at their first Monday", async () => {
    const { container } = await renderWithRouter({
      ui: () => <ActivityHeatmap ariaLabel="Aligned heatmap" period="30d" data={new Map()} />,
      authProvider: false,
    })

    const grid = gridOf(container)
    expect(grid.style.gridTemplateColumns).toBe("auto repeat(5, 1fr)")
    // corner + 5 month cells + 7 rows x (label + 5 weeks)
    expect(grid.children).toHaveLength(1 + 5 + 7 * 6)
    expect(monthHeader(container)).toEqual([
      monthName("en-US", 2024, 1),
      "",
      "",
      monthName("en-US", 2024, 2),
      "",
    ])
    expect(dayColumn(container)).toEqual([
      weekdayName("en-US", 1),
      "",
      weekdayName("en-US", 3),
      "",
      weekdayName("en-US", 5),
      "",
      "",
    ])

    const texts = gridTexts(container)
    // Monday row: the leading Monday 2024-02-12 is outside the range (blank),
    // then 02-19, 02-26, 03-04 and 03-11 are rendered day cells.
    const mondayRow = [...grid.children].slice(7, 12)
    expect(mondayRow[0]).not.toHaveAttribute("title")
    expect(mondayRow.slice(1).map((cell) => cell.getAttribute("title"))).toEqual([
      "2024-02-19: 0 activities",
      "2024-02-26: 0 activities",
      "2024-03-04: 0 activities",
      "2024-03-11: 0 activities",
    ])
    // Tuesday row starts exactly at the first in-range day.
    expect(grid.children[13]).toHaveAttribute("title", "2024-02-13: 0 activities")
    // Thursday of the last week is tomorrow and must stay blank.
    expect(grid.children[1 + 5 + 3 * 6 + 5]).not.toHaveAttribute("title")
    expect(texts.filter(Boolean)).toEqual([
      monthName("en-US", 2024, 1),
      monthName("en-US", 2024, 2),
      weekdayName("en-US", 1),
      weekdayName("en-US", 3),
      weekdayName("en-US", 5),
    ])
    expect(container.querySelectorAll(".activity-heatmap-cell[title]")).toHaveLength(30)
  })

  it("provides a localized accessible table of every in-range date and activity count", async () => {
    await renderWithRouter({ ui: Harness, authProvider: false })

    const table = screen.getByRole("table", { name: "Activity Calendar" })
    expect(table).toHaveClass("sr-only")
    expect(table).not.toHaveAttribute("aria-hidden")
    const headers = within(table).getAllByRole("columnheader")
    expect(headers.map((header) => header.textContent)).toEqual(["Date", "Activity"])
    headers.forEach((header) => expect(header).toHaveAttribute("scope", "col"))

    const rows = within(table).getAllByRole("row").slice(1)
    expect(rows).toHaveLength(30)
    const expectedDates = Array.from({ length: 30 }, (_, index) => {
      const date = new Date(2024, 1, 13 + index)
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
    })
    expect(
      rows.map((row) => {
        const date = within(row).getByRole("rowheader")
        expect(date).toHaveAttribute("scope", "row")
        return [date.textContent, within(row).getByRole("cell").textContent]
      })
    ).toEqual(expectedDates.map((date) => [date, date === "2024-03-13" ? "4" : "0"]))

    fireEvent.click(screen.getByRole("button", { name: "more-data" }))
    expect(
      within(within(table).getByRole("row", { name: "2024-03-12 16" })).getByRole("cell")
    ).toHaveTextContent("16")

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "russian" }))
    })
    await waitFor(() =>
      expect(screen.getByRole("table", { name: "Календарь активности" })).toBeInTheDocument()
    )
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent)
    ).toEqual(["Дата", "Активность"])
    expect(within(table).getAllByRole("row")).toHaveLength(31)

    fireEvent.click(screen.getByRole("button", { name: "period-90" }))
    expect(within(table).getAllByRole("row")).toHaveLength(91)
    expect(within(table).getAllByRole("rowheader")[0]).toHaveTextContent("2023-12-15")
  })

  it("maps counts to exact heat levels relative to the maximum count", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityHeatmap
          ariaLabel="Levels heatmap"
          period="30d"
          data={
            new Map([
              ["2024-03-13", 4],
              ["2024-03-12", 3],
              ["2024-03-11", 2],
              ["2024-03-10", 1],
              ["2024-02-13", 1],
              ["2024-02-12", 4], // outside the range but still part of the data
            ])
          }
        />
      ),
      authProvider: false,
    })

    expect(heatOf("2024-03-13")).toBe("var(--activity-heat-4)")
    expect(heatOf("2024-03-12")).toBe("var(--activity-heat-3)")
    expect(heatOf("2024-03-11")).toBe("var(--activity-heat-2)")
    expect(heatOf("2024-03-10")).toBe("var(--activity-heat-1)")
    expect(heatOf("2024-02-13")).toBe("var(--activity-heat-1)")
    expect(heatOf("2024-02-14")).toBe("var(--activity-heat-0)")
    expect(heatOf("2024-02-12")).toBeNull()
    expect(screen.getByRole("img", { name: "2024-03-12: 3 activities" })).toHaveAttribute(
      "title",
      "2024-03-12: 3 activities"
    )
  })

  it("recomputes levels, grid and labels when data, period and language change", async () => {
    const { container } = await renderWithRouter({ ui: Harness, authProvider: false })

    expect(heatOf("2024-03-13")).toBe("var(--activity-heat-4)")
    fireEvent.click(screen.getByRole("button", { name: "more-data" }))
    expect(heatOf("2024-03-12")).toBe("var(--activity-heat-4)")
    expect(heatOf("2024-03-13")).toBe("var(--activity-heat-1)")

    fireEvent.click(screen.getByRole("button", { name: "period-90" }))
    // 90 days: Fri 2023-12-15 .. 2024-03-13, grid from Mon 2023-12-11, 14 weeks.
    expect(gridOf(container).style.gridTemplateColumns).toBe("auto repeat(14, 1fr)")
    expect(container.querySelectorAll(".activity-heatmap-cell[title]")).toHaveLength(90)
    expect(monthHeader(container)).toEqual([
      monthName("en-US", 2023, 11),
      "",
      "",
      monthName("en-US", 2024, 0),
      "",
      "",
      "",
      "",
      monthName("en-US", 2024, 1),
      "",
      "",
      "",
      monthName("en-US", 2024, 2),
      "",
    ])

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "russian" }))
    })
    await waitFor(() => expect(dayColumn(container)[0]).toBe(weekdayName("ru-RU", 1)))
    expect(dayColumn(container)).toEqual([
      weekdayName("ru-RU", 1),
      "",
      weekdayName("ru-RU", 3),
      "",
      weekdayName("ru-RU", 5),
      "",
      "",
    ])
    expect(monthHeader(container)[0]).toBe(monthName("ru-RU", 2023, 11))
  })
})
