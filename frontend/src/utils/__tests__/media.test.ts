import { afterAll, beforeEach, describe, expect, it, vi } from "vitest"

const originalEnv = { ...import.meta.env }

const setEnv = (key: string, value: unknown) => {
  const env = import.meta.env as Record<string, unknown>
  if (value === undefined) {
    delete env[key]
  } else {
    env[key] = value
  }
}

afterAll(() => {
  const env = import.meta.env as Record<string, unknown>
  for (const key of Object.keys(env)) {
    delete env[key]
  }
  Object.assign(env, originalEnv)
})

describe("resolveMediaUrl", () => {
  beforeEach(() => {
    vi.resetModules()
    setEnv("VITE_BACKEND_ORIGIN", undefined)
    setEnv("DEV", true)
  })

  it("returns empty string for empty input", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl(undefined)).toBe("")
    expect(resolveMediaUrl("   ")).toBe("")
  })

  it("keeps absolute URLs untouched", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    const absolute = "https://cdn.example/images/photo.png"
    expect(resolveMediaUrl(absolute)).toBe(absolute)
  })

  it("prefixes backend origin for media paths", async () => {
    setEnv("VITE_BACKEND_ORIGIN", "https://api.example.com")
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("/media/avatar.png")).toBe("https://api.example.com/media/avatar.png")
    expect(resolveMediaUrl("static/logo.svg")).toBe("https://api.example.com/static/logo.svg")
  })

  it("downgrades to relative path in dev when origin is missing", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("media/avatar.png")).toBe("/media/avatar.png")
  })

  it("falls back to relative path in production when origin is missing", async () => {
    setEnv("DEV", false)
    const { resolveMediaUrl } = await import("@/utils/media")
    // Now falls back to relative path instead of throwing
    expect(resolveMediaUrl("/media/avatar.png")).toBe("/media/avatar.png")
  })

  it("allows overriding origin explicitly", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("/media/avatar.png", "https://override.example")).toBe(
      "https://override.example/media/avatar.png"
    )
  })

  it("keeps unrelated relative paths untouched", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("images/photo.png")).toBe("images/photo.png")
  })
})

describe("addVersionParam", () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it("appends version parameter", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("https://example.com/image.png", 123)).toBe(
      "https://example.com/image.png?_v=123"
    )
  })

  it("updates existing parameter", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("https://example.com/image.png?_v=1", 2)).toBe(
      "https://example.com/image.png?_v=2"
    )
  })

  it("handles relative URLs", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("/media/photo.png", 7)).toBe("/media/photo.png?_v=7")
  })

  it("returns original URL when version is not provided", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("https://example.com/image.png")).toBe("https://example.com/image.png")
    expect(addVersionParam(undefined, 1)).toBe("")
  })

  it("falls back to string concatenation when URL parsing fails", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("http://[invalid", "a b")).toBe("http://[invalid?_v=a%20b")
    expect(addVersionParam("http://[invalid?existing=1", 3)).toBe("http://[invalid?existing=1&_v=3")
  })

  it("treats null and empty versions as no-op values", async () => {
    const { addVersionParam } = await import("@/utils/media")
    const url = "/media/image.png"
    expect(addVersionParam(url, null)).toBe(url)
    expect(addVersionParam(url, "")).toBe(url)
  })
})

describe("resolveMediaUrl security and proxy helpers", () => {
  it.each(["javascript:alert(1)", "vbscript:msgbox(1)", "data:text/html,<p>x</p>"])(
    "rejects dangerous protocol %s",
    async (value) => {
      const { resolveMediaUrl } = await import("@/utils/media")
      expect(resolveMediaUrl(`  ${value}`)).toBe("")
    }
  )

  it("keeps blob previews and protocol-relative URLs unchanged", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("blob:https://example.com/preview")).toBe(
      "blob:https://example.com/preview"
    )
    expect(resolveMediaUrl("//cdn.example.com/image.png")).toBe("//cdn.example.com/image.png")
  })

  it("creates an image proxy URL with width and normalized origin", async () => {
    const { resolveProxyImageUrl } = await import("@/utils/media")
    expect(resolveProxyImageUrl("media/photo.png", 320, "https://api.example.com///")).toBe(
      "https://api.example.com/api/v1/img/media/photo.png?w=320"
    )
  })

  it("supports an already proxied path and relative nginx mode", async () => {
    const { resolveProxyImageUrl } = await import("@/utils/media")
    expect(resolveProxyImageUrl("/api/v1/img/photo.png", undefined, "")).toBe(
      "/api/v1/img/photo.png"
    )
    expect(resolveProxyImageUrl("/media/photo.png", undefined, "")).toBe(
      "/api/v1/img/media/photo.png"
    )
    expect(resolveProxyImageUrl("/media/photo.png", undefined, undefined)).toBe(
      "/api/v1/img/media/photo.png"
    )
  })

  it("delegates non-media paths, absolute URLs, blobs, and empty input", async () => {
    const { resolveProxyImageUrl } = await import("@/utils/media")
    expect(resolveProxyImageUrl("avatar.png", undefined, "https://api.example.com")).toBe(
      "avatar.png"
    )
    expect(resolveProxyImageUrl("https://cdn.example.com/photo.png")).toBe(
      "https://cdn.example.com/photo.png"
    )
    expect(resolveProxyImageUrl("blob:https://example.com/preview")).toBe(
      "blob:https://example.com/preview"
    )
    expect(resolveProxyImageUrl(undefined)).toBe("")
  })
})

describe("sanitizeUrl", () => {
  it("allows safe protocols and relative paths", async () => {
    const { sanitizeUrl } = await import("@/utils/media")
    expect(sanitizeUrl("https://example.com/photo.png")).toBe("https://example.com/photo.png")
    expect(sanitizeUrl("/media/photo.png")).toBe(`${window.location.origin}/media/photo.png`)
    expect(sanitizeUrl("blob:https://example.com/preview")).toBe("blob:https://example.com/preview")
    expect(sanitizeUrl("mailto:user@example.com")).toBe("mailto:user@example.com")
    expect(sanitizeUrl("tel:+79990000000")).toBe("tel:+79990000000")
    expect(sanitizeUrl("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA")
  })

  it.each([
    "",
    "javascript:alert(1)",
    "vbscript:msgbox(1)",
    "data:text/html,<script>alert(1)</script>",
    "ftp://example.com/file",
    "file:///etc/passwd",
    "http://[invalid",
  ])("returns null for unsafe or malformed URL %s", async (value) => {
    const { sanitizeUrl } = await import("@/utils/media")
    expect(sanitizeUrl(value)).toBeNull()
  })

  it("uses the relative-path fallback when executed without window", async () => {
    const { sanitizeUrl } = await import("@/utils/media")
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window")
    Reflect.deleteProperty(globalThis, "window")
    try {
      expect(sanitizeUrl("/media/photo.png")).toBe("/media/photo.png")
    } finally {
      if (descriptor) Object.defineProperty(globalThis, "window", descriptor)
    }
  })
})
