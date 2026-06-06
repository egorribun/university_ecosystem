import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ActivityComparativeCard } from "@/features/activity/components/ActivityComparativeCard"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// See ActivityBarChart.test.tsx for the render-helper rationale. The comparative
// card renders formatValue(current) directly (namespace-independent) plus a
// sign-based trend branch (up / down / unchanged) and a NaN-guarded formatter.

describe("ActivityComparativeCard", () => {
  it("renders a positive delta as an up-trend", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityComparativeCard
          label="Attendance"
          current={85}
          previous={80}
          delta={5}
          format="percent"
          colorVar="var(--x)"
        />
      ),
      authProvider: false,
    })

    expect(screen.getByText("Attendance")).toBeInTheDocument()
    expect(screen.getByText("85%")).toBeInTheDocument() // formatValue(current, percent)
    expect(screen.getByText("+5.0%")).toBeInTheDocument() // positive delta gets a "+"
  })

  it("renders a negative delta as a down-trend", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityComparativeCard
          label="GPA"
          current={3.2}
          previous={4}
          delta={-0.8}
          format="decimal"
          colorVar="var(--x)"
        />
      ),
      authProvider: false,
    })

    expect(screen.getByText("3.2")).toBeInTheDocument() // decimal format
    expect(screen.getByText("-0.8%")).toBeInTheDocument() // negative delta (no "+")
  })

  it("uses the count format and NaN-guards the current value", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityComparativeCard
          label="Events"
          current={Number.NaN}
          previous={2}
          delta={0}
          format="count"
          colorVar="var(--x)"
        />
      ),
      authProvider: false,
    })

    // Number.isFinite(NaN) is false → guarded to 0 → count → "0".
    expect(screen.getByText("0")).toBeInTheDocument()
  })
})
