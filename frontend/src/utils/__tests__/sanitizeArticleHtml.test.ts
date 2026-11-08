import { afterEach, describe, expect, it, vi } from "vitest"
import { render } from "@testing-library/react"
import { createElement, Fragment } from "react"
import {
  articleFragmentToReactNodes,
  articleHtmlToText,
  decodeArticleAttribute,
  decodeArticleText,
  sanitizeArticleFragment,
  sanitizeArticleHtml,
  sanitizeArticleUrl,
} from "../sanitizeArticleHtml"

afterEach(() => {
  vi.unstubAllGlobals()
})

class FakeTrustedHTML {
  constructor(readonly value: string) {}

  toString(): string {
    return this.value
  }
}

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

  it("decodes complete HTML5 character references as text and as attributes", () => {
    expect(decodeArticleText("Caf&eacute; &euro; &trade; &#x1F393;")).toBe("Café € ™ 🎓")
    expect(decodeArticleText("Literal <strong>text</strong>")).toBe("Literal <strong>text</strong>")
    expect(decodeArticleAttribute('A &eacute; "quoted"')).toBe('A é "quoted"')
    expect(sanitizeArticleUrl("href", "https://example.edu/?a=1&amp;b=2")).toBe(
      "https://example.edu/?a=1&b=2"
    )
    expect(sanitizeArticleUrl("href", "javascript&colon;alert(1)")).toBeNull()
  })

  it("keeps decoded less-than characters in flat text nodes", () => {
    expect(decodeArticleText("&euro; <strong>literal</strong> &lt;img src=x&gt;")).toBe(
      "€ <strong>literal</strong> <img src=x>"
    )
  })

  it("reads only visible text from raw HTML, whatever its nesting or comments", () => {
    expect(articleHtmlToText("<strong>Campus</strong> &eacute;<!-- hidden --> end")).toBe(
      "Campus é end"
    )
    expect(articleHtmlToText("<b><i>deep</i> text</b> after")).toBe("deep text after")
    expect(articleHtmlToText("<scr<script>ipt>payload()</script>tail")).toBe("ipt>payload()tail")
    expect(articleHtmlToText("<script>hidden()</script><style>a{}</style>shown")).toBe("shown")
    expect(articleHtmlToText("a < b &lt;img src=x&gt;")).toBe("a < b <img src=x>")
    expect(articleHtmlToText("<div".repeat(50_000))).toBe("")
  })

  it("restores only matching safe heading ids after DOM sanitization", () => {
    const matching = sanitizeArticleFragment("<h2>Campus update</h2>", ["campus-update"])
    const mismatched = sanitizeArticleFragment("<h2>Campus update</h2>", ["first", "second"])
    const unsafe = sanitizeArticleFragment("<h2>Campus update</h2>", ["unsafe id"])

    expect(matching?.querySelector("h2")?.getAttribute("id")).toBe("campus-update")
    expect(mismatched?.querySelector("h2")?.hasAttribute("id")).toBe(false)
    expect(unsafe?.querySelector("h2")?.hasAttribute("id")).toBe(false)
  })

  it("does not restore an id from a missing sparse heading-id slot", () => {
    const headingIds = new Array<string>(1)
    const fragment = sanitizeArticleFragment("<h2>Campus update</h2>", headingIds)
    if (!fragment) throw new Error("Expected a browser article fragment")

    expect(fragment.querySelector("h2")?.hasAttribute("id")).toBe(false)
  })

  it("converts safe fragment attributes into React props and drops invalid numeric values", () => {
    const fragment = sanitizeArticleFragment(
      '<pre class="language-ts">const x = 1</pre>' +
        '<table><tbody><tr><td colspan="2" rowspan="3">Valid span</td>' +
        '<td colspan="1000" rowspan="0">Invalid span</td></tr></tbody></table>' +
        '<img src="/campus.png" alt="Campus" width="640" height="10000">' +
        "<p>Before<!-- editorial comment -->after</p>"
    )
    if (!fragment) throw new Error("Expected a browser article fragment")

    const { container } = render(
      createElement(Fragment, null, articleFragmentToReactNodes(fragment))
    )

    expect(container.querySelector("pre")).toHaveClass("language-ts")
    expect(container.querySelector("td[colspan='2'][rowspan='3']")).toHaveTextContent("Valid span")
    expect(container.querySelectorAll("td")[1]).not.toHaveAttribute("colspan")
    expect(container.querySelectorAll("td")[1]).not.toHaveAttribute("rowspan")
    expect(container.querySelector("img")).toHaveAttribute("width", "640")
    expect(container.querySelector("img")).not.toHaveAttribute("height")
    expect(container.querySelector("p")).toHaveTextContent("Beforeafter")
  })

  it("uses an image alt value as text when the URL sanitizer removes its source", () => {
    const fragment = sanitizeArticleFragment(
      '<img src="javascript:alert(1)" alt="Campus &amp; library">'
    )
    if (!fragment) throw new Error("Expected a browser article fragment")

    expect(articleFragmentToReactNodes(fragment)).toEqual(["Campus & library"])
  })

  it("omits a sanitized image with no source or alt fallback", () => {
    const fragment = sanitizeArticleFragment('<img src="javascript:alert(1)">')
    if (!fragment) throw new Error("Expected a browser article fragment")

    expect(articleFragmentToReactNodes(fragment)).toEqual([null])
  })

  it("omits disallowed elements from direct fragment conversion", () => {
    const fragment = document.createDocumentFragment()
    const script = document.createElement("script")
    script.textContent = "unsafe script content"
    fragment.append(script)

    expect(articleFragmentToReactNodes(fragment)).toEqual([null])
  })

  it("uses the plain-text fallback when document is unavailable during SSR", () => {
    vi.stubGlobal("document", undefined)

    expect(sanitizeArticleHtml("<p>Hello, <strong>SSR</strong></p>")).toBe("Hello, SSR")
  })

  it("does not attempt to create an article fragment during SSR", () => {
    vi.stubGlobal("document", undefined)

    expect(sanitizeArticleFragment("<p>SSR</p>")).toBeNull()
  })

  it("passes only app-policy TrustedHTML to the template sink when setHTML is unavailable", () => {
    const innerHTML = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML")
    if (!innerHTML?.set) throw new Error("Missing innerHTML setter")
    const originalSet = innerHTML.set
    const rawWrites: string[] = []
    const trustedWrites: FakeTrustedHTML[] = []
    Object.defineProperty(Element.prototype, "innerHTML", {
      ...innerHTML,
      set(this: Element, value: unknown) {
        if (!(value instanceof FakeTrustedHTML)) {
          rawWrites.push(String(value))
          throw new TypeError("TrustedHTML required")
        }
        trustedWrites.push(value)
        originalSet.call(this, String(value))
      },
    })

    const policyNames: string[] = []
    const createPolicy = vi.fn(
      (name: string, rules: { createHTML?: (value: string) => string }) => {
        policyNames.push(name)
        return {
          createHTML: (value: string) => new FakeTrustedHTML(rules.createHTML?.(value) ?? value),
          createScriptURL: (value: string) => value,
        }
      }
    )
    Object.defineProperty(window, "trustedTypes", {
      configurable: true,
      value: { createPolicy },
    })

    try {
      const fragment = sanitizeArticleFragment('<p onclick="bad()">Safe <strong>text</strong></p>')

      expect(policyNames).toEqual(["app"])
      expect(createPolicy).toHaveBeenCalledWith("app", expect.any(Object))
      expect(rawWrites).toEqual([])
      expect(trustedWrites).toHaveLength(1)
      expect(fragment?.querySelector("p")?.textContent).toBe("Safe text")
      expect(fragment?.querySelector("p")?.hasAttribute("onclick")).toBe(false)
    } finally {
      Object.defineProperty(Element.prototype, "innerHTML", innerHTML)
      Reflect.deleteProperty(window, "trustedTypes")
      Reflect.deleteProperty(window, "__ttAppPolicy")
    }
  })

  it("uses the plain-text fallback when app Trusted Types policy creation fails", () => {
    const trustedTypesDescriptor = Object.getOwnPropertyDescriptor(window, "trustedTypes")
    const appPolicyDescriptor = Object.getOwnPropertyDescriptor(window, "__ttAppPolicy")
    const createPolicy = vi.fn(() => {
      throw new TypeError("Trusted Types policy creation rejected")
    })
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)
    Object.defineProperty(window, "trustedTypes", {
      configurable: true,
      value: { createPolicy },
    })
    Reflect.deleteProperty(window, "__ttAppPolicy")

    try {
      expect(sanitizeArticleHtml("<p>Hello, <strong>Policy</strong></p>")).toBe("Hello, Policy")
      expect(createPolicy).toHaveBeenCalledWith("app", expect.any(Object))
      expect(consoleError).toHaveBeenCalled()
    } finally {
      if (trustedTypesDescriptor) {
        Object.defineProperty(window, "trustedTypes", trustedTypesDescriptor)
      } else {
        Reflect.deleteProperty(window, "trustedTypes")
      }
      if (appPolicyDescriptor) {
        Object.defineProperty(window, "__ttAppPolicy", appPolicyDescriptor)
      } else {
        Reflect.deleteProperty(window, "__ttAppPolicy")
      }
      consoleError.mockRestore()
    }
  })

  it("preserves allowed HTML structure (p, h2, ul, li, a, img)", () => {
    const html =
      "<h2>Title</h2><p>Some <b>bold</b> <i>italic</i> <strike>old</strike> text.</p><ul><li>Item</li></ul>" +
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

  it("does not sanitize descendants after their dangerous parent is removed", () => {
    const result = sanitizeArticleHtml(
      '<form action="/steal"><p onclick="evil()">nested secret</p></form><p>safe</p>'
    )

    expect(result).toBe("<p>safe</p>")
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

  it("removes malformed URL attributes without throwing", () => {
    const result = sanitizeArticleHtml('<a href="http://[invalid-host">broken</a>')
    expect(result).not.toContain("href")
  })

  it("removes URL attributes that contain no usable characters", () => {
    const result = sanitizeArticleHtml('<a href=" \t">blank</a>')
    expect(result).not.toContain("href")
  })

  it("rejects a URL composed only of control characters", () => {
    expect(sanitizeArticleUrl("href", "\u0000\u007f")).toBeNull()
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

  it("removes SVG, MathML, namespace attributes, and unknown active elements", () => {
    const html =
      "<p>Approved <strong>editorial</strong> markup</p>" +
      '<svg><a xlink:href="javascript:alert(1)">svg payload</a></svg>' +
      '<math><maction xlink:href="javascript:alert(2)">math payload</maction></math>' +
      '<custom-active data-action="javascript:alert(3)">custom payload</custom-active>' +
      '<a href="https://example.com" xlink:href="javascript:alert(4)">safe link</a>' +
      "<table><thead><tr><th>Column</th></tr></thead><tbody><tr><td>Value</td></tr></tbody></table>"

    const result = sanitizeArticleHtml(html)

    expect(result).toContain("<p>Approved <strong>editorial</strong> markup</p>")
    expect(result).toContain("<table>")
    expect(result).toContain('<a href="https://example.com">safe link</a>')
    expect(result).not.toMatch(/<(svg|math|maction|custom-active)\b/i)
    expect(result).not.toMatch(/xlink:href|javascript:/i)
  })

  it("keeps only safe editorial attributes and normalizes their values", () => {
    const html =
      '<h2 id="campus-heading">Heading</h2>' +
      '<h2 id="bad heading">Invalid heading id</h2>' +
      '<pre class="language-ts extra">code</pre>' +
      '<code class="not-a-language">plain</code>' +
      '<table align="CENTER"><tr><td align="nope" colspan="2" rowspan="1">Cell</td></tr></table>' +
      '<a href="/relative" target="_blank" rel="opener external">new tab</a>' +
      '<a href="/relative" target="_blank">new tab without rel</a>' +
      '<a href="/relative" target="_self">same tab</a>' +
      '<a href="/relative" target="javascript">invalid target</a>' +
      '<img src="/image.png" loading="lazy" decoding="async">' +
      '<img src="/image.png" loading="eagerly" decoding="fast">'

    const result = sanitizeArticleHtml(html)

    expect(result).toContain('<h2 id="campus-heading">Heading</h2>')
    expect(result).not.toContain('id="bad heading"')
    expect(result).toContain('<pre class="language-ts">code</pre>')
    expect(result).not.toContain('class="not-a-language"')
    expect(result).toContain('<table align="center">')
    expect(result).not.toContain('align="nope"')
    expect(result).toContain('rel="external noopener noreferrer"')
    expect(result).toContain('rel="noopener noreferrer"')
    expect(result).not.toContain('target="javascript"')
    expect(result).toContain('loading="lazy"')
    expect(result).not.toContain('loading="eagerly"')
    expect(result).toContain('decoding="async"')
    expect(result).not.toContain('decoding="fast"')
  })
})
