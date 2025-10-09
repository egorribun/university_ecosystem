import { afterAll, beforeEach, describe, expect, it, vi } from "vitest"

const originalLocation = window.location

const setWindowOrigin = (origin: string) => {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, origin } as Location,
  })
}

const setEnvOrigin = (origin?: string) => {
  const env = import.meta.env as any
  if (origin === undefined) {
    delete env.VITE_BACKEND_ORIGIN
  } else {
    env.VITE_BACKEND_ORIGIN = origin
  }
}

afterAll(() => {
  Object.defineProperty(window, "location", { configurable: true, value: originalLocation })
  setEnvOrigin(undefined)
})

describe("resolveMediaUrl", () => {
  beforeEach(() => {
    vi.resetModules()
    setEnvOrigin(undefined)
    setWindowOrigin("https://backend.example")
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

  it("builds URL from window origin when env is missing", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("media/avatar.png")).toBe("https://backend.example/media/avatar.png")
  })

  it("prefers env origin when provided", async () => {
    setEnvOrigin("https://env.example")
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("media/file.png")).toBe("https://env.example/media/file.png")
  })

  it("encodes unicode path segments and collapses slashes", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl(" /media/фото 1.png")).toBe(
      "https://backend.example/media/%D1%84%D0%BE%D1%82%D0%BE%201.png",
    )
  })

  it("preserves query strings on relative URLs", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("media/picture.png?token=abc&expires=1"))
      .toBe("https://backend.example/media/picture.png?token=abc&expires=1")
  })

  it("keeps query and hash when encoding path segments", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("/media/фото 2.png?x=1#anchor"))
      .toBe("https://backend.example/media/%D1%84%D0%BE%D1%82%D0%BE%202.png?x=1#anchor")
  })

  it("supports overriding origin", async () => {
    const { resolveMediaUrl } = await import("@/utils/media")
    expect(resolveMediaUrl("avatar.png", "https://custom.example"))
      .toBe("https://custom.example/avatar.png")
  })
})

describe("addVersionParam", () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it("appends version parameter", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("https://example.com/image.png", 123)).toBe(
      "https://example.com/image.png?v=123",
    )
  })

  it("updates existing parameter", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("https://example.com/image.png?v=1", 2)).toBe(
      "https://example.com/image.png?v=2",
    )
  })

  it("handles relative URLs", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("/media/photo.png", 7)).toBe("/media/photo.png?v=7")
  })

  it("returns original URL when version is not provided", async () => {
    const { addVersionParam } = await import("@/utils/media")
    expect(addVersionParam("https://example.com/image.png")).toBe(
      "https://example.com/image.png",
    )
  })
})
