import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Card } from "@/components/ui/Card"

describe("Card mutation contracts", () => {
  it("renders the default surface, forwards DOM props, style, children, and className", () => {
    render(
      <Card
        data-testid="card"
        aria-label="Record card"
        className="custom-card"
        style={{ minHeight: "10px" }}
      >
        <span>Card content</span>
      </Card>
    )

    const card = screen.getByTestId("card")
    expect(card.tagName).toBe("DIV")
    expect(card).toHaveAttribute("aria-label", "Record card")
    expect(card).toHaveClass(
      "relative",
      "flex",
      "flex-col",
      "rounded-xl",
      "border",
      "border-border-subtle",
      "bg-(--bg-surface)",
      "text-text-primary",
      "shadow-surface",
      "transition-premium",
      "p-4",
      "custom-card"
    )
    expect(card).toHaveStyle({ minHeight: "10px" })
    expect(screen.getByText("Card content")).toBeInTheDocument()
  })

  it.each([
    ["none", "p-0"],
    ["sm", "p-3"],
    ["md", "p-4"],
    ["lg", "p-6"],
  ] as const)("applies the %s padding variant", (padding, expectedClass) => {
    render(
      <Card data-testid={`card-${padding}`} padding={padding}>
        {padding}
      </Card>
    )

    const card = screen.getByTestId(`card-${padding}`)
    expect(card).toHaveClass(expectedClass)
    const otherPaddingClasses = ["p-0", "p-3", "p-4", "p-6"].filter(
      (candidate) => candidate !== expectedClass
    )
    expect(card).not.toHaveClass(...otherPaddingClasses)
  })

  it("adds the complete hoverable state and keeps the non-hoverable state inert", () => {
    const { rerender } = render(<Card data-testid="card" hoverable />)
    const card = screen.getByTestId("card")
    expect(card).toHaveClass(
      "hover:-translate-y-1.5",
      "hover:scale-hover-lift",
      "hover:shadow-premium-lift",
      "focus-ring-premium",
      "motion-reduce:hover:translate-y-0",
      "motion-reduce:hover:scale-100",
      "motion-reduce:transition-shadow"
    )

    rerender(<Card data-testid="card" hoverable={false} />)
    expect(card).not.toHaveClass(
      "hover:-translate-y-1.5",
      "hover:scale-hover-lift",
      "hover:shadow-premium-lift",
      "focus-ring-premium",
      "motion-reduce:hover:translate-y-0",
      "motion-reduce:hover:scale-100",
      "motion-reduce:transition-shadow"
    )
  })

  it("supports a semantic component and exposes the diagnostic display name", () => {
    render(
      <Card as="article" data-testid="article-card" padding="lg" hoverable>
        Article
      </Card>
    )

    const card = screen.getByTestId("article-card")
    expect(card.tagName).toBe("ARTICLE")
    expect(card).toHaveClass("p-6", "hover:scale-hover-lift")
    expect(Card.displayName).toBe("Card")
  })
})
