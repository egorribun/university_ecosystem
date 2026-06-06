import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ActivityBarChart } from "@/features/activity/components/ActivityBarChart"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// First render tests for features/activity/components (0 tests before this).
// Mounted via renderWithRouter — supplies LanguageProvider (useTranslation) +
// LazyMotion (framer-motion `m.*`), which these charts need. authProvider:false
// skips the real AuthProvider's useProfileSync /users/me fetch (the charts read
// no auth). Assertions target the a11y surface (role="img" + the passed
// ariaLabel, the sr-only <table>) so they're independent of which i18n namespace
// is loaded in the test env.

describe("ActivityBarChart", () => {
  it("renders the chart svg + sr-only data table when data is present", async () => {
    await renderWithRouter({
      ui: () => (
        <ActivityBarChart
          ariaLabel="Grades by subject"
          data={[
            { label: "Math", value: 4.5, max: 5 },
            { label: "Physics", value: 3 },
          ]}
        />
      ),
      authProvider: false,
    })

    // SVG carries role="img" + the ariaLabel.
    expect(screen.getByRole("img", { name: "Grades by subject" })).toBeInTheDocument()

    // sr-only <table> mirror: 1 thead row + 1 row per datum.
    expect(screen.getAllByRole("row")).toHaveLength(3)

    // Value cell formatted with max ("x.x / max") — spaced form is unique to
    // the table (the SVG renders the no-space "4.5/5" variant).
    expect(screen.getByText("4.5 / 5")).toBeInTheDocument()
  })

  it("renders the empty state (no svg, no table) when data is empty", async () => {
    await renderWithRouter({
      ui: () => <ActivityBarChart ariaLabel="Empty" data={[]} />,
      authProvider: false,
    })

    expect(screen.queryByRole("img")).not.toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })
})
