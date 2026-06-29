import { describe, expect, it, vi, beforeEach } from "vitest"

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
  })
})
