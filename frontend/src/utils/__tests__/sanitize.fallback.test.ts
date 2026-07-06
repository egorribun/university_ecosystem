import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { sanitize_rich_text, strip_html } from "wasm-sanitizer"
import { logWarning } from "@/app/logger"
import { sanitizeNewsHtml, sanitizeNewsText } from "../sanitize"

// This file mocks the wasm-sanitizer package per-file (vi.mock is hoisted) so we
// can drive the RZ-24-04 regex fallback + Trusted Types policy-failure branches
// that the WASM-initialized happy path in setupTests.ts never reaches.
vi.mock("wasm-sanitizer", () => ({
  sanitize_rich_text: vi.fn((s: string) => s),
  strip_html: vi.fn((s: string) => s),
}))

vi.mock("@/app/logger", () => ({
  logWarning: vi.fn((..._args: unknown[]) => undefined),
}))

type TrustedTypesWindow = Window & {
  trustedTypes?: unknown
  __dompurifyNewsPolicy?: unknown
}

const win = window as unknown as TrustedTypesWindow
const originalTrustedTypes = win.trustedTypes

beforeEach(() => {
  vi.clearAllMocks()
  delete win.__dompurifyNewsPolicy
  // Default: no Trusted Types support, so sanitizeNewsHtml uses the direct
  // sanitize_rich_text path (or its catch fallback).
  win.trustedTypes = undefined
})

afterEach(() => {
  win.trustedTypes = originalTrustedTypes
  delete win.__dompurifyNewsPolicy
})

// ---------------------------------------------------------------------------
// (a) wasm-sanitizer unavailable / throwing -> regex fallback strips tags
// ---------------------------------------------------------------------------
describe("sanitizeNewsHtml — regex fallback (RZ-24-04)", () => {
  it("falls back to stripping tags when sanitize_rich_text throws", async () => {
    vi.mocked(sanitize_rich_text).mockImplementation(() => {
      throw new Error("wasm unavailable")
    })
    const result = await sanitizeNewsHtml("<div>alert(1)</div><p>hello</p>")
    expect(result).toBe("alert(1)hello")
  })

  it("never renders nothing — preserves text content on fallback", async () => {
    vi.mocked(sanitize_rich_text).mockImplementation(() => {
      throw new Error("boom")
    })
    const result = await sanitizeNewsHtml("<b>visible text</b>")
    expect(result).toBe("visible text")
  })

  it("uses sanitize_rich_text directly when it does not throw (no Trusted Types)", async () => {
    vi.mocked(sanitize_rich_text).mockImplementation((s: string) => `[clean]${s}`)
    const result = await sanitizeNewsHtml("<p>x</p>")
    expect(result).toBe("[clean]<p>x</p>")
    expect(sanitize_rich_text).toHaveBeenCalledWith("<p>x</p>")
  })

  it("coerces null/undefined to empty string before fallback", async () => {
    vi.mocked(sanitize_rich_text).mockImplementation(() => {
      throw new Error("boom")
    })
    expect(await sanitizeNewsHtml(null)).toBe("")
    expect(await sanitizeNewsHtml(undefined)).toBe("")
  })
})

describe("sanitizeNewsText — regex fallback (RZ-24-04)", () => {
  it("falls back to stripping tags when strip_html throws", async () => {
    vi.mocked(strip_html).mockImplementation(() => {
      throw new Error("wasm unavailable")
    })
    const result = await sanitizeNewsText("<span>plain</span> <i>text</i>")
    expect(result).toBe("plain text")
  })

  it("uses strip_html directly when it does not throw", async () => {
    vi.mocked(strip_html).mockImplementation((s: string) => `[stripped]${s}`)
    const result = await sanitizeNewsText("<p>y</p>")
    expect(result).toBe("[stripped]<p>y</p>")
    expect(strip_html).toHaveBeenCalledWith("<p>y</p>")
  })

  it("coerces null/undefined to empty string", async () => {
    vi.mocked(strip_html).mockImplementation((s: string) => s)
    expect(await sanitizeNewsText(null)).toBe("")
    expect(await sanitizeNewsText(undefined)).toBe("")
  })
})

// ---------------------------------------------------------------------------
// (b) Trusted Types policy creation failure -> policy = false flag path
// ---------------------------------------------------------------------------
describe("sanitizeNewsHtml — Trusted Types policy creation failure", () => {
  it("sets __dompurifyNewsPolicy = false and falls back to direct sanitize when createPolicy throws", async () => {
    const factory = {
      createPolicy: vi.fn(() => {
        throw new Error("CSP rejects trusted-types policy")
      }),
    }
    win.trustedTypes = factory
    vi.mocked(sanitize_rich_text).mockImplementation((s: string) => `[clean]${s}`)

    const result = await sanitizeNewsHtml("<p>z</p>")

    expect(factory.createPolicy).toHaveBeenCalledTimes(1)
    expect(win.__dompurifyNewsPolicy).toBe(false)
    expect(logWarning).toHaveBeenCalledWith(
      "Unable to create dompurify-news trusted types policy",
      expect.objectContaining({ error: expect.any(Error) })
    )
    // policy resolved to null -> direct sanitize_rich_text path used
    expect(result).toBe("[clean]<p>z</p>")
  })

  it("does not retry createPolicy once __dompurifyNewsPolicy is already false (cached failure)", async () => {
    const factory = {
      createPolicy: vi.fn(() => {
        throw new Error("CSP rejects trusted-types policy")
      }),
    }
    win.trustedTypes = factory
    win.__dompurifyNewsPolicy = false
    vi.mocked(sanitize_rich_text).mockImplementation((s: string) => s)

    await sanitizeNewsHtml("<p>a</p>")

    expect(factory.createPolicy).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// (c) policy caching on the 2nd call
// ---------------------------------------------------------------------------
describe("sanitizeNewsHtml — Trusted Types policy caching", () => {
  it("creates the policy once and reuses the cached instance on the 2nd call", async () => {
    const createHTML = vi.fn((s: string) => `[tt]${s}`)
    const policy = { createHTML }
    const factory = {
      createPolicy: vi.fn(() => policy),
    }
    win.trustedTypes = factory

    const first = await sanitizeNewsHtml("<p>1</p>")
    const second = await sanitizeNewsHtml("<p>2</p>")

    expect(factory.createPolicy).toHaveBeenCalledTimes(1)
    expect(win.__dompurifyNewsPolicy).toBe(policy)
    expect(first).toBe("[tt]<p>1</p>")
    expect(second).toBe("[tt]<p>2</p>")
    expect(createHTML).toHaveBeenCalledTimes(2)
    // WASM sanitize path never touched when a policy is in play
    expect(sanitize_rich_text).not.toHaveBeenCalled()
  })

  it("returns null policy (no createPolicy call) when trustedTypes is absent", async () => {
    win.trustedTypes = undefined
    vi.mocked(sanitize_rich_text).mockImplementation((s: string) => `[direct]${s}`)

    const result = await sanitizeNewsHtml("<p>q</p>")

    expect(result).toBe("[direct]<p>q</p>")
    expect(win.__dompurifyNewsPolicy).toBeUndefined()
  })
})
