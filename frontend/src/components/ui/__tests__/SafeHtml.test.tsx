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

describe("SafeHtml rendering paths", () => {
  beforeEach(() => {
    sanitize.mockReset().mockImplementation((html) => html)
  })

  it("renders the sanitizer output as markup, not as a text fallback", () => {
    sanitize.mockReturnValue("<p><strong>Bold</strong> text</p>")
    const { container } = render(<SafeHtml html="<p>raw</p>" className="rich" />)

    expect(sanitize).toHaveBeenCalledWith("<p>raw</p>")
    const root = container.querySelector("div.rich")
    expect(root?.innerHTML).toBe("<p><strong>Bold</strong> text</p>")
    expect(container.querySelector("span.rich")).toBeNull()
  })

  it("re-sanitizes when the html prop changes", () => {
    const { container, rerender } = render(<SafeHtml html="<p>first</p>" className="rich" />)
    rerender(<SafeHtml html="<p>second</p>" className="rich" />)

    expect(container.querySelector("div.rich")?.innerHTML).toBe("<p>second</p>")
    expect(sanitize).toHaveBeenLastCalledWith("<p>second</p>")
  })

  it("falls back to plain text when the sanitizer throws, without markup", () => {
    sanitize.mockImplementation(() => {
      throw new Error("WASM not initialized")
    })
    const { container } = render(<SafeHtml html="<b>Readable</b>" className="rich" />)

    expect(container.querySelector("span.rich")?.innerHTML).toBe("Readable")
    expect(container.querySelector("div.rich")).toBeNull()
  })

  it.each([
    ["a script tag with attributes", '<script src="x.js"></script><p>Safe</p>'],
    ["an upper-case script tag", "<SCRIPT>alert(1)</SCRIPT><p>Safe</p>"],
    ["a handler with a space before '='", '<p onclick ="boom()">Safe</p>'],
    ["a handler with a tab before '='", '<p onmouseover\t="boom()">Safe</p>'],
  ])("falls back to text when the output still contains %s", (_label, output) => {
    sanitize.mockReturnValue(output)
    const { container } = render(<SafeHtml html="<p>Safe</p>" className="rich" />)

    expect(container.querySelector("div.rich")).toBeNull()
    expect(container.querySelector("span.rich")).toHaveTextContent("Safe")
  })

  it.each([["a script-like word", "<p>scripting guide</p>"]])(
    "keeps markup for %s",
    (_label, output) => {
      sanitize.mockReturnValue(output)
      const { container } = render(<SafeHtml html="<p>x</p>" className="rich" />)

      expect(container.querySelector("div.rich")?.innerHTML).toBe(output)
    }
  )
})
