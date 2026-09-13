import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ContentCard } from "@/components/ui/ContentCard"

describe("ContentCard mutation contracts", () => {
  it("keeps the shared badge base classes for every status variant", () => {
    render(
      <div>
        <ContentCard.Badge data-testid="default-badge">Default</ContentCard.Badge>
        <ContentCard.Badge data-testid="success-badge" variant="success">
          Success
        </ContentCard.Badge>
        <ContentCard.Badge data-testid="warning-badge" variant="warning">
          Warning
        </ContentCard.Badge>
        <ContentCard.Badge data-testid="error-badge" variant="error">
          Error
        </ContentCard.Badge>
        <ContentCard.Badge data-testid="info-badge" variant="info">
          Info
        </ContentCard.Badge>
      </div>
    )

    for (const badge of screen.getAllByTestId(/badge$/)) {
      expect(badge).toHaveClass(
        "inline-flex",
        "items-center",
        "rounded-full",
        "px-2",
        "py-0.5",
        "text-xs",
        "font-medium"
      )
    }
  })

  it("keeps variant classes, custom classes, forwarded props, and display names", () => {
    render(
      <ContentCard.Badge
        data-testid="custom-badge"
        variant="success"
        className="custom-badge"
        aria-label="Published status"
      >
        Published
      </ContentCard.Badge>
    )

    const badge = screen.getByTestId("custom-badge")
    expect(badge).toHaveAttribute("aria-label", "Published status")
    expect(badge).toHaveClass("bg-success-bg", "text-success-text", "custom-badge")
    expect(ContentCard.Badge.displayName).toBe("ContentCard.Badge")
  })
})
