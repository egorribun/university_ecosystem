import { afterEach, describe, expect, it, vi, beforeEach } from "vitest"

const mocks = vi.hoisted(() => ({
  apiDefaults: { baseURL: "/api" },
}))

vi.mock("@/api/client", () => ({
  default: { defaults: { baseURL: mocks.apiDefaults.baseURL } },
}))

import { resolveBackendOrigin, buildAvatarUrl } from "@/utils/avatar"

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiDefaults.baseURL = "/api"
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("avatar utilities", () => {
  describe("resolveBackendOrigin", () => {
    it("returns locationOrigin when baseURL is relative", () => {
      const result = resolveBackendOrigin({
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toBe("https://example.com")
    })

    it("returns origin from absolute baseURL", () => {
      const result = resolveBackendOrigin({
        baseURL: "https://api.example.com/v1",
        locationOrigin: "https://frontend.example.com",
      })
      expect(result).toBe("https://api.example.com")
    })

    it("returns locationOrigin as fallback when baseURL is empty", () => {
      const result = resolveBackendOrigin({
        baseURL: "",
        locationOrigin: "https://example.com",
      })
      expect(result).toBe("https://example.com")
    })

    it("returns undefined when both baseURL and locationOrigin are missing", () => {
      const result = resolveBackendOrigin({
        baseURL: undefined,
        locationOrigin: undefined,
      })
      expect(result).toBe("http://localhost:3000")
    })

    it("handles invalid baseURL gracefully", () => {
      const result = resolveBackendOrigin({
        baseURL: ":::invalid",
        locationOrigin: "https://example.com",
      })
      // Falls back to locationOrigin on URL parse error
      expect(result).toBe("https://example.com")
    })

    it("uses the dummy origin when a relative base URL has no location fallback", () => {
      expect(resolveBackendOrigin({ baseURL: "/api", locationOrigin: null as unknown as string })).toBe(
        "http://__avatar__"
      )
    })

    it("falls back when URL construction rejects the base URL", () => {
      expect(
        resolveBackendOrigin({ baseURL: "http://[invalid", locationOrigin: "https://example.com" })
      ).toBe("https://example.com")
    })

    it("works with default parameters", () => {
      const result = resolveBackendOrigin()
      // Should default to api.defaults.baseURL and window.location.origin
      expect(result).toBe("http://localhost:3000")
    })

    it("handles window object missing or window.location throwing", () => {
      const originalWindow = global.window
      try {
        // Temporarily delete window
        Object.defineProperty(global, "window", {
          value: undefined,
          writable: true,
          configurable: true,
        })
        const result = resolveBackendOrigin({ baseURL: "", locationOrigin: undefined })
        expect(result).toBeUndefined()
      } finally {
        Object.defineProperty(global, "window", {
          value: originalWindow,
          writable: true,
          configurable: true,
        })
      }
    })

    it("handles window.location throwing error when accessing origin", () => {
      const originalWindow = global.window
      try {
        const fakeWindow = {
          get location() {
            throw new Error("inaccessible location")
          },
        }
        Object.defineProperty(global, "window", {
          value: fakeWindow,
          writable: true,
          configurable: true,
        })
        const result = resolveBackendOrigin({ baseURL: "", locationOrigin: undefined })
        expect(result).toBeUndefined()
      } finally {
        Object.defineProperty(global, "window", {
          value: originalWindow,
          writable: true,
          configurable: true,
        })
      }
    })
  })

  describe("buildAvatarUrl", () => {
    it("returns empty string for null rawUrl", () => {
      expect(buildAvatarUrl(null, "123")).toBe("")
    })

    it("returns empty string for undefined rawUrl", () => {
      expect(buildAvatarUrl(undefined, "123")).toBe("")
    })

    it("returns empty string for empty string rawUrl", () => {
      expect(buildAvatarUrl("", "123")).toBe("")
    })

    it("returns empty string for whitespace-only rawUrl", () => {
      expect(buildAvatarUrl("   ", "123")).toBe("")
    })

    it("returns absolute URL unchanged when already absolute (https)", () => {
      const url = "https://cdn.example.com/avatar.jpg"
      expect(buildAvatarUrl(url, "123")).toBe(url)
    })

    it("returns absolute URL unchanged when already absolute (http)", () => {
      const url = "http://cdn.example.com/avatar.jpg"
      expect(buildAvatarUrl(url, "123")).toBe(url)
    })

    it("returns protocol-relative URL unchanged", () => {
      const url = "//cdn.example.com/avatar.jpg"
      expect(buildAvatarUrl(url, "123")).toBe(url)
    })

    it("prepends origin and appends uid for relative URL", () => {
      const result = buildAvatarUrl("/avatars/photo.jpg", "42", {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("https://example.com")
      expect(result).toContain("/avatars/photo.jpg")
      expect(result).toContain("uid=42")
    })

    it("adds leading slash to relative URL without one", () => {
      const result = buildAvatarUrl("avatars/photo.jpg", "42", {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("/avatars/photo.jpg")
    })

    it("appends uid as query parameter", () => {
      const result = buildAvatarUrl("/avatar.jpg", "user-99", {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("uid=user-99")
    })

    it("handles numeric uid", () => {
      const result = buildAvatarUrl("/avatar.jpg", 123, {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("uid=123")
    })

    it("handles URL that already has query parameters", () => {
      const result = buildAvatarUrl("/avatar.jpg?size=large", "42", {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("uid=42")
      expect(result).toContain("size=large")
    })

    it("handles relative URL appendUid parse failure", () => {
      // Pass a malformed string that triggers URL parsing failure in new URL(..., DUMMY_ORIGIN)
      // and triggers the catch block in appendUid.
      // Space is usually handled/encoded by URL, so we can use invalid characters for URL parsing or backslash.
      // An invalid URL template such as "http://invalid domain:::" or similar could fail.
      const result = buildAvatarUrl(":::invalid-url-path", "123", {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("uid=123")
    })

    it("handles relative URL appendUid parse failure with query parameters", () => {
      const result = buildAvatarUrl(":::invalid-url-path?size=large", "123", {
        baseURL: "/api",
        locationOrigin: "https://example.com",
      })
      expect(result).toContain("uid=123")
      expect(result).toContain("size=large")
    })

    it("uses the appendUid fallback when URL construction rejects a relative path", () => {
      const originalURL = globalThis.URL
      class RejectingURL extends originalURL {
        constructor(input: string | URL, base?: string | URL) {
          if (String(input) === "/force-invalid") throw new TypeError("invalid relative URL")
          super(input, base)
        }
      }
      vi.stubGlobal("URL", RejectingURL)

      expect(
        buildAvatarUrl("/force-invalid", "a user", {
          baseURL: "/api",
          locationOrigin: "https://example.com",
        })
      ).toContain("uid=a%20user")
    })

    it("returns the relative URL when no backend origin is available", () => {
      expect(
        buildAvatarUrl("avatar.jpg", "42", {
          baseURL: "",
          locationOrigin: null as unknown as string,
        })
      ).toBe("/avatar.jpg?uid=42")
    })
  })
})
