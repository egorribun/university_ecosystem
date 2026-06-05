import { describe, it, expect } from "vitest"

import { localizeField } from "../localize"

describe("localizeField", () => {
  it("returns the english value when language is 'en' and english is present", () => {
    expect(localizeField("Привет", "Hello", "en")).toBe("Hello")
  })

  it("returns the primary value when language is not 'en'", () => {
    expect(localizeField("Привет", "Hello", "ru")).toBe("Привет")
  })

  it("falls back to the primary value when english is blank under 'en'", () => {
    expect(localizeField("Привет", "   ", "en")).toBe("Привет")
    expect(localizeField("Привет", null, "en")).toBe("Привет")
  })

  it("falls back to english when primary is empty", () => {
    expect(localizeField("", "fallback", "ru")).toBe("fallback")
  })

  it("returns empty string when both primary and english are empty", () => {
    expect(localizeField("", undefined, "ru")).toBe("")
  })
})
