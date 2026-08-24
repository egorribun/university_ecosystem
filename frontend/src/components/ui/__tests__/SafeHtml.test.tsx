import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

const sanitize = vi.hoisted(() => vi.fn<(html: string) => string | null>())

vi.mock("wasm-sanitizer", () => ({ sanitize_rich_text: sanitize }))

import SafeHtml from "@/components/ui/SafeHtml"

// wasm-sanitizer is initialized in setupTests.ts. Assertions stay robust whether
// the sanitizer renders the cleaned <div> or the regex text-only fallback path —
// in both cases the visible text content is identical.

describe("SafeHtml", () => {
  beforeEach(() => {
    sanitize.mockReset().mockImplementation((html) => html)
  })

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

  it("uses the text-only fallback while the WASM sanitizer is unavailable", () => {
    sanitize.mockImplementation(() => {
      throw new Error("WASM not initialized")
    })

    render(<SafeHtml html="<strong>Still readable</strong>" />)
    expect(screen.getByText("Still readable")).toBeInTheDocument()
  })

  it.each(["<script>alert(1)</script><p>Safe text</p>", '<p onclick="boom()">Safe text</p>'])(
    "fails closed when sanitized output still contains an injection pattern",
    (maliciousOutput) => {
      sanitize.mockReturnValue(maliciousOutput)

      const { container } = render(<SafeHtml html="<p>Safe text</p>" className="safe-text" />)
      expect(container.querySelector("span.safe-text")).toHaveTextContent("Safe text")
      expect(container.querySelector("script")).not.toBeInTheDocument()
    }
  )
})
