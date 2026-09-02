import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mediaMock } = vi.hoisted(() => ({ mediaMock: vi.fn() }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: (query: string) => mediaMock(query) }))

let NewsDetailBody: (typeof import("@/components/news/NewsDetailBody"))["NewsDetailBody"]

const MARKDOWN_WITH_TOC = `## Background

The university opened a new interdisciplinary lab this spring.

## Methodology

We surveyed enrolment data across three faculties.

## Key Findings

Enrolment rose by a double-digit margin year over year.`

const PLAIN_TEXT = `The new facility is the largest investment in a decade.

It will host robotics, AI, and data-science tracks under one roof.`

describe("NewsDetailBody", () => {
  beforeEach(async () => {
    vi.resetModules()
    const newsDetailBodyModule = await import("@/components/news/NewsDetailBody")
    NewsDetailBody = newsDetailBodyModule.NewsDetailBody
    mediaMock.mockReset()
    mediaMock.mockImplementation((query: string) => query === "(min-width: 1024px)")
  })

  it("renders markdown headings and the table of contents on desktop", () => {
    const { container } = render(<NewsDetailBody content={MARKDOWN_WITH_TOC} />)
    expect(screen.getByRole("heading", { name: "Background" })).toHaveAttribute("id", "background")
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
    expect(container.querySelector("section")).toHaveClass(
      "glass-layer-surface",
      "glass-noise",
      "flex",
      "gap-8"
    )
  })

  it("does not reserve table-of-contents layout for fewer than three headings", () => {
    const { container } = render(
      <NewsDetailBody content={"## First heading\n\n## Second heading"} />
    )

    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
    expect(container.querySelector("section")).not.toHaveClass("flex")
    expect(container.querySelector("section")).not.toHaveClass("gap-8")
  })

  it("recognizes only line-start heading, list, fence, and rule markers", () => {
    const { container } = render(
      <NewsDetailBody
        content={`Inline # marker
Inline - marker
Inline 1. marker
Inline \`\`\` marker
Inline ---
--- trailing

> Preserved quote`}
      />
    )

    expect(container.querySelector("blockquote.news-pullquote")).toHaveTextContent(
      "Preserved quote"
    )
  })

  it("recognizes a heading only when its marker is followed by whitespace", () => {
    render(<NewsDetailBody content="# Campus life" />)

    expect(screen.getByRole("heading", { name: "Campus life" })).toBeInTheDocument()
  })

  it("recognizes multi-character emphasis", () => {
    const { container } = render(<NewsDetailBody content="*Campus life*" />)

    expect(container.querySelector("em")).toHaveTextContent("Campus life")
  })

  it("renders multi-character bold Markdown", () => {
    const { container } = render(<NewsDetailBody content="**Campus life**" />)

    expect(container.querySelector("strong")).toHaveTextContent("Campus life")
  })

  it("does not mistake an asterisk-only run for bold text", () => {
    const { container } = render(<NewsDetailBody content={"*****\n\n> Preserved quote"} />)

    expect(container.querySelector("blockquote.news-pullquote")).toHaveTextContent(
      "Preserved quote"
    )
  })

  it("recognizes a line-start unordered list marker followed by whitespace", () => {
    render(<NewsDetailBody content={"- First item\n- Second item"} />)

    expect(screen.getAllByRole("listitem")).toHaveLength(2)
  })

  it("recognizes multi-digit ordered list markers followed by whitespace", () => {
    render(<NewsDetailBody content="12. Twelfth item" />)

    expect(screen.getByRole("listitem")).toHaveTextContent("Twelfth item")
  })

  it("recognizes links with multi-character labels and destinations", () => {
    render(<NewsDetailBody content="[Docs portal](https://example.edu/docs)" />)

    expect(screen.getByRole("link", { name: "Docs portal" })).toHaveAttribute(
      "href",
      "https://example.edu/docs"
    )
  })

  it("renders GFM tables with multi-character cells", () => {
    const { container } = render(
      <NewsDetailBody
        content={`| Alpha column | Beta column |
| --- | --- |
| Alpha value | Beta value |`}
      />
    )

    expect(container.querySelector("table")).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Alpha column" })).toBeInTheDocument()
  })

  it("recognizes horizontal rules longer than three hyphens", () => {
    render(<NewsDetailBody content="----" />)

    expect(screen.getByRole("separator")).toBeInTheDocument()
  })

  it("keeps soft Markdown line breaks inside one paragraph", () => {
    const { container } = render(
      <NewsDetailBody content={"# Introduction\n\nFirst line\nSecond line"} />
    )

    expect(container.querySelector(".news-article-body br")).not.toBeInTheDocument()
    expect(screen.getByText("First line Second line")).toBeInTheDocument()
  })

  it("renders plain-text content as paragraphs", () => {
    const { container } = render(<NewsDetailBody content={PLAIN_TEXT} />)
    expect(
      screen.getByText("The new facility is the largest investment in a decade.")
    ).toBeInTheDocument()
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
    expect(container.querySelector(".news-article-body")?.textContent).toBe(
      "The new facility is the largest investment in a decade." +
        "It will host robotics, AI, and data-science tracks under one roof."
    )
  })

  it("keeps single newlines within trimmed legacy paragraphs and skips blank chunks", () => {
    const { container } = render(
      <NewsDetailBody content={"  First line\nSecond line  \n\n   \n\nThird paragraph  \n\n "} />
    )
    const paragraphs = container.querySelectorAll(".news-article-body p")

    expect(paragraphs).toHaveLength(2)
    expect(paragraphs[0]?.textContent).toBe("First line\nSecond line")
    expect(paragraphs[1]?.textContent).toBe("Third paragraph")
  })

  it("escapes every HTML-significant character in legacy text", () => {
    const { container } = render(
      <NewsDetailBody content={'Fish & <chips> are "today\'s" special'} />
    )
    const paragraph = container.querySelector(".news-article-body p")

    expect(paragraph?.textContent).toBe('Fish & <chips> are "today\'s" special')
    expect(container.querySelector("chips")).not.toBeInTheDocument()
  })

  it("renders nothing in the body for empty content without throwing", () => {
    expect(() => render(<NewsDetailBody content="" />)).not.toThrow()
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
  })

  it("renders pull quotes and skips blank legacy paragraphs", () => {
    const { container } = render(
      <NewsDetailBody content={"\n\n>   Safety > first\n\n\nPlain paragraph"} />
    )
    expect(container.querySelector("blockquote.news-pullquote")?.textContent).toBe("Safety > first")
    expect(screen.getByText("Plain paragraph")).toBeInTheDocument()
  })

  it("recomputes rendered HTML when article content changes", () => {
    const { rerender } = render(<NewsDetailBody content="First article" />)
    expect(screen.getByText("First article")).toBeInTheDocument()

    rerender(<NewsDetailBody content="Second article" />)

    expect(screen.queryByText("First article")).not.toBeInTheDocument()
    expect(screen.getByText("Second article")).toBeInTheDocument()
  })

  it("places the table of contents below the article on mobile", () => {
    mediaMock.mockReturnValue(false)
    const { container } = render(<NewsDetailBody content={MARKDOWN_WITH_TOC} />)
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
    expect(container.querySelector("section")).not.toHaveClass("flex")
    expect(container.querySelector("section")).not.toHaveClass("gap-8")
  })
})
