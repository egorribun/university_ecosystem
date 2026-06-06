import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import SafeHtml from "@/components/ui/SafeHtml"

// wasm-sanitizer is initialized in setupTests.ts. Assertions stay robust whether
// the sanitizer renders the cleaned <div> or the regex text-only fallback path —
// in both cases the visible text content is identical.

describe("SafeHtml", () => {
  it("renders the text content of clean HTML", () => {
    render(<SafeHtml html="<p>Hello world</p>" />)
    expect(screen.getByText("Hello world")).toBeInTheDocument()
  })

  it("renders the fallback node when sanitized output is empty", () => {
    render(<SafeHtml html="" fallback={<span data-testid="fb">FB</span>} />)
    expect(screen.getByTestId("fb")).toBeInTheDocument()
  })

  it("renders a text-only span when empty with no fallback", () => {
    const { container } = render(<SafeHtml html="" className="so" />)
    expect(container.querySelector("span.so")).not.toBeNull()
  })
})
