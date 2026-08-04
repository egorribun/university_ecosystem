import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => true,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { ActivityBarChart } from "../ActivityBarChart"

describe("ActivityBarChart defensive and reduced-motion branches", () => {
  it("handles non-finite values, long labels, explicit titles, and reduced motion", () => {
    render(
      <ActivityBarChart
        ariaLabel="Grade chart"
        title="Custom chart"
        data={[
          { label: "Very Long Subject Name", value: 3, max: 0 },
          { label: "Invalid", value: Number.NaN, max: Number.NaN },
        ]}
      />
    )

    expect(screen.getByText("Custom chart")).toBeInTheDocument()
    expect(screen.getByText("Very Long …")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "Grade chart" })).toBeInTheDocument()
    expect(screen.getAllByRole("row")).toHaveLength(3)
  })
})
