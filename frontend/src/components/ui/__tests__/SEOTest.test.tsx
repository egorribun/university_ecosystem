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
})
