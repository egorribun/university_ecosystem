import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import DetailRow from "@/components/profile/DetailRow"

describe("DetailRow mutation contracts", () => {
  it.each([undefined, null, ""])("omits nullish or empty values (%s)", (value) => {
    const { container } = render(<DetailRow label="About" value={value} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders zero, false, and rich nodes instead of treating them as empty", () => {
    const { rerender } = render(<DetailRow label="Count" value={0} />)
    expect(screen.getByText("Count")).toBeInTheDocument()
    expect(screen.getByText("0")).toBeInTheDocument()

    rerender(<DetailRow label="Enabled" value={false} />)
    expect(screen.getByText("Enabled")).toBeInTheDocument()
    expect(screen.getByText("Enabled").nextElementSibling).toBeInTheDocument()

    rerender(<DetailRow label="About" value={<strong data-testid="rich-value">Details</strong>} />)
    expect(screen.getByTestId("rich-value")).toBeInTheDocument()
  })

  it("preserves the accessible visual row contract", () => {
    const { container } = render(<DetailRow label="Department" value="Computer Science" />)
    const row = container.firstElementChild!
    expect(row).toHaveClass(
      "profile-detail-row",
      "grid",
      "grid-cols-[0.75rem_1fr]",
      "items-start",
      "gap-2",
      "rounded-2xl",
      "border",
      "border-transparent",
      "transition-all",
      "duration-base"
    )
    expect(row.querySelector("span.font-bold")).toHaveTextContent("Department")
    expect(row.querySelector("span.font-medium")).toHaveTextContent("Computer Science")
  })
})
