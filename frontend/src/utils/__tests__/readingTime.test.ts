import { describe, expect, it } from "vitest"
import { estimateReadingTime } from "../readingTime"

describe("estimateReadingTime", () => {
  // ---------------------------------------------------------------------------
  // Empty / blank content
  // ---------------------------------------------------------------------------
  it("returns null for empty string", () => {
    expect(estimateReadingTime("")).toBeNull()
  })

  it("returns null for whitespace-only string", () => {
    expect(estimateReadingTime("   ")).toBeNull()
  })

  it("returns null for HTML-only content (no text)", () => {
    expect(estimateReadingTime("<p></p><br/>")).toBeNull()
  })

  // ---------------------------------------------------------------------------
  // Minimum reading time
  // ---------------------------------------------------------------------------
  it("returns at least 1 minute for a few words", () => {
    expect(estimateReadingTime("Hello world")).toBe(1)
  })

  it("returns 1 minute for fewer than 220 words", () => {
    const text = "word ".repeat(100)
    expect(estimateReadingTime(text)).toBe(1)
  })

  // ---------------------------------------------------------------------------
  // Standard calculation: 220 wpm
  // ---------------------------------------------------------------------------
  it("returns 1 minute for exactly 220 words", () => {
    const text = "word ".repeat(220)
    expect(estimateReadingTime(text)).toBe(1)
  })

  it("returns 2 minutes for 440 words", () => {
    const text = "word ".repeat(440)
    expect(estimateReadingTime(text)).toBe(2)
  })

  it("returns 5 minutes for 1100 words", () => {
    const text = "word ".repeat(1100)
    expect(estimateReadingTime(text)).toBe(5)
  })

  // ---------------------------------------------------------------------------
  // HTML stripping
  // ---------------------------------------------------------------------------
  it("strips HTML tags before counting words", () => {
    const html = "<p>Hello</p><p>World</p>"
    // 2 words → 1 minute
    expect(estimateReadingTime(html)).toBe(1)
  })

  it("correctly counts words inside nested tags", () => {
    const html = "<article><h1>Title</h1><p>This <strong>is</strong> a test.</p></article>"
    // "Title This is a test." → 5 words → 1 minute
    expect(estimateReadingTime(html)).toBe(1)
  })

  it("handles HTML with inline style attributes", () => {
    const html = '<span style="color:red">Important text here</span>'
    // "Important text here" → 3 words → 1 minute
    expect(estimateReadingTime(html)).toBe(1)
  })
})
