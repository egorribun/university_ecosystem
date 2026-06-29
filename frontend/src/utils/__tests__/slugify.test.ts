import { describe, expect, it } from "vitest"
import { slugify } from "@/utils/slugify"

describe("slugify", () => {
  it("slugifies normal strings", () => {
    expect(slugify("Hello World")).toBe("hello-world")
  })

  it("collapses multiple spaces", () => {
    expect(slugify("a    b")).toBe("a-b")
  })

  it("handles unicode", () => {
    expect(slugify("Héllö")).toBe("hello")
  })

  it("returns empty string for empty input", () => {
    expect(slugify("")).toBe("")
  })
})
