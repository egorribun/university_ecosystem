import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { StoryCircle } from "@/components/ui/StoryCircle"

describe("StoryCircle polymorphic and sizing branches", () => {
  it.each(["sm", "md", "lg"] as const)("renders the %s size", (size) => {
    render(<StoryCircle size={size}>avatar</StoryCircle>)
    const circle = screen.getByText("avatar").closest("div")
    for (const dimension of ["h", "w", "min-h", "min-w"]) {
      expect(circle).toHaveClass(`${dimension}-(--size-story-${size})`)
      for (const other of ["sm", "md", "lg"].filter((candidate) => candidate !== size)) {
        expect(circle).not.toHaveClass(`${dimension}-(--size-story-${other})`)
      }
    }
  })

  it.each([
    ["omitted", {}],
    ["undefined", { size: undefined }],
  ] as const)("uses medium diameter when size is %s", (_label, props) => {
    render(
      <StoryCircle as="button" aria-label="story" {...props}>
        avatar
      </StoryCircle>
    )
    const circle = screen.getByRole("button", { name: "story" })
    for (const dimension of ["h", "w", "min-h", "min-w"]) {
      expect(circle).toHaveClass(`${dimension}-(--size-story-md)`)
      expect(circle).not.toHaveClass(`${dimension}-(--size-story-sm)`)
      expect(circle).not.toHaveClass(`${dimension}-(--size-story-lg)`)
    }
  })

  it("supports a polymorphic element, numeric border, and style override", () => {
    render(
      <StoryCircle as="button" borderWidth={4} style={{ borderColor: "red" }} aria-label="story">
        open
      </StoryCircle>
    )
    const button = screen.getByRole("button", { name: "story" })
    expect(button.style.borderWidth).toBe("0.25rem")
    expect(button.style.borderColor).toBe("red")
    expect(button).toHaveTextContent("open")
  })

  it("accepts a string border width and custom class", () => {
    render(
      <StoryCircle borderWidth="thin" className="custom-story">
        content
      </StoryCircle>
    )
    expect(screen.getByText("content").closest("div")).toHaveClass("custom-story")
  })
})
