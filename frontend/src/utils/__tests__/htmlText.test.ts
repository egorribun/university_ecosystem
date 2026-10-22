import { describe, expect, it } from "vitest"
import { htmlToPlainText } from "../htmlText"

const replaceProperty = (target: object, key: string, value: unknown): (() => void) => {
  const previous = Object.getOwnPropertyDescriptor(target, key)
  Object.defineProperty(target, key, {
    value,
    writable: true,
    configurable: true,
  })
  return () => {
    if (previous) Object.defineProperty(target, key, previous)
    else Reflect.deleteProperty(target, key)
  }
}

describe("htmlText utils", () => {
  it("returns empty string for null, undefined, or empty string", () => {
    expect(htmlToPlainText(null)).toBe("")
    expect(htmlToPlainText(undefined)).toBe("")
    expect(htmlToPlainText("")).toBe("")
  })

  it("parses text using DOMParser if available", () => {
    expect(htmlToPlainText("plain text")).toBe("plain text")
    expect(htmlToPlainText("A &amp; B")).toBe("A & B")
    expect(htmlToPlainText("<p>hello <strong>world</strong></p>")).toBe("hello world")
  })

  it("passes cached app-policy TrustedHTML to a TT-enforcing DOMParser and keeps decoded text", () => {
    const source = "<p>Привет &amp; <strong>мир</strong></p><script>secret()</script>"
    const sanitizedMarkup = "<p>Привет &amp; <strong>мир</strong></p>"
    const trustedHtml = { toString: () => sanitizedMarkup }
    const sanitizerInputs: string[] = []
    const policy = {
      createHTML: (value: string) => {
        sanitizerInputs.push(value)
        return trustedHtml
      },
    }
    const NativeDOMParser = globalThis.DOMParser
    let restoreTrustedTypes = () => {}
    let restoreAppPolicy = () => {}
    let restoreDOMParser = () => {}

    class TrustedHTMLOnlyDOMParser {
      parseFromString(value: string, mimeType: DOMParserSupportedType) {
        if ((value as unknown) !== trustedHtml) throw new TypeError("TrustedHTML required")
        return new NativeDOMParser().parseFromString(String(value), mimeType)
      }
    }

    try {
      restoreTrustedTypes = replaceProperty(window, "trustedTypes", {})
      restoreAppPolicy = replaceProperty(window, "__ttAppPolicy", policy)
      restoreDOMParser = replaceProperty(globalThis, "DOMParser", TrustedHTMLOnlyDOMParser)

      expect(htmlToPlainText(source)).toBe("Привет & мир")
      expect(sanitizerInputs).toEqual([source])
    } finally {
      restoreDOMParser()
      restoreAppPolicy()
      restoreTrustedTypes()
    }
  })

  it("uses the text-only fallback when TT is active before the app policy exists", () => {
    let parserCalled = false
    let restoreTrustedTypes = () => {}
    let restoreAppPolicy = () => {}
    let restoreDOMParser = () => {}

    class RejectingDOMParser {
      parseFromString() {
        parserCalled = true
        throw new TypeError("TrustedHTML required")
      }
    }

    try {
      restoreTrustedTypes = replaceProperty(window, "trustedTypes", {})
      restoreAppPolicy = replaceProperty(window, "__ttAppPolicy", undefined)
      restoreDOMParser = replaceProperty(globalThis, "DOMParser", RejectingDOMParser)

      expect(htmlToPlainText("<p>plain &amp; fallback</p>")).toBe("plain &amp; fallback")
      expect(parserCalled).toBe(false)
    } finally {
      restoreDOMParser()
      restoreAppPolicy()
      restoreTrustedTypes()
    }
  })

  it("uses text-only fallback when the app policy cache is explicitly disabled", () => {
    let parserCalled = false
    let restoreTrustedTypes = () => {}
    let restoreAppPolicy = () => {}
    let restoreDOMParser = () => {}

    class RejectingDOMParser {
      parseFromString() {
        parserCalled = true
        throw new TypeError("TrustedHTML required")
      }
    }

    try {
      restoreTrustedTypes = replaceProperty(window, "trustedTypes", {})
      restoreAppPolicy = replaceProperty(window, "__ttAppPolicy", false)
      restoreDOMParser = replaceProperty(globalThis, "DOMParser", RejectingDOMParser)

      expect(htmlToPlainText("<p>plain &amp; fallback</p>")).toBe("plain &amp; fallback")
      expect(parserCalled).toBe(false)
    } finally {
      restoreDOMParser()
      restoreAppPolicy()
      restoreTrustedTypes()
    }
  })

  it("uses the text-only fallback when the cached app policy rejects input", () => {
    let parserCalled = false
    let restoreTrustedTypes = () => {}
    let restoreAppPolicy = () => {}
    let restoreDOMParser = () => {}

    class RejectingDOMParser {
      parseFromString() {
        parserCalled = true
        throw new TypeError("TrustedHTML required")
      }
    }

    try {
      restoreTrustedTypes = replaceProperty(window, "trustedTypes", {})
      restoreAppPolicy = replaceProperty(window, "__ttAppPolicy", {
        createHTML: () => {
          throw new TypeError("WASM sanitizer unavailable")
        },
      })
      restoreDOMParser = replaceProperty(globalThis, "DOMParser", RejectingDOMParser)

      expect(htmlToPlainText("<p>plain &amp; fallback</p>")).toBe("plain &amp; fallback")
      expect(parserCalled).toBe(false)
    } finally {
      restoreDOMParser()
      restoreAppPolicy()
      restoreTrustedTypes()
    }
  })

  it("uses the text-only fallback when DOMParser rejects cached TrustedHTML", () => {
    const source = "<p>parser fallback</p>"
    const trustedHtml = { toString: () => source }
    const sanitizerInputs: string[] = []
    let parserCalled = false
    let restoreTrustedTypes = () => {}
    let restoreAppPolicy = () => {}
    let restoreDOMParser = () => {}

    class RejectingDOMParser {
      parseFromString(value: string) {
        parserCalled = true
        if ((value as unknown) !== trustedHtml) throw new TypeError("TrustedHTML required")
        throw new TypeError("Parser rejected TrustedHTML")
      }
    }

    try {
      restoreTrustedTypes = replaceProperty(window, "trustedTypes", {})
      restoreAppPolicy = replaceProperty(window, "__ttAppPolicy", {
        createHTML: (value: string) => {
          sanitizerInputs.push(value)
          return trustedHtml
        },
      })
      restoreDOMParser = replaceProperty(globalThis, "DOMParser", RejectingDOMParser)

      expect(htmlToPlainText(source)).toBe("parser fallback")
      expect(sanitizerInputs).toEqual([source])
      expect(parserCalled).toBe(true)
    } finally {
      restoreDOMParser()
      restoreAppPolicy()
      restoreTrustedTypes()
    }
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

  it("uses native DOMParser during SSR without a window or Trusted Types", () => {
    const restoreWindow = replaceProperty(globalThis, "window", undefined)
    try {
      expect(htmlToPlainText("<p>Server &amp; <strong>render</strong></p>")).toBe("Server & render")
    } finally {
      restoreWindow()
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
      expect(htmlToPlainText("A &amp; B")).toBe("A &amp; B")
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
