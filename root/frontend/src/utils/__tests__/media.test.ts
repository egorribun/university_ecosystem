import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type MediaModule = typeof import("../media")

const originalDescriptor = Object.getOwnPropertyDescriptor(window, "location")

const restoreLocation = () => {
  if (originalDescriptor) {
    Object.defineProperty(window, "location", originalDescriptor)
  }
}

const importMedia = async (): Promise<MediaModule> => {
  return import("../media")
}

beforeEach(() => {
  vi.resetModules()
  vi.unstubAllEnvs()
  restoreLocation()
})

afterEach(() => {
  vi.resetModules()
  vi.unstubAllEnvs()
  restoreLocation()
})

describe("resolveMediaUrl", () => {
  it("returns fallback for nullish or empty values", async () => {
    const { resolveMediaUrl } = await importMedia()
    expect(resolveMediaUrl(undefined, undefined, { fallback: "fallback" })).toBe("fallback")
    expect(resolveMediaUrl(null, undefined, { fallback: "fallback" })).toBe("fallback")
    expect(resolveMediaUrl("   ", undefined, { fallback: "fallback" })).toBe("fallback")
  })

  it("normalizes relative paths against the configured backend origin", async () => {
    vi.stubEnv("VITE_BACKEND_ORIGIN", "https://api.example.com//")
    const { resolveMediaUrl } = await importMedia()
    expect(resolveMediaUrl("static/uploads/avatar.png")).toBe(
      "https://api.example.com/media/uploads/avatar.png",
    )
  })

  it("honours the explicit origin argument and preserves query parameters", async () => {
    const { resolveMediaUrl } = await importMedia()
    const url = resolveMediaUrl(
      "media/profile/photo 01.png?token=abc&lang=ru",
      "https://cdn.university.example",
    )
    expect(url).toBe("https://cdn.university.example/media/profile/photo%2001.png?token=abc&lang=ru")
  })

  it("falls back to the browser origin when no backend origin is provided", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        origin: "https://portal.example.edu",
        href: "https://portal.example.edu/dashboard",
      } as Location,
    })

    const { resolveMediaUrl } = await importMedia()
    const resolved = resolveMediaUrl("media/gallery//photo.jpg", "")
    expect(resolved).toBe("https://portal.example.edu/media/gallery/photo.jpg")
  })

  it("produces safe relative URLs when no origin can be determined", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { origin: "" } as Location,
    })

    const { resolveMediaUrl } = await importMedia()
    expect(resolveMediaUrl("static//attachments/report.pdf", "")).toBe("/media/attachments/report.pdf")
  })
})

describe("appendCacheBust", () => {
  it("adds the cache bust parameter to absolute URLs", async () => {
    const { appendCacheBust } = await importMedia()
    expect(appendCacheBust("https://cdn.example.com/file.css", 123)).toBe(
      "https://cdn.example.com/file.css?v=123",
    )
  })

  it("appends to existing query strings and encodes the value", async () => {
    const { appendCacheBust } = await importMedia()
    expect(appendCacheBust("/media/file.jpg?size=large", "ru-RU"))
      .toBe("/media/file.jpg?size=large&v=ru-RU")
  })

  it("gracefully handles invalid URLs", async () => {
    const { appendCacheBust } = await importMedia()
    expect(appendCacheBust("/media/file[1].png", "2025-01-01"))
      .toBe("/media/file[1].png?v=2025-01-01")
  })
})

