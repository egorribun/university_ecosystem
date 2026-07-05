import { describe, expect, it } from "vitest"
import { sanitizeArticleHtml } from "../sanitizeArticleHtml"

describe("sanitizeArticleHtml", () => {
  // ---------------------------------------------------------------------------
  // Empty / falsy inputs
  // ---------------------------------------------------------------------------
  it("returns empty string for empty string", () => {
    expect(sanitizeArticleHtml("")).toBe("")
  })

  // ---------------------------------------------------------------------------
  // Normal content passes through untouched
  // ---------------------------------------------------------------------------
  it("returns plain text unchanged", () => {
    expect(sanitizeArticleHtml("Hello, world!")).toBe("Hello, world!")
  })

  it("preserves allowed HTML structure (p, h2, ul, li, a, img)", () => {
    const html =
      "<h2>Title</h2><p>Some <strong>bold</strong> text.</p><ul><li>Item</li></ul>" +
      '<a href="https://example.com">Link</a>' +
      '<img src="https://img.example.com/photo.jpg" alt="Photo">'
    expect(sanitizeArticleHtml(html)).toBe(html)
  })

  it("preserves GFM tables", () => {
    const html =
      "<table><thead><tr><th>A</th><th>B</th></tr></thead>" +
      "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    expect(sanitizeArticleHtml(html)).toBe(html)
  })

  it("preserves <hr> horizontal rule", () => {
    expect(sanitizeArticleHtml("<p>Before</p><hr><p>After</p>")).toBe(
      "<p>Before</p><hr><p>After</p>"
    )
  })

  it("preserves <code> and <pre> blocks", () => {
    const html = "<pre><code>const x = 1;</code></pre>"
    expect(sanitizeArticleHtml(html)).toBe(html)
  })

  // ---------------------------------------------------------------------------
  // Dangerous tag stripping
  // ---------------------------------------------------------------------------
  it("removes <script> elements", () => {
    const result = sanitizeArticleHtml("<p>Hello</p><script>xss_payload</script>")
    expect(result).not.toContain("<script")
    expect(result).not.toContain("</script>")
    expect(result).not.toContain("xss_payload")
  })

  it("removes <style> tags", () => {
    const result = sanitizeArticleHtml("<style>body{background:red}</style><p>ok</p>")
    expect(result).not.toContain("<style>")
  })

  it("removes <iframe> tags", () => {
    const result = sanitizeArticleHtml('<iframe src="https://evil.com" />')
    expect(result).not.toContain("<iframe")
  })

  it("removes <form> and <input> tags", () => {
    const result = sanitizeArticleHtml('<form action="/steal"><input type="text" /></form>')
    expect(result).not.toContain("<form")
    expect(result).not.toContain("<input")
  })

  it("removes <embed> and <object> tags", () => {
    expect(sanitizeArticleHtml("<embed src='x.swf'>")).not.toContain("<embed")
    expect(sanitizeArticleHtml('<object data="x.swf">')).not.toContain("<object")
  })

  // ---------------------------------------------------------------------------
  // Event handler attribute stripping
  // ---------------------------------------------------------------------------
  it("removes onclick attributes", () => {
    const result = sanitizeArticleHtml('<a href="https://x.com" onclick="alert(1)">Click</a>')
    expect(result).not.toContain("onclick")
  })

  it("removes onerror attributes", () => {
    const result = sanitizeArticleHtml('<img src="x.jpg" onerror="alert(1)">')
    expect(result).not.toContain("onerror")
  })

  it("removes onmouseover attributes", () => {
    const result = sanitizeArticleHtml('<p onmouseover="evil()">Hover me</p>')
    expect(result).not.toContain("onmouseover")
  })

  // ---------------------------------------------------------------------------
  // JavaScript URL blocking
  // ---------------------------------------------------------------------------
  it("removes javascript: in href", () => {
    const result = sanitizeArticleHtml('<a href="javascript:alert(1)">XSS</a>')
    expect(result).not.toMatch(/href\s*=\s*["']javascript:/i)
  })

  it("removes javascript: in src", () => {
    const result = sanitizeArticleHtml('<img src="javascript:alert(1)">')
    expect(result).not.toMatch(/src\s*=\s*["']javascript:/i)
  })

  // ---------------------------------------------------------------------------
  // data: URL blocking (non-image)
  // ---------------------------------------------------------------------------
  it("removes data: URLs in src for non-image types", () => {
    const result = sanitizeArticleHtml('<iframe src="data:text/html,<h1>hi</h1>">')
    expect(result).not.toMatch(/src\s*=\s*["']data:text/i)
  })

  it("preserves data: URLs for images (allowed by the regex)", () => {
    // data:image/ is explicitly allowed for inline article images.
    const input = '<img src="data:image/png;base64,abc123">'
    const result = sanitizeArticleHtml(input)
    expect(result).toContain("data:image/png")
  })

  // ---------------------------------------------------------------------------
  // Defense-in-depth: structural attribute removal is case-insensitive
  // ---------------------------------------------------------------------------
  it("removes mixed-case event handler attributes", () => {
    const sneaky = "<p>text</p><img ONerror=evil()>"
    const result = sanitizeArticleHtml(sneaky)
    expect(result).not.toContain("ONerror")
    expect(result).not.toContain("onerror")
  })
})
