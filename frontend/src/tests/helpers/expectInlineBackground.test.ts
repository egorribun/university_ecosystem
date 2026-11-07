import { describe, expect, it } from "vitest"

import { expectInlineBackground } from "./expectInlineBackground"

describe("expectInlineBackground", () => {
  it("checks unresolved CSS tokens without requiring a theme stylesheet", () => {
    const element = document.createElement("div")
    element.style.background = "var(--card-background)"
    expectInlineBackground(element, "var(--card-background)")
  })

  it("normalizes equivalent CSSOM color spellings", () => {
    const element = document.createElement("div")
    element.style.backgroundColor = "rgb(59, 130, 246)"
    expectInlineBackground(element, "#3b82f6", "background-color")
  })

  it("rejects missing or changed inline declarations", () => {
    const element = document.createElement("div")
    expect(() => expectInlineBackground(element, "var(--card-background)")).toThrow()
    element.style.background = "var(--other-background)"
    expect(() => expectInlineBackground(element, "var(--card-background)")).toThrow()
  })

  it("rejects invalid expectations instead of accepting two empty declarations", () => {
    const element = document.createElement("div")
    expect(() => expectInlineBackground(element, "")).toThrow()
    expect(() => expectInlineBackground(element, "not-a-css-background")).toThrow()
  })

  it("rejects absent elements and supports SVG inline styles", () => {
    expect(() => expectInlineBackground(null, "red")).toThrow()
    expect(() => expectInlineBackground(undefined, "red")).toThrow()
    const unsupported = document.createElementNS("urn:test", "foreign")
    expect(() => expectInlineBackground(unsupported, "red")).toThrow()
    const element = document.createElementNS("http://www.w3.org/2000/svg", "svg")
    element.style.background = "var(--card-background)"
    expectInlineBackground(element, "var(--card-background)")
  })
})
