import { afterEach, beforeAll, vi } from "vitest"
import { cleanup } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"

const mockPlainText = vi.hoisted(() => (html: string | null | undefined): string => {
  let output = ""
  let insideTag = false

  for (const char of html ?? "") {
    if (char === "<") {
      insideTag = true
      continue
    }
    if (char === ">") {
      insideTag = false
      continue
    }
    if (!insideTag) output += char
  }

  return output
})

vi.mock("@/utils/cryptoWorker", () => ({
  cryptoWorker: {
    pbkdf2: vi.fn().mockResolvedValue("mocked_pbkdf2_hash"),
    scrypt: vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3])),
    hmacSha256: vi.fn().mockResolvedValue("mocked_hmac_base64"),
  },
}))

vi.mock("wasm-sanitizer", () => ({
  sanitize_rich_text: vi.fn((html: string) => html),
  sanitize_html_basic: vi.fn((html: string) => html),
  strip_html: vi.fn((html: string) => mockPlainText(html)),
}))

afterEach(() => {
  cleanup()
})

beforeAll(() => {
  if (!("scrollTo" in window)) {
    Object.defineProperty(window, "scrollTo", {
      value: () => {},
      configurable: true,
      writable: true,
    })
  }

  if (typeof window.scrollTo !== "function") {
    Object.defineProperty(window, "scrollTo", {
      value: () => {},
      configurable: true,
      writable: true,
    })
  }

  if (!("matchMedia" in window)) {
    Object.defineProperty(window, "matchMedia", {
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
      configurable: true,
    })
  }

  if (typeof window.requestAnimationFrame !== "function") {
    window.requestAnimationFrame = (cb: FrameRequestCallback) =>
      setTimeout(() => cb(Date.now()), 0) as unknown as number
  }

  if (typeof window.cancelAnimationFrame !== "function") {
    window.cancelAnimationFrame = (id: number) => {
      clearTimeout(id)
    }
  }

  if (!("scrollTo" in Element.prototype)) {
    Object.defineProperty(Element.prototype, "scrollTo", {
      value: function scrollTo(this: Element, options?: ScrollToOptions | number, y?: number) {
        if (typeof options === "object" && options !== null) {
          ;(this as unknown as { scrollTop: number }).scrollTop = options.top ?? 0
        } else if (typeof options === "number") {
          ;(this as unknown as { scrollTop: number }).scrollTop = options
          if (typeof y === "number") {
            ;(this as unknown as { scrollLeft: number }).scrollLeft = y
          }
        }
      },
      configurable: true,
    })
  }
})
