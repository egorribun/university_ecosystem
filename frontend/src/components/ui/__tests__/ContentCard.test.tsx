/**
 * Render coverage tests (testing session 10) for the ContentCard compound
 * component (all slots + the useContentCardContext hook + Media fallback /
 * image branches + Title polymorphic `as` + Badge variants). Plain render —
 * no router/providers needed.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ContentCard, useContentCardContext } from "@/components/ui/ContentCard"

describe("ContentCard slots", () => {
  it("renders the full compound composition", () => {
    render(
      <ContentCard>
        <ContentCard.Media src="https://img.example/x.jpg" alt="cover" />
        <ContentCard.Header>
          <ContentCard.Title>Card Title</ContentCard.Title>
          <ContentCard.Actions>
            <button type="button">menu</button>
          </ContentCard.Actions>
        </ContentCard.Header>
        <ContentCard.Meta>
          <span>2026-06-01</span>
        </ContentCard.Meta>
        <ContentCard.Body>Body text</ContentCard.Body>
        <ContentCard.Footer>
          <ContentCard.Badge variant="success">Live</ContentCard.Badge>
        </ContentCard.Footer>
      </ContentCard>
    )
    expect(screen.getByText("Card Title")).toBeInTheDocument()
    expect(screen.getByText("Body text")).toBeInTheDocument()
    expect(screen.getByText("menu")).toBeInTheDocument()
    expect(screen.getByText("2026-06-01")).toBeInTheDocument()
    expect(screen.getByText("Live")).toBeInTheDocument()
  })

  it("Media renders the fallback node when src is absent", () => {
    render(
      <ContentCard>
        <ContentCard.Media src={undefined} fallback={<span>no image</span>} />
      </ContentCard>
    )
    expect(screen.getByText("no image")).toBeInTheDocument()
  })

  it("Title honours the polymorphic `as` prop", () => {
    render(
      <ContentCard>
        <ContentCard.Title as="h2">Heading Two</ContentCard.Title>
      </ContentCard>
    )
    expect(screen.getByRole("heading", { level: 2, name: "Heading Two" })).toBeInTheDocument()
  })

  it("Badge defaults to the default variant when none given", () => {
    render(
      <ContentCard>
        <ContentCard.Badge>Plain</ContentCard.Badge>
      </ContentCard>
    )
    const badge = screen.getByText("Plain")
    expect(badge.className).toContain("bg-(--bg-surface-hover)")
  })
})

describe("useContentCardContext", () => {
  it("returns the default context outside an explicit hover state", () => {
    const Probe = () => {
      const ctx = useContentCardContext()
      return <span data-testid="hover">{String(ctx.isHovered)}</span>
    }
    render(
      <ContentCard>
        <Probe />
      </ContentCard>
    )
    expect(screen.getByTestId("hover")).toHaveTextContent("false")
  })
})
