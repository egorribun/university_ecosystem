import { beforeEach, describe, expect, it, vi } from "vitest";

const loadSanitizeModule = async () => import("../sanitize");

const readValue = (value: string | TrustedHTML) =>
  typeof value === "string" ? value : (value as unknown as { toString(): string }).toString();

beforeEach(() => {
  vi.resetModules();
  delete (window as any).__dompurifyNewsPolicy;
  delete (window as any).trustedTypes;
});

describe("sanitizeNewsHtml", () => {
  it("strips scripts and dangerous attributes", async () => {
    const { sanitizeNewsHtml } = await loadSanitizeModule();
    const dirty = '<p onclick="alert(1)">Hello</p><script>alert(1)</script><img src="x" onerror="alert(1)" />';
    const sanitized = readValue(sanitizeNewsHtml(dirty));
    expect(sanitized).toContain("<p>Hello</p>");
    expect(sanitized).not.toContain("onclick");
    expect(sanitized).not.toContain("<script>");
    expect(sanitized).not.toContain("onerror");
  });

  it("uses trusted types policy when available", async () => {
    const policy = { createHTML: vi.fn((input: string) => `trusted:${input}`) };
    const createPolicy = vi.fn(() => policy);
    (window as any).trustedTypes = { createPolicy };

    const { sanitizeNewsHtml } = await loadSanitizeModule();
    const dirty = "<strong>Secure</strong>";
    const result = sanitizeNewsHtml(dirty);

    expect(createPolicy).toHaveBeenCalledWith("dompurify-news", expect.any(Object));
    expect(policy.createHTML).toHaveBeenCalledWith(dirty);
    expect(result).toBe(`trusted:${dirty}`);
    expect((window as any).__dompurifyNewsPolicy).toBe(policy);
  });

  it("falls back to DOMPurify when policy creation fails", async () => {
    const createPolicy = vi.fn(() => {
      throw new Error("policy disabled");
    });
    (window as any).trustedTypes = { createPolicy };

    const { sanitizeNewsHtml } = await loadSanitizeModule();
    const dirty = '<em data-test="1">ok</em>';
    const sanitized = readValue(sanitizeNewsHtml(dirty));

    expect(createPolicy).toHaveBeenCalled();
    expect(sanitized).toBe("<em>ok</em>");
    expect((window as any).__dompurifyNewsPolicy).toBe(false);
  });
});

describe("sanitizeNewsText", () => {
  it("drops markup and keeps plain strings intact", async () => {
    const { sanitizeNewsText } = await loadSanitizeModule();
    const dirty = "<h1>Заголовок</h1><p>Текст <strong>важный</strong></p>";
    expect(sanitizeNewsText(dirty)).toBe("");
    expect(sanitizeNewsText("Просто текст")).toBe("Просто текст");
  });
});
