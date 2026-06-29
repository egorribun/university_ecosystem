import { describe, expect, it } from "vitest"
import { slugify } from "@/utils/slugify"

describe("slugify", () => {
  it("converts normal text to a slug", () => {
    expect(slugify("Hello World")).toBe("hello-world")
  })

  it("converts to lowercase", () => {
    expect(slugify("UPPERCASE TEXT")).toBe("uppercase-text")
  })

  it("handles Unicode characters (Cyrillic)", () => {
    expect(slugify("Привет Мир")).toBe("привет-мир")
  })

  it("handles mixed Latin and Cyrillic", () => {
    expect(slugify("Hello Мир")).toBe("hello-мир")
  })

  it("removes special characters", () => {
    expect(slugify("Hello! @World# $Test%")).toBe("hello-world-test")
  })

  it("collapses multiple spaces into single hyphen", () => {
    expect(slugify("hello    world")).toBe("hello-world")
  })

  it("collapses multiple hyphens into single hyphen", () => {
    expect(slugify("hello---world")).toBe("hello-world")
  })

  it("returns empty string for empty input", () => {
    expect(slugify("")).toBe("")
  })

  it("trims whitespace", () => {
    expect(slugify("  hello world  ")).toBe("hello-world")
  })

  it("strips HTML tags before slugifying", () => {
    expect(slugify("<strong>Bold</strong> text")).toBe("bold-text")
  })

  it("handles numbers in text", () => {
    expect(slugify("Chapter 1 Introduction")).toBe("chapter-1-introduction")
  })

  it("truncates to 64 characters maximum", () => {
    const longText = "a".repeat(100)
    expect(slugify(longText).length).toBeLessThanOrEqual(64)
  })

  it("handles only-special-characters input", () => {
    expect(slugify("!@#$%^&*()")).toBe("")
  })

  it("handles single word", () => {
    expect(slugify("hello")).toBe("hello")
  })

  it("preserves hyphens between words", () => {
    expect(slugify("well-known fact")).toBe("well-known-fact")
  })
})
