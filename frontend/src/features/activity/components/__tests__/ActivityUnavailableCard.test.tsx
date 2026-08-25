import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { ActivityUnavailableCard } from "../ActivityUnavailableCard"

describe("ActivityUnavailableCard", () => {
  it("labels the missing feed without presenting a numeric value", () => {
    render(<ActivityUnavailableCard title="Attendance" />)
    expect(screen.getByLabelText("Attendance")).toHaveTextContent(
      "activity:partial.feedUnavailable"
    )
    expect(screen.queryByText("0")).not.toBeInTheDocument()
  })
})
