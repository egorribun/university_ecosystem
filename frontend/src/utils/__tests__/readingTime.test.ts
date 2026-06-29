import { describe, expect, it } from "vitest"
import { estimateReadingTime } from "@/utils/readingTime"

describe("estimateReadingTime", () => {
  it("returns null for empty string", () => {
    expect(estimateReadingTime("")).toBeNull()
  })

  it("returns null for whitespace-only string", () => {
    expect(estimateReadingTime("   ")).toBeNull()
  })

  it("returns 1 for very short text (minimum 1 minute)", () => {
    expect(estimateReadingTime("Hello world")).toBe(1)
  })

  it("returns 1 for a single word", () => {
    expect(estimateReadingTime("Hello")).toBe(1)
  })

  it("calculates reading time for normal text (~220 wpm)", () => {
    // 440 words → 440/220 = 2 minutes
    const words = Array.from({ length: 440 }, () => "word").join(" ")
    expect(estimateReadingTime(words)).toBe(2)
  })

  it("strips HTML tags before counting words", () => {
    const html = "<p>Hello</p> <strong>world</strong> <a href='#'>link</a>"
    // 3 words → 1 minute
    expect(estimateReadingTime(html)).toBe(1)
  })

  it("handles complex HTML content", () => {
    // Generate ~220 words wrapped in HTML
    const words = Array.from({ length: 220 }, (_, i) => `<span>word${i}</span>`).join(" ")
    const result = estimateReadingTime(words)
    expect(result).toBe(1) // 220 words / 220 wpm = 1
  })

  it("collapses multiple whitespace before counting", () => {
    const text = "word1    word2    word3"
    expect(estimateReadingTime(text)).toBe(1)
  })

  it("rounds to nearest minute", () => {
    // 330 words → 330/220 = 1.5 → rounds to 2
    const words = Array.from({ length: 330 }, () => "word").join(" ")
    expect(estimateReadingTime(words)).toBe(2)
  })

  it("handles large text", () => {
    // 2200 words → 10 minutes
    const words = Array.from({ length: 2200 }, () => "word").join(" ")
    expect(estimateReadingTime(words)).toBe(10)
  })
})
