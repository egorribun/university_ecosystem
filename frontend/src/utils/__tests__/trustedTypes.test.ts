import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { createTrustedScriptURL, ensureTrustedTypesPolicies, sanitizeHTML } from "../trustedTypes"
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
    vi.unstubAllEnvs()
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

  it("creates and then reuses both application policies", async () => {
    const policyRules = new Map<string, Record<string, (value: string) => string>>()
    const mockFactory = {
      createPolicy: vi.fn((name: string, rules: Record<string, (value: string) => string>) => {
        policyRules.set(name, rules)
        return rules
      }),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory

    await ensureTrustedTypesPolicies()
    await ensureTrustedTypesPolicies()

    expect(mockFactory.createPolicy).toHaveBeenCalledTimes(2)
    expect(policyRules.get("app")?.createHTML?.("<i>app</i>")).toBe("<i>app</i> (sanitized)")
    expect(policyRules.get("app")?.createScriptURL?.("/safe.js")).toContain("/safe.js")
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

  it("records app policy creation failure and degrades script URLs to raw values", async () => {
    const mockFactory = {
      createPolicy: vi.fn((name: string) => {
        if (name === "app") {
          throw new Error("App policy forbidden by CSP")
        }
        return { createHTML: vi.fn() }
      }),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})

    await ensureTrustedTypesPolicies()

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Failed to create app policy"),
      expect.anything()
    )
    expect(createTrustedScriptURL("/safe.js")).toBe("/safe.js")
    consoleSpy.mockRestore()
  })

  it("honors cached policy failure sentinels without recreating policies", async () => {
    const win = window as unknown as {
      __ttSanitizePolicy?: unknown
      __ttAppPolicy?: unknown
      trustedTypes?: unknown
    }
    const createPolicy = vi.fn()
    win.trustedTypes = { createPolicy }
    win.__ttSanitizePolicy = false
    win.__ttAppPolicy = false

    await expect(sanitizeHTML("<b>fallback</b>")).resolves.toBe("<b>fallback</b> (sanitized)")
    expect(createTrustedScriptURL("/fallback.js")).toBe("/fallback.js")
    expect(createPolicy).not.toHaveBeenCalled()
  })

  it("allows the configured backend origin for trusted script URLs", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_BACKEND_ORIGIN", "https://backend.example")
    const { createTrustedScriptURL: createScriptURL } = await import("../trustedTypes")
    const factory = {
      createPolicy: vi.fn(
        (_name: string, rules: Record<string, (value: string) => string>) => rules
      ),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = factory

    expect(createScriptURL("https://backend.example/assets/runtime.js")).toBe(
      "https://backend.example/assets/runtime.js"
    )
  })

  it("ignores a malformed backend origin instead of widening the allowlist", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_BACKEND_ORIGIN", "http://[")
    const { createTrustedScriptURL: createScriptURL } = await import("../trustedTypes")
    const factory = {
      createPolicy: vi.fn(
        (_name: string, rules: Record<string, (value: string) => string>) => rules
      ),
    }
    ;(window as unknown as { trustedTypes: unknown }).trustedTypes = factory

    expect(() => createScriptURL("https://evil.example/malice.js")).toThrow("Blocked script origin")
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
