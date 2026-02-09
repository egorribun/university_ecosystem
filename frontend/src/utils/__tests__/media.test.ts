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
  })
})




