import { describe, expect, it } from "vitest"
import { suggestEmailDomain, COMMON_EMAIL_DOMAINS } from "../authUtils"

describe("suggestEmailDomain", () => {
  // ---------------------------------------------------------------------------
  // No-suggestion cases
  // ---------------------------------------------------------------------------
  it("returns null when email has no @", () => {
    expect(suggestEmailDomain("notanemail")).toBeNull()
  })

  it("returns null when domain is already a known domain", () => {
    expect(suggestEmailDomain("user@gmail.com")).toBeNull()
    expect(suggestEmailDomain("user@yandex.ru")).toBeNull()
    expect(suggestEmailDomain("user@mail.ru")).toBeNull()
  })

  it("returns null when local part is missing", () => {
    expect(suggestEmailDomain("@gmail.com")).toBeNull()
  })

  it("returns null when domain is missing after @", () => {
    expect(suggestEmailDomain("user@")).toBeNull()
  })

  it("returns null when typo distance > 2", () => {
    // "totally-wrong.com" has distance >> 2 from any known domain
    expect(suggestEmailDomain("user@totally-wrong.com")).toBeNull()
  })

  // ---------------------------------------------------------------------------
  // Typo correction
  // ---------------------------------------------------------------------------
  it("suggests gmail.com for gmai.com (1 deletion)", () => {
    expect(suggestEmailDomain("user@gmai.com")).toBe("user@gmail.com")
  })

  it("suggests gmail.com for gmial.com (1 transposition)", () => {
    expect(suggestEmailDomain("user@gmial.com")).toBe("user@gmail.com")
  })

  it("keeps the closest match when a later domain is also within the typo threshold", () => {
    expect(suggestEmailDomain("user@hmail.com")).toBe("user@gmail.com")
  })

  it("suggests yandex.ru for yandex.r (1 deletion)", () => {
    expect(suggestEmailDomain("user@yandex.r")).toBe("user@yandex.ru")
  })

  it("suggests mail.ru for mail.r (1 deletion)", () => {
    expect(suggestEmailDomain("user@mail.r")).toBe("user@mail.ru")
  })

  it("preserves the local part in the suggestion", () => {
    const result = suggestEmailDomain("johndoe@gmai.com")
    expect(result).toMatch(/^johndoe@/)
  })

  it("does not treat an address without @ as a domain typo", () => {
    expect(suggestEmailDomain("gmail.co")).toBeNull()
  })

  it("returns null when the local part is only whitespace", () => {
    expect(suggestEmailDomain("   @gmial.com")).toBeNull()
  })

  it("returns null for a typo domain without a local part", () => {
    expect(suggestEmailDomain("@gmial.com")).toBeNull()
  })

  it("trims whitespace around the local part in the suggestion", () => {
    expect(suggestEmailDomain(" john @gmial.com")).toBe("john@gmail.com")
  })

  it("prefers a later domain that is strictly closer", () => {
    // yandex.ru is 2 edits away, yandex.com only 1.
    expect(suggestEmailDomain("user@yandex.co")).toBe("user@yandex.com")
  })

  it("keeps the first listed domain when two are equally close", () => {
    // Both yandex.ru and yandex.com are 2 edits away.
    expect(suggestEmailDomain("user@yandex.oo")).toBe("user@yandex.ru")
  })

  // ---------------------------------------------------------------------------
  // Case handling
  // ---------------------------------------------------------------------------
  it("is case-insensitive for the domain part", () => {
    expect(suggestEmailDomain("user@GMAIL.COM")).toBeNull() // exact match after lowercase
  })

  // ---------------------------------------------------------------------------
  // COMMON_EMAIL_DOMAINS list
  // ---------------------------------------------------------------------------
  it("exports a non-empty domain list", () => {
    expect(COMMON_EMAIL_DOMAINS.length).toBeGreaterThan(0)
  })

  it("includes expected well-known domains", () => {
    const domains = COMMON_EMAIL_DOMAINS as ReadonlyArray<string>
    expect(domains).toContain("gmail.com")
    expect(domains).toContain("yandex.ru")
    expect(domains).toContain("mail.ru")
  })
})
