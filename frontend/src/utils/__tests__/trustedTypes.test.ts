import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { sanitizeHTML, createTrustedScriptURL } from "../trustedTypes"
import { sanitize_rich_text } from "wasm-sanitizer"

vi.mock("wasm-sanitizer", () => ({
  sanitize_rich_text: vi.fn((s: string) => s + " (sanitized)"),
}))

describe("trustedTypes util", () => {
  const originalTrustedTypes = (window as unknown as { trustedTypes: unknown }).trustedTypes

  beforeEach(() => {
    vi.clearAllMocks()
    // Clear cached policies from window
    delete (window as unknown as { __ttSanitizePolicy?: unknown }).__ttSanitizePolicy
    delete (window as unknown as { __ttAppPolicy?: unknown }).__ttAppPolicy
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = originalTrustedTypes
  })

  afterEach(() => {
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = originalTrustedTypes
  })

  it("sanitizes HTML directly when TrustedTypes is not supported", async () => {
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = undefined
    const input = "<b>hello</b>"
    const result = await sanitizeHTML(input)
    expect(result).toBe("<b>hello</b> (sanitized)")
    expect(sanitize_rich_text).toHaveBeenCalledWith(input)
  })

  it("uses TrustedTypes policy when supported", async () => {
    const createHTML = vi.fn((s: string) => s + " (policy sanitized)")
    const mockPolicy = {
      createHTML,
    }
    const mockFactory = {
      createPolicy: vi.fn((name) => {
        if (name === "wasm-sanitizer") return mockPolicy
        return {}
      }),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory

    const result = await sanitizeHTML("<b>test</b>")
    expect(result).toBe("<b>test</b> (policy sanitized)")
    expect(mockFactory.createPolicy).toHaveBeenCalledWith("wasm-sanitizer", expect.anything())
    expect(createHTML).toHaveBeenCalledWith("<b>test</b>")
  })

  it("enforces allowed script origins in app policy", () => {
    let policyCallback: (val: string) => string
    const mockFactory = {
      createPolicy: vi.fn((name, options) => {
        if (name === "app") {
          policyCallback = options.createScriptURL
          return {
            createScriptURL: (val: string) => policyCallback(val),
          }
        }
        return {}
      }),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory

    // This creates the policy and captures the callback
    createTrustedScriptURL("/foo.js")

    expect(mockFactory.createPolicy).toHaveBeenCalledWith("app", expect.anything())

    // Should allow same origin (relative URL)
    expect(() => policyCallback("/valid.js")).not.toThrow()

    // Should allow same origin (absolute URL)
    expect(() => policyCallback(window.location.origin + "/valid.js")).not.toThrow()

    // Should block unknown external origin
    expect(() => policyCallback("https://evil.com/malice.js")).toThrow(TypeError)
  })

  it("handles policy creation failure gracefully by falling back to WASM directly", async () => {
    const mockFactory = {
      createPolicy: vi.fn(() => {
        throw new Error("Creation forbidden by CSP or browser extension")
      }),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})

    const result = await sanitizeHTML("hello")

    // Result should be from WASM sanitizer directly
    expect(result).toBe("hello (sanitized)")
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Failed to create sanitize policy"),
      expect.anything()
    )

    consoleSpy.mockRestore()
  })

  it("propagates createScriptURL errors to caller", () => {
    const mockPolicy = {
      createScriptURL: vi.fn(() => {
        throw new TypeError("Blocked origin")
      }),
    }
    const mockFactory = {
      createPolicy: vi.fn(() => mockPolicy),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory

    expect(() => createTrustedScriptURL("https://evil.com")).toThrow("Blocked origin")
  })
})
