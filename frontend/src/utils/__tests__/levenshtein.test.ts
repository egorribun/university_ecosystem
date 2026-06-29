import { describe, expect, it } from "vitest"
import { levenshtein } from "@/utils/levenshtein"

describe("levenshtein", () => {
  it("returns 0 for identical strings", () => {
    expect(levenshtein("kitten", "kitten")).toBe(0)
  })

  it("returns 0 for two empty strings", () => {
    expect(levenshtein("", "")).toBe(0)
  })

  it("returns length of second string when first is empty", () => {
    expect(levenshtein("", "hello")).toBe(5)
  })

  it("returns length of first string when second is empty", () => {
    expect(levenshtein("hello", "")).toBe(5)
  })

  it("computes single character difference (substitution)", () => {
    expect(levenshtein("cat", "bat")).toBe(1)
  })

  it("computes single character insertion", () => {
    expect(levenshtein("cat", "cats")).toBe(1)
  })

  it("computes single character deletion", () => {
    expect(levenshtein("cats", "cat")).toBe(1)
  })

  it("computes classic kitten/sitting distance", () => {
    expect(levenshtein("kitten", "sitting")).toBe(3)
  })

  it("returns length of longer string for completely different strings", () => {
    expect(levenshtein("abc", "xyz")).toBe(3)
  })

  it("handles single-character strings", () => {
    expect(levenshtein("a", "b")).toBe(1)
    expect(levenshtein("a", "a")).toBe(0)
  })

  it("is symmetric", () => {
    expect(levenshtein("abc", "def")).toBe(levenshtein("def", "abc"))
  })

  it("handles longer strings", () => {
    // "sunday" → "saturday": distance 3
    expect(levenshtein("sunday", "saturday")).toBe(3)
  })

  it("handles case sensitivity", () => {
    expect(levenshtein("Hello", "hello")).toBe(1)
  })

  it("handles strings of very different lengths", () => {
    expect(levenshtein("a", "abcdefgh")).toBe(7)
  })

  it("handles email domain typo detection", () => {
    // Practical use case: detecting email domain typos
    expect(levenshtein("gmail.com", "gmai.com")).toBe(1)
    expect(levenshtein("gmail.com", "gmial.com")).toBe(2)
  })
})
