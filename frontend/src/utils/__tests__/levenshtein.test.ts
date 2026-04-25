import { describe, expect, it } from "vitest"
import { levenshtein } from "../levenshtein"

describe("levenshtein", () => {
  // ---------------------------------------------------------------------------
  // Zero-cost base cases
  // ---------------------------------------------------------------------------
  it("returns 0 for two identical strings", () => {
    expect(levenshtein("hello", "hello")).toBe(0)
  })

  it("returns 0 for two empty strings", () => {
    expect(levenshtein("", "")).toBe(0)
  })

  // ---------------------------------------------------------------------------
  // Empty string edge cases
  // ---------------------------------------------------------------------------
  it("returns length of b when a is empty", () => {
    expect(levenshtein("", "abc")).toBe(3)
  })

  it("returns length of a when b is empty", () => {
    expect(levenshtein("abc", "")).toBe(3)
  })

  // ---------------------------------------------------------------------------
  // Single operations
  // ---------------------------------------------------------------------------
  it("returns 1 for single insertion", () => {
    expect(levenshtein("cat", "cats")).toBe(1)
  })

  it("returns 1 for single deletion", () => {
    expect(levenshtein("cats", "cat")).toBe(1)
  })

  it("returns 1 for single substitution", () => {
    expect(levenshtein("cat", "bat")).toBe(1)
  })

  // ---------------------------------------------------------------------------
  // Real-world email domain typos (the actual use case)
  // ---------------------------------------------------------------------------
  it("detects 1-char typo in gmail.com", () => {
    expect(levenshtein("gmai.com", "gmail.com")).toBe(1)
  })

  it("detects 2-char typo in yandex.ru", () => {
    expect(levenshtein("yandexru", "yandex.ru")).toBe(1)
  })

  it("handles completely different strings", () => {
    expect(levenshtein("abc", "xyz")).toBe(3)
  })

  // ---------------------------------------------------------------------------
  // Longer strings
  // ---------------------------------------------------------------------------
  it("computes distance for longer inputs correctly", () => {
    // kitten → sitting: classic benchmark = 3
    expect(levenshtein("kitten", "sitting")).toBe(3)
  })

  it("is symmetric", () => {
    expect(levenshtein("abc", "abcd")).toBe(levenshtein("abcd", "abc"))
  })
})
