import { describe, expect, it } from "vitest"
import { fireEvent, screen } from "@testing-library/react"

import { ContentSummary } from "@/components/ui/ContentSummary"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("ContentSummary", () => {
  it("renders children only when there is no summary and not loading", async () => {
    await renderWithRouter({
      ui: () => (
        <ContentSummary summary={null}>
          <p>Full content body</p>
        </ContentSummary>
      ),
      authProvider: false,
    })
    expect(screen.getByText("Full content body")).toBeInTheDocument()
    // No expand/collapse control in the no-summary branch.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("shows the summary + a read-more toggle that expands the full content", async () => {
    await renderWithRouter({
      ui: () => (
        <ContentSummary summary="A short AI summary">
          <p>Full content body</p>
        </ContentSummary>
      ),
      authProvider: false,
    })
    expect(screen.getByText("A short AI summary")).toBeInTheDocument()
    const toggle = screen.getByRole("button")
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    // Collapsed → full content not rendered yet.
    expect(screen.queryByText("Full content body")).not.toBeInTheDocument()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("Full content body")).toBeInTheDocument()
  })

  it("renders the loading skeleton (no toggle) while loading", async () => {
    await renderWithRouter({
      ui: () => (
        <ContentSummary summary={null} loading>
          <p>Full content body</p>
        </ContentSummary>
      ),
      authProvider: false,
    })
    // loading branch → read-more button is gated out; children stay collapsed.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.queryByText("Full content body")).not.toBeInTheDocument()
  })
})
