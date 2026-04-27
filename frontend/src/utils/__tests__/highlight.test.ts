import { describe, expect, it } from "vitest"
import { renderHighlight, renderHighlightFragments } from "../highlight"

// Sentinel constants mirror those in highlight.ts
const MARK_OPEN = "\x00MARK_OPEN\x00"
const MARK_CLOSE = "\x00MARK_CLOSE\x00"

describe("renderHighlight", () => {
  // ---------------------------------------------------------------------------
  // Basic sentinel replacement
  // ---------------------------------------------------------------------------
  it("wraps marked term in <mark> tags", () => {
    const raw = `university ${MARK_OPEN}festival${MARK_CLOSE} 2025`
    expect(renderHighlight(raw)).toBe("university <mark>festival</mark> 2025")
  })

  it("handles multiple highlighted terms in one string", () => {
    const raw = `${MARK_OPEN}hello${MARK_CLOSE} and ${MARK_OPEN}world${MARK_CLOSE}`
    expect(renderHighlight(raw)).toBe("<mark>hello</mark> and <mark>world</mark>")
  })

  it("returns plain text unchanged when no sentinels are present", () => {
    expect(renderHighlight("plain text")).toBe("plain text")
  })

  // ---------------------------------------------------------------------------
  // XSS prevention — HTML in document content must be escaped
  // ---------------------------------------------------------------------------
  it("escapes < and > in document content", () => {
    const raw = "look at <script>alert(1)</script> here"
    const result = renderHighlight(raw)
    expect(result).not.toContain("<script>")
    expect(result).toContain("&lt;script&gt;")
  })

  it("escapes & in document content", () => {
    const raw = "cats & dogs"
    expect(renderHighlight(raw)).toContain("cats &amp; dogs")
  })

  it("escapes double-quotes", () => {
    const raw = `he said "hello"`
    expect(renderHighlight(raw)).toContain("&quot;")
  })

  it("escapes single-quotes", () => {
    const raw = `it's fine`
    expect(renderHighlight(raw)).toContain("&#x27;")
  })

  it("does NOT escape <mark> tags produced by sentinel replacement", () => {
    // The <mark> should appear as raw HTML, not &lt;mark&gt;
    const raw = `${MARK_OPEN}test${MARK_CLOSE}`
    expect(renderHighlight(raw)).toBe("<mark>test</mark>")
  })

  // ---------------------------------------------------------------------------
  // XSS via sentinels
  // ---------------------------------------------------------------------------
  it("escapes document content that contains sentinel-like characters within markers", () => {
    // If the document itself contained &, it must be escaped BEFORE sentinels are replaced
    const raw = `${MARK_OPEN}AT&T${MARK_CLOSE}`
    expect(renderHighlight(raw)).toBe("<mark>AT&amp;T</mark>")
  })

  // ---------------------------------------------------------------------------
  // Empty input
  // ---------------------------------------------------------------------------
  it("returns empty string for empty input", () => {
    expect(renderHighlight("")).toBe("")
  })
})

// ---------------------------------------------------------------------------
// renderHighlightFragments
// ---------------------------------------------------------------------------
describe("renderHighlightFragments", () => {
  it("joins multiple fragments with ellipsis separator", () => {
    const fragments = [`part ${MARK_OPEN}one${MARK_CLOSE}`, `part ${MARK_OPEN}two${MARK_CLOSE}`]
    expect(renderHighlightFragments(fragments)).toBe(
      "part <mark>one</mark> … part <mark>two</mark>"
    )
  })

  it("returns empty string for empty array", () => {
    expect(renderHighlightFragments([])).toBe("")
  })

  it("returns single fragment without separator", () => {
    const fragments = [`${MARK_OPEN}only${MARK_CLOSE}`]
    expect(renderHighlightFragments(fragments)).toBe("<mark>only</mark>")
  })

  it("escapes HTML across all fragments", () => {
    const fragments = ["<b>bold</b>", `${MARK_OPEN}safe${MARK_CLOSE}`]
    const result = renderHighlightFragments(fragments)
    expect(result).toContain("&lt;b&gt;")
    expect(result).toContain("<mark>safe</mark>")
  })
})
