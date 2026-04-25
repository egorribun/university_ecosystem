import { describe, expect, it } from "vitest"
import { slugify } from "../slugify"

describe("slugify", () => {
  // ---------------------------------------------------------------------------
  // Basic ASCII
  // ---------------------------------------------------------------------------
  it("lowercases ASCII text", () => {
    expect(slugify("Hello World")).toBe("hello-world")
  })

  it("replaces spaces with hyphens", () => {
    expect(slugify("foo bar baz")).toBe("foo-bar-baz")
  })

  it("collapses multiple spaces into one hyphen", () => {
    expect(slugify("foo   bar")).toBe("foo-bar")
  })

  it("strips special characters", () => {
    expect(slugify("Hello, World!")).toBe("hello-world")
  })

  // ---------------------------------------------------------------------------
  // HTML stripping (used with marked heading content)
  // ---------------------------------------------------------------------------
  it("strips HTML tags before slugifying", () => {
    expect(slugify("<strong>Title</strong>")).toBe("title")
  })

  it("handles nested HTML tags", () => {
    expect(slugify("<em><code>function</code></em>")).toBe("function")
  })

  // ---------------------------------------------------------------------------
  // Unicode / Cyrillic support
  // ---------------------------------------------------------------------------
  it("preserves Cyrillic letters", () => {
    expect(slugify("Привет мир")).toBe("привет-мир")
  })

  it("lowercases Cyrillic text", () => {
    expect(slugify("КИРИЛЛИЦА")).toBe("кириллица")
  })

  it("handles mixed Latin and Cyrillic", () => {
    expect(slugify("API методы")).toBe("api-методы")
  })

  // ---------------------------------------------------------------------------
  // Edge cases
  // ---------------------------------------------------------------------------
  it("returns empty string for empty input", () => {
    expect(slugify("")).toBe("")
  })

  it("returns empty string for whitespace-only input", () => {
    expect(slugify("   ")).toBe("")
  })

  it("trims leading/trailing whitespace before slugifying", () => {
    expect(slugify("  hello  ")).toBe("hello")
  })

  it("collapses consecutive hyphens into one", () => {
    // e.g. "foo - bar" → "foo---bar" after char removal, then collapsed
    expect(slugify("foo - bar")).toBe("foo-bar")
  })

  it("truncates output to 64 characters", () => {
    const longInput = "a".repeat(100)
    expect(slugify(longInput)).toHaveLength(64)
  })

  it("does not start or end with extra hyphens after truncation (no leading/trailing hyphens)", () => {
    const result = slugify("word ".repeat(20))
    expect(result).not.toMatch(/^-/)
    expect(result).not.toMatch(/-$/)
  })
})
