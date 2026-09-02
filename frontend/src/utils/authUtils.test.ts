import { describe, expect, it } from "vitest"

import { COMMON_EMAIL_DOMAINS, suggestEmailDomain } from "./authUtils"
import { levenshtein } from "./levenshtein"

/**
 * Tests for the email-suggestion state-machine input used by useLoginForm.
 * The hook itself glues together AuthContext + react-hook-form + TanStack
 * Router + MFA — its observable state machine (caps lock, show password,
 * MFA branches) is best verified via the E2E suite. The deterministic
 * suggestion logic — `suggestEmailDomain` and the underlying
 * `levenshtein` distance — is the testable kernel and has direct user-facing
 * impact ("did you mean foo@gmail.com?"), so we cover it exhaustively here.
 */

describe("levenshtein", () => {
  it("returns 0 for identical strings", () => {
    expect(levenshtein("hello", "hello")).toBe(0)
  })

  it("returns the length when one string is empty", () => {
    expect(levenshtein("", "hello")).toBe(5)
    expect(levenshtein("hello", "")).toBe(5)
  })

  it("counts a single character substitution", () => {
    expect(levenshtein("kitten", "sitten")).toBe(1)
  })

  it("counts a single character insertion", () => {
    expect(levenshtein("cat", "cats")).toBe(1)
  })

  it("counts a single character deletion", () => {
    expect(levenshtein("cats", "cat")).toBe(1)
  })

  it("computes the canonical kitten/sitting distance", () => {
    // Classic edit-distance example: kitten -> sitting requires 3 edits.
    expect(levenshtein("kitten", "sitting")).toBe(3)
  })

  it("is symmetric (a→b == b→a)", () => {
    expect(levenshtein("foo", "bar")).toBe(levenshtein("bar", "foo"))
    expect(levenshtein("yandex.ru", "yandexru")).toBe(levenshtein("yandexru", "yandex.ru"))
  })

  it("handles unicode without crashing", () => {
    // The implementation operates per-codepoint, not per-grapheme — but it
    // must not raise. Multi-byte chars count as one per str index.
    expect(levenshtein("café", "cafe")).toBe(1)
    expect(levenshtein("Привет", "Привед")).toBe(1)
  })
})

describe("suggestEmailDomain", () => {
  it("returns null for input without an @", () => {
    expect(suggestEmailDomain("not-an-email")).toBeNull()
  })

  it("returns null for an empty local part", () => {
    expect(suggestEmailDomain("@gmail.com")).toBeNull()
  })

  it("returns null for an empty domain", () => {
    expect(suggestEmailDomain("user@")).toBeNull()
    expect(suggestEmailDomain("user@   ")).toBeNull()
  })

  it("returns null when the domain is already canonical", () => {
    expect(suggestEmailDomain("user@gmail.com")).toBeNull()
    expect(suggestEmailDomain("user@yandex.ru")).toBeNull()
    expect(suggestEmailDomain("user@proton.me")).toBeNull()
  })

  it("returns null when the domain is unrecognised + far from any common one", () => {
    expect(suggestEmailDomain("user@university.edu")).toBeNull()
    expect(suggestEmailDomain("user@completelydifferent.io")).toBeNull()
  })

  it("suggests the closest common domain within edit distance 2", () => {
    // 1-edit typo: gmial → gmail.
    expect(suggestEmailDomain("user@gmial.com")).toBe("user@gmail.com")
    // 1-edit typo: yandx → yandex.
    expect(suggestEmailDomain("user@yandx.ru")).toBe("user@yandex.ru")
    // 1-edit typo: protn → proton.
    expect(suggestEmailDomain("user@protn.me")).toBe("user@proton.me")
  })

  it("suggests the lowest-distance match when several are close", () => {
    // 'gmial.com' is distance 1 from gmail.com, 5 from googlemail.com
    expect(suggestEmailDomain("foo@gmial.com")).toBe("foo@gmail.com")
  })

  it("does not suggest when distance > 2", () => {
    // 'gnail' → distance 1 from gmail
    expect(suggestEmailDomain("user@gnail.com")).toBe("user@gmail.com")
    // 'gnaaaail' → distance 4 from gmail
    expect(suggestEmailDomain("user@gnaaaail.com")).toBeNull()
  })

  it("normalises domain case for comparison", () => {
    // Upper-case domain still matches gmail.com (lowercased internally).
    expect(suggestEmailDomain("user@GMail.COM")).toBeNull()
  })

  it("preserves the local part as typed", () => {
    expect(suggestEmailDomain("MixedCase.User@gmial.com")).toBe("MixedCase.User@gmail.com")
  })

  it("trims whitespace around the address", () => {
    expect(suggestEmailDomain("user@  gmial.com  ")).toBe("user@gmail.com")
  })

  it("falls back gracefully when the local part is whitespace-only", () => {
    expect(suggestEmailDomain("   @gmail.com")).toBeNull()
  })

  it("supports every domain in the registry as a no-op", () => {
    // Every canonical domain returns null for "user@<domain>".
    for (const domain of COMMON_EMAIL_DOMAINS) {
      expect(suggestEmailDomain(`user@${domain}`)).toBeNull()
    }
  })
})
