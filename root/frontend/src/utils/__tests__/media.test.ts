import { beforeEach, describe, expect, it, vi } from "vitest";

const ORIGIN = "https://backend.example";

const loadMediaUtils = async () => import("../media");

beforeEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
});

describe("resolveMediaUrl", () => {
  it("returns undefined for empty input", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    expect(resolveMediaUrl(undefined, ORIGIN)).toBeUndefined();
    expect(resolveMediaUrl("   ", ORIGIN)).toBeUndefined();
  });

  it("keeps absolute URLs untouched", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    const absolute = "https://cdn.example/images/photo.png";
    expect(resolveMediaUrl(absolute, ORIGIN)).toBe(absolute);
  });

  it("handles relative paths without leading slash", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    expect(resolveMediaUrl("media/avatar.png", ORIGIN)).toBe("https://backend.example/media/avatar.png");
  });

  it("normalizes static prefix and encodes unicode segments", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    const url = resolveMediaUrl(" /static/аватары/фото 1.png", ORIGIN);
    expect(url).toBe(
      "https://backend.example/media/%D0%B0%D0%B2%D0%B0%D1%82%D0%B0%D1%80%D1%8B/%D1%84%D0%BE%D1%82%D0%BE%201.png",
    );
  });

  it("preserves already encoded segments without double-encoding", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    const url = resolveMediaUrl("/media/gallery/%D0%A4%D0%BE%D1%82%D0%BE%202.png", ORIGIN);
    expect(url).toBe(
      "https://backend.example/media/gallery/%D0%A4%D0%BE%D1%82%D0%BE%202.png",
    );
  });

  it("collapses duplicate slashes and preserves query/hash", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    const url = resolveMediaUrl("media//gallery//item.jpg?foo=bar&foo=bar#секция", ORIGIN);
    expect(url).toBe(
      "https://backend.example/media/gallery/item.jpg?foo=bar&foo=bar#%D1%81%D0%B5%D0%BA%D1%86%D0%B8%D1%8F",
    );
  });

  it("returns fallback when origin is invalid", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    expect(resolveMediaUrl("/media/photo.png", "not a url", { fallback: "https://fallback" })).toBe(
      "https://fallback",
    );
  });

  it("falls back to window origin when explicit origin is missing", async () => {
    const { resolveMediaUrl } = await loadMediaUtils();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { origin: "https://app.local" } as Location,
    });
    try {
      expect(resolveMediaUrl("avatars/photo.png")).toBe("https://app.local/avatars/photo.png");
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }
  });

  it("uses VITE_BACKEND_ORIGIN as the default base", async () => {
    vi.stubEnv("VITE_BACKEND_ORIGIN", "https://env.example/base/");
    const { resolveMediaUrl } = await loadMediaUtils();
    expect(resolveMediaUrl("media/photo.png")).toBe("https://env.example/base/media/photo.png");
  });
});

describe("addCacheBust", () => {
  it("adds the version query parameter", async () => {
    const { addCacheBust } = await loadMediaUtils();
    expect(addCacheBust("https://example.com/image.png", 123)).toBe("https://example.com/image.png?v=123");
  });

  it("updates an existing version parameter", async () => {
    const { addCacheBust } = await loadMediaUtils();
    expect(addCacheBust("https://example.com/image.png?v=1", "456")).toBe("https://example.com/image.png?v=456");
  });

  it("handles relative URLs gracefully", async () => {
    const { addCacheBust } = await loadMediaUtils();
    expect(addCacheBust("/media/photo.png", 7)).toBe("/media/photo.png?v=7");
  });

  it("appends using fallback when URL constructor fails", async () => {
    const { addCacheBust } = await loadMediaUtils();
    expect(addCacheBust("not a url", "beta")).toBe("not a url?v=beta");
  });

  it("encodes version values", async () => {
    const { addCacheBust } = await loadMediaUtils();
    expect(addCacheBust("https://example.com/image.png", "1 2")).toBe("https://example.com/image.png?v=1+2");
  });
});
