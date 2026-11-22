import { describe, expect, it } from "vitest"

import { expectInlineStyle, expectInlineStyleAbsent } from "./expectInlineStyle"

describe("expectInlineStyle", () => {
  it("checks unresolved tokens and custom properties without a theme stylesheet", () => {
    const element = document.createElement("div")
    element.style.color = "var(--text-tertiary)"
    element.style.setProperty("--_badge-accent", "var(--cat-amber-text)")
    expectInlineStyle(element, {
      color: "var(--text-tertiary)",
      "--_badge-accent": "var(--cat-amber-text)",
    })
  })

  it("normalizes equivalent CSSOM spellings of the expected value", () => {
    const element = document.createElement("div")
    element.style.width = "calc(100vw - 2rem)"
    element.style.transform = "translateY(0)"
    element.style.backgroundColor = "rgb(59, 130, 246)"
    expectInlineStyle(element, {
      width: "calc(100vw - 2rem)",
      transform: "translateY(0px)",
      backgroundColor: "#3b82f6",
    })
  })

  it("checks a shorthand and its longhand independently", () => {
    const element = document.createElement("div")
    element.style.transition = "transform 150ms ease-out"
    element.style.willChange = "transform"
    expectInlineStyle(element, {
      transition: "transform 150ms ease-out",
      transitionDuration: "150ms",
      willChange: "transform",
    })
  })

  it("rejects missing, changed or invalid declarations", () => {
    const element = document.createElement("div")
    expect(() => expectInlineStyle(element, { color: "var(--text-primary)" })).toThrow()
    element.style.color = "var(--text-secondary)"
    expect(() => expectInlineStyle(element, { color: "var(--text-primary)" })).toThrow()
    expect(() => expectInlineStyle(element, { color: "" })).toThrow()
    expect(() => expectInlineStyle(element, { color: "not-a-color" })).toThrow()
    expect(() => expectInlineStyle(element, {})).toThrow()
  })

  it("rejects absent elements and supports SVG inline styles", () => {
    expect(() => expectInlineStyle(null, { color: "red" })).toThrow()
    expect(() => expectInlineStyle(undefined, { color: "red" })).toThrow()
    const unsupported = document.createElementNS("urn:test", "foreign")
    expect(() => expectInlineStyle(unsupported, { color: "red" })).toThrow()
    const element = document.createElementNS("http://www.w3.org/2000/svg", "svg")
    element.style.opacity = "var(--opacity-strong)"
    expectInlineStyle(element, { opacity: "var(--opacity-strong)" })
  })
})

describe("expectInlineStyleAbsent", () => {
  it("passes when the declaration is missing or has another value", () => {
    const element = document.createElement("div")
    expectInlineStyleAbsent(element, { backgroundColor: "var(--bg-surface-hover)" })
    element.style.backgroundColor = "var(--bg-surface)"
    expectInlineStyleAbsent(element, { backgroundColor: "var(--bg-surface-hover)" })
  })

  it("fails when the declaration is present, and on invalid input", () => {
    const element = document.createElement("div")
    element.style.backgroundColor = "var(--bg-surface-hover)"
    expect(() =>
      expectInlineStyleAbsent(element, { backgroundColor: "var(--bg-surface-hover)" })
    ).toThrow()
    expect(() => expectInlineStyleAbsent(element, { backgroundColor: "" })).toThrow()
    expect(() => expectInlineStyleAbsent(null, { color: "red" })).toThrow()
  })
})
