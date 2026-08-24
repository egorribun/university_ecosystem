import { describe, expect, it } from "vitest"
import { htmlToPlainText } from "../htmlText"

describe("htmlText utils", () => {
  it("returns empty string for null, undefined, or empty string", () => {
    expect(htmlToPlainText(null)).toBe("")
    expect(htmlToPlainText(undefined)).toBe("")
    expect(htmlToPlainText("")).toBe("")
  })

  it("parses text using DOMParser if available", () => {
    expect(htmlToPlainText("plain text")).toBe("plain text")
    expect(htmlToPlainText("<p>hello <strong>world</strong></p>")).toBe("hello world")
  })

  it("normalizes a DOM parser result without text content to an empty string", () => {
    class EmptyDOMParser {
      parseFromString() {
        return { body: { textContent: null } }
      }
    }
    const originalDOMParser = global.DOMParser
    Object.defineProperty(global, "DOMParser", {
      value: EmptyDOMParser,
      writable: true,
      configurable: true,
    })
    try {
      expect(htmlToPlainText("<p>content</p>")).toBe("")
    } finally {
      Object.defineProperty(global, "DOMParser", {
        value: originalDOMParser,
        writable: true,
        configurable: true,
      })
    }
  })

  it("falls back to stripTagsByState if DOMParser is undefined", () => {
    const originalDOMParser = global.DOMParser
    try {
      // Temporarily hide DOMParser
      Object.defineProperty(global, "DOMParser", {
        value: undefined,
        writable: true,
        configurable: true,
      })

      expect(htmlToPlainText("plain text")).toBe("plain text")
      expect(htmlToPlainText("<p>hello <strong>world</strong></p>")).toBe("hello world")
      expect(
        htmlToPlainText(
          '<div class="test">hello <span style="color: red;">nested</span> tags</div>'
        )
      ).toBe("hello nested tags")
      // Check edge cases of tags
      expect(htmlToPlainText("<tag>unclosed-at-end")).toBe("unclosed-at-end")
      expect(htmlToPlainText("no-tag-at-start</tag>")).toBe("no-tag-at-start")
    } finally {
      // Restore DOMParser
      Object.defineProperty(global, "DOMParser", {
        value: originalDOMParser,
        writable: true,
        configurable: true,
      })
    }
  })
})
