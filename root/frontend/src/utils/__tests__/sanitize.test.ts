import DOMPurify from "dompurify"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type SanitizeModule = typeof import("../sanitize")

const originalTrustedTypes = window.trustedTypes

const loadModule = async (): Promise<SanitizeModule> => {
  return import("../sanitize")
}

beforeEach(() => {
  vi.resetModules()
  vi.restoreAllMocks()
  delete (window as typeof window & { __dompurifyNewsPolicy?: unknown }).__dompurifyNewsPolicy
  window.trustedTypes = originalTrustedTypes
})

afterEach(() => {
  vi.resetModules()
  delete (window as typeof window & { __dompurifyNewsPolicy?: unknown }).__dompurifyNewsPolicy
  window.trustedTypes = originalTrustedTypes
})

describe("sanitizeNewsHtml", () => {
  it("removes disallowed markup when Trusted Types are unavailable", async () => {
    window.trustedTypes = undefined
    const { sanitizeNewsHtml } = await loadModule()
    const dirty = "<img src=x onerror=alert(1)><p>safe</p>"
    const sanitized = sanitizeNewsHtml(dirty)
    expect(String(sanitized)).toContain("<p>safe</p>")
    expect(String(sanitized)).not.toContain("onerror")
    expect(String(sanitized)).not.toContain("<script")
  })

  it("reuses the Trusted Types policy when available", async () => {
    const createHTML = vi.fn((dirty: string) => {
      const clean = DOMPurify.sanitize(dirty, {
        USE_PROFILES: { html: true },
        ALLOW_DATA_ATTR: false,
        KEEP_CONTENT: false,
      })
      return { toString: () => clean } as unknown as TrustedHTML
    })
    const policy = { createHTML }
    const createPolicy = vi.fn(() => policy)
    window.trustedTypes = {
      createPolicy,
    } as unknown as TrustedTypePolicyFactory

    const { sanitizeNewsHtml } = await loadModule()

    const first = sanitizeNewsHtml("<script>alert(1)</script><b>ok</b>")
    expect(createPolicy).toHaveBeenCalledTimes(1)
    expect(createHTML).toHaveBeenCalledTimes(1)
    expect(String(first)).toContain("<b>ok</b>")
    expect(String(first)).not.toContain("<script")

    const second = sanitizeNewsHtml("<i>italic</i>")
    expect(createPolicy).toHaveBeenCalledTimes(1)
    expect(createHTML).toHaveBeenCalledTimes(2)
    expect(String(second)).toBe("<i>italic</i>")
  })

  it("falls back to DOMPurify when policy creation fails", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
    window.trustedTypes = {
      createPolicy: () => {
        throw new Error("policy error")
      },
    } as unknown as TrustedTypePolicyFactory

    const { sanitizeNewsHtml } = await loadModule()
    const result = sanitizeNewsHtml("<span data-test='1'>ok</span><script>bad()</script>")
    expect(String(result)).toBe("<span>ok</span>")
    expect(warnSpy).toHaveBeenCalled()
  })
})

describe("sanitizeNewsText", () => {
  it("returns plain text untouched", async () => {
    const { sanitizeNewsText } = await loadModule()
    expect(sanitizeNewsText("Привет мир!")).toBe("Привет мир!")
  })

  it("drops markup when it contains HTML tags", async () => {
    const { sanitizeNewsText } = await loadModule()
    expect(sanitizeNewsText("Привет <strong>мир</strong>!")).toBe("")
  })
})

