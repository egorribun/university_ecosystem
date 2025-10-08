import { describe, expect, it } from "vitest";
import { addCacheBuster, resolveMediaUrl } from "@/utils/media";

const ORIGIN = "https://backend.example";

describe("resolveMediaUrl", () => {
  it("returns undefined for empty input", () => {
    expect(resolveMediaUrl(undefined, ORIGIN)).toBeUndefined();
    expect(resolveMediaUrl("   ", ORIGIN)).toBeUndefined();
  });

  it("keeps absolute URLs untouched", () => {
    const absolute = "https://cdn.example/images/photo.png";
    expect(resolveMediaUrl(absolute, ORIGIN)).toBe(absolute);
  });

  it("normalizes static prefix and encodes unicode segments", () => {
    const url = resolveMediaUrl(" /static/аватары/фото 1.png", ORIGIN);
    expect(url).toBe(
      "https://backend.example/media/%D0%B0%D0%B2%D0%B0%D1%82%D0%B0%D1%80%D1%8B/%D1%84%D0%BE%D1%82%D0%BE%201.png",
    );
  });

  it("collapses duplicate slashes and preserves query and hash", () => {
    const url = resolveMediaUrl("media//gallery//item.jpg?foo=bar&foo=bar#секция", ORIGIN);
    expect(url).toBe(
      "https://backend.example/media/gallery/item.jpg?foo=bar&foo=bar#%D1%81%D0%B5%D0%BA%D1%86%D0%B8%D1%8F",
    );
  });

  it("falls back to window origin when explicit origin is missing", () => {
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
});

describe("addCacheBuster", () => {
  it("adds the version query parameter", () => {
    expect(addCacheBuster("https://example.com/image.png", 123)).toBe(
      "https://example.com/image.png?v=123",
    );
  });

  it("updates an existing version parameter", () => {
    expect(addCacheBuster("https://example.com/image.png?v=1", "456")).toBe(
      "https://example.com/image.png?v=456",
    );
  });

  it("handles relative URLs gracefully", () => {
    expect(addCacheBuster("/media/photo.png", 7)).toBe("/media/photo.png?v=7");
  });
});
