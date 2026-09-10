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

  it("preserves slot geometry and prefers a real image when both source and fallback exist", () => {
    render(
      <ContentCard data-testid="root" className="root-custom">
        <ContentCard.Media
          src="https://img.example/cover.jpg"
          alt="cover"
          aspectRatio="4/3"
          className="media-custom"
          fallback={<span>should not replace image</span>}
        />
        <ContentCard.Header data-testid="header">
          <ContentCard.Title>Card title</ContentCard.Title>
          <ContentCard.Actions data-testid="actions">Actions</ContentCard.Actions>
        </ContentCard.Header>
        <ContentCard.Body data-testid="body">Body</ContentCard.Body>
        <ContentCard.Meta data-testid="meta">Meta</ContentCard.Meta>
        <ContentCard.Footer data-testid="footer">Footer</ContentCard.Footer>
      </ContentCard>
    )

    expect(screen.getByTestId("root")).toHaveClass("overflow-hidden", "root-custom")
    const media = document.querySelector(".media-custom")
    expect(media).toHaveClass("relative", "w-full", "overflow-hidden")
    expect(media).toHaveStyle({ aspectRatio: "4/3" })
    expect(screen.getByRole("img", { name: "cover" })).toBeInTheDocument()
    expect(screen.queryByText("should not replace image")).not.toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Card title", level: 3 })).toHaveClass(
      "line-clamp-2",
      "text-lg",
      "font-semibold"
    )
    expect(screen.getByTestId("header")).toHaveClass(
      "flex",
      "items-start",
      "justify-between",
      "gap-2",
      "px-4",
      "pt-4"
    )
    expect(screen.getByTestId("actions")).toHaveClass("shrink-0")
    expect(screen.getByTestId("body")).toHaveClass(
      "flex-1",
      "px-4",
      "py-3",
      "text-sm",
      "text-(--text-secondary)"
    )
    expect(screen.getByTestId("meta")).toHaveClass(
      "flex",
      "flex-wrap",
      "items-center",
      "gap-2",
      "px-4",
      "pb-2",
      "text-xs"
    )
    expect(screen.getByTestId("footer")).toHaveClass(
      "flex",
      "items-center",
      "gap-3",
      "border-t",
      "border-border-subtle",
      "px-4",
      "py-3"
    )
  })

  it("renders the fallback branch with the documented card media shell", () => {
    render(
      <ContentCard>
        <ContentCard.Media className="fallback-media" fallback={<span>Empty</span>} />
      </ContentCard>
    )

    const media = document.querySelector(".fallback-media")
    expect(media).toHaveClass("relative", "w-full", "bg-glass")
    expect(media).toHaveStyle({ aspectRatio: "16/9" })
    expect(screen.getByText("Empty")).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("keeps compound display names and the context default observable", () => {
    const Probe = () => {
      const context = useContentCardContext()
      return <span data-testid="context-default">{String(context.isHovered)}</span>
    }

    render(<Probe />)
    expect(screen.getByTestId("context-default")).toHaveTextContent("false")
    expect(ContentCard.displayName).toBe("ContentCard")
    expect(ContentCard.Media.displayName).toBe("ContentCard.Media")
    expect(ContentCard.Header.displayName).toBe("ContentCard.Header")
    expect(ContentCard.Title.displayName).toBe("ContentCard.Title")
    expect(ContentCard.Actions.displayName).toBe("ContentCard.Actions")
    expect(ContentCard.Body.displayName).toBe("ContentCard.Body")
    expect(ContentCard.Footer.displayName).toBe("ContentCard.Footer")
    expect(ContentCard.Meta.displayName).toBe("ContentCard.Meta")
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
