import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { SEO } from "../SEO"

describe("SEO Component", () => {
  it("renders with title only", () => {
    render(<SEO title="Home" />)
    expect(document.title).toBe("Home | University Ecosystem")
  })

  it("renders with all props (title, description, image, type)", () => {
    render(
      <SEO
        title="Custom Page"
        description="This is a test description"
        image="https://example.com/image.png"
        type="article"
      />
    )
    expect(document.title).toBe("Custom Page | University Ecosystem")
  })

  it("renders every social metadata field with the supplied values", () => {
    render(
      <SEO
        title="Article"
        description="A complete description"
        image="https://example.com/cover.png"
        type="article"
      />
    )

    expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      "A complete description"
    )
    expect(document.head.querySelector('meta[property="og:type"]')).toHaveAttribute(
      "content",
      "article"
    )
    expect(document.head.querySelector('meta[property="og:description"]')).toHaveAttribute(
      "content",
      "A complete description"
    )
    expect(document.head.querySelector('meta[property="og:image"]')).toHaveAttribute(
      "content",
      "https://example.com/cover.png"
    )
    expect(document.head.querySelector('meta[name="twitter:description"]')).toHaveAttribute(
      "content",
      "A complete description"
    )
    expect(document.head.querySelector('meta[name="twitter:image"]')).toHaveAttribute(
      "content",
      "https://example.com/cover.png"
    )
    expect(document.head.querySelector('meta[name="twitter:card"]')).toHaveAttribute(
      "content",
      "summary_large_image"
    )
  })

  it("omits optional metadata when description and image are absent", () => {
    render(<SEO title="Minimal" />)

    expect(document.head.querySelector('meta[name="description"]')).not.toBeInTheDocument()
    expect(document.head.querySelector('meta[property="og:description"]')).not.toBeInTheDocument()
    expect(document.head.querySelector('meta[property="og:image"]')).not.toBeInTheDocument()
    expect(document.head.querySelector('meta[name="twitter:description"]')).not.toBeInTheDocument()
    expect(document.head.querySelector('meta[name="twitter:image"]')).not.toBeInTheDocument()
  })

  it("defaults the Open Graph type to website", () => {
    render(<SEO title="Home" />)

    expect(document.head.querySelector('meta[property="og:type"]')).toHaveAttribute(
      "content",
      "website"
    )
  })
})
