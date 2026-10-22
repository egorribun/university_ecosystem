import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import TrendChip from "../TrendChip"

describe("TrendChip", () => {
  it("renders nothing when the trend is absent", () => {
    const { container } = render(<TrendChip />)
    expect(container).toBeEmptyDOMElement()
  })

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "does not display a non-finite trend %s",
    (value) => {
      const { container } = render(<TrendChip value={value} />)
      expect(container).toBeEmptyDOMElement()
    }
  )

  it.each([
    [2.5, "+2.5%"],
    [0, "0.0%"],
    [-1.25, "-1.3%"],
  ])("formats %s as %s", (value, expected) => {
    render(<TrendChip value={value} />)
    expect(screen.getByText(expected)).toBeInTheDocument()
  })
})
