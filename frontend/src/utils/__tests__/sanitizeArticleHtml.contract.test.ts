import { describe, expect, it } from "vitest"
import { sanitizeArticleHtml } from "../sanitizeArticleHtml"

/**
 * Exact allowlist contract of the article sanitizer: every approved tag and
 * attribute survives, every normalization is observable, and every unsafe
 * or obfuscated URL is dropped.
 */
const parse = (html: string) => {
  const template = document.createElement("template")
  template.innerHTML = sanitizeArticleHtml(html)
  return template.content
}
const first = (html: string, selector: string) => parse(html).querySelector(selector)

describe("sanitizeArticleHtml allowlist", () => {
  it.each([
    ["br", "<p>a<br>b</p>"],
    ["b", "<b>x</b>"],
    ["i", "<i>x</i>"],
    ["strong", "<strong>x</strong>"],
    ["em", "<em>x</em>"],
    ["del", "<del>x</del>"],
    ["s", "<s>x</s>"],
    ["strike", "<strike>x</strike>"],
    ["u", "<u>x</u>"],
    ["h1", "<h1>x</h1>"],
    ["h2", "<h2>x</h2>"],
    ["h3", "<h3>x</h3>"],
    ["h4", "<h4>x</h4>"],
    ["h5", "<h5>x</h5>"],
    ["h6", "<h6>x</h6>"],
    ["ol", "<ol><li>x</li></ol>"],
    ["blockquote", "<blockquote>x</blockquote>"],
    ["pre", "<pre><code>x</code></pre>"],
    ["tfoot", "<table><tfoot><tr><td>x</td></tr></tfoot></table>"],
    ["hr", "<hr>"],
  ])("keeps <%s>", (_tag, html) => {
    expect(sanitizeArticleHtml(html)).toBe(html)
  })

  it.each(["script", "iframe", "style", "span", "div", "svg", "form"])(
    "removes <%s> together with its content",
    (tag) => {
      expect(sanitizeArticleHtml(`<p>keep</p><${tag}>drop</${tag}>`)).toBe("<p>keep</p>")
    }
  )

  it("sanitizes an allowed element nested inside a removed one without leaking it", () => {
    expect(sanitizeArticleHtml('<div><a href="javascript:alert(1)">x</a></div><p>ok</p>')).toBe(
      "<p>ok</p>"
    )
  })

  it("returns an empty string for empty input", () => {
    expect(sanitizeArticleHtml("")).toBe("")
  })
})

describe("sanitizeArticleHtml attributes", () => {
  it.each(["h1", "h2", "h3", "h4", "h5", "h6"])("keeps a safe id on <%s> only", (tag) => {
    expect(first(`<${tag} id="intro_1">x</${tag}>`, tag)?.getAttribute("id")).toBe("intro_1")
  })

  it("drops ids outside headings and unsafe heading ids", () => {
    expect(first('<p id="intro">x</p>', "p")?.hasAttribute("id")).toBe(false)
    expect(first('<h2 id="bad id">x</h2>', "h2")?.hasAttribute("id")).toBe(false)
  })

  it("drops attributes that no tag allows", () => {
    const img = first('<img src="https://a.test/x.png" onerror="alert(1)" style="x">', "img")
    expect(img?.getAttributeNames()).toEqual(["src"])
  })

  it("keeps the approved link and image attributes", () => {
    const link = first('<a href="https://a.test" title="Docs" rel="author">x</a>', "a")
    expect(link?.getAttribute("title")).toBe("Docs")
    expect(link?.getAttribute("rel")).toBe("author")
    const img = first(
      '<img src="https://a.test/x.png" alt="A" title="T" width="10" height="20">',
      "img"
    )
    expect(img?.getAttribute("title")).toBe("T")
    expect(img?.getAttribute("width")).toBe("10")
    expect(img?.getAttribute("height")).toBe("20")
  })

  it.each(["th", "td"])("keeps table cell alignment and spans on <%s>", (cell) => {
    const node = first(
      `<table><tbody><tr><${cell} align="left" colspan="2" rowspan="3">x</${cell}></tr></tbody></table>`,
      cell
    )
    expect(node?.getAttribute("align")).toBe("left")
    expect(node?.getAttribute("colspan")).toBe("2")
    expect(node?.getAttribute("rowspan")).toBe("3")
  })

  it.each(["left", "center", "right", "justify"])("normalizes align=%s", (value) => {
    const table = first(`<table align=" ${value.toUpperCase()} "></table>`, "table")
    expect(table?.getAttribute("align")).toBe(value)
  })

  it("drops an unknown alignment", () => {
    expect(first('<table align="middle"></table>', "table")?.hasAttribute("align")).toBe(false)
  })

  it.each(["pre", "code"])("keeps only language classes on <%s>", (tag) => {
    const html =
      tag === "pre"
        ? '<pre class="language-js evil  language-ts"></pre>'
        : '<code class="language-js evil  language-ts"></code>'
    expect(first(html, tag)?.getAttribute("class")).toBe("language-js language-ts")
  })

  it.each(["evil", "xlanguage-js", "language-js.evil"])(
    "removes the class attribute when no token is an exact language class (%s)",
    (token) => {
      expect(first(`<code class="${token}"></code>`, "code")?.hasAttribute("class")).toBe(false)
    }
  )

  it.each(["_self", "_blank", "_parent", "_top"])("normalizes target=%s", (value) => {
    const link = first(`<a href="https://a.test" target=" ${value.toUpperCase()} ">x</a>`, "a")
    expect(link?.getAttribute("target")).toBe(value)
  })

  it("drops an unknown target", () => {
    expect(
      first('<a href="https://a.test" target="frame">x</a>', "a")?.hasAttribute("target")
    ).toBe(false)
  })

  it("forces noopener and noreferrer on new-tab links and removes opener", () => {
    const link = first('<a href="https://a.test" target="_BLANK" rel="opener  author">x</a>', "a")
    expect(link?.getAttribute("rel")).toBe("author noopener noreferrer")
  })

  it("leaves rel untouched on same-tab links", () => {
    expect(
      first('<a href="https://a.test" target="_self" rel="opener">x</a>', "a")?.getAttribute("rel")
    ).toBe("opener")
  })

  it.each([
    ["loading", "eager"],
    ["loading", "lazy"],
    ["decoding", "sync"],
    ["decoding", "async"],
    ["decoding", "auto"],
  ])("keeps %s=%s regardless of case and padding", (name, value) => {
    const img = first(`<img src="https://a.test/x.png" ${name}=" ${value.toUpperCase()} ">`, "img")
    expect(img?.hasAttribute(name)).toBe(true)
  })

  it.each([
    ["loading", "soon"],
    ["decoding", "later"],
  ])("drops %s=%s", (name, value) => {
    const img = first(`<img src="https://a.test/x.png" ${name}="${value}">`, "img")
    expect(img?.hasAttribute(name)).toBe(false)
  })
})

describe("sanitizeArticleHtml URLs", () => {
  it.each(["http://a.test/x", "https://a.test/x", "/relative/path", "#section"])(
    "keeps the safe link %s",
    (href) => {
      expect(first(`<a href="${href}">x</a>`, "a")?.getAttribute("href")).toBe(href)
    }
  )

  it.each([
    ["javascript", "javascript:alert(1)"],
    ["an upper-case scheme", "JaVaScRiPt:alert(1)"],
    ["an embedded tab", "java&#9;script:alert(1)"],
    ["an embedded space", "java script:alert(1)"],
    ["an SOH control", "java&#1;script:alert(1)"],
    ["a unit separator", "java&#31;script:alert(1)"],
    ["DEL", "java&#127;script:alert(1)"],
    ["a no-break space", "java&#160;script:alert(1)"],
    ["a vbscript scheme", "vbscript:msgbox(1)"],
    ["a data URL", "data:image/png;base64,AAAA"],
    ["a blank value", "   "],
    ["an unparseable authority", "https://["],
  ])("drops a link with %s", (_label, href) => {
    expect(first(`<a href="${href}">x</a>`, "a")?.hasAttribute("href")).toBe(false)
  })

  it.each([
    ["a png", "data:image/png;base64,iVBORw0KGgo="],
    ["a padded webp", " data:image/webp;base64,UklGR g== "],
  ])("keeps an inline image data URL with %s", (_label, src) => {
    expect(first(`<img src="${src}" alt="">`, "img")?.hasAttribute("src")).toBe(true)
  })

  it.each([
    ["a non-image type", "data:text/html;base64,PHNjcmlwdD4="],
    ["an svg image", "data:image/svg+xml;base64,PHN2Zz4="],
    ["a leading control character", "&#1;data:image/png;base64,AAAA"],
    ["trailing markup", "data:image/png;base64,AAAA!"],
    ["no base64 marker", "data:image/png,AAAA"],
  ])("drops an image data URL with %s", (_label, src) => {
    expect(first(`<img src="${src}" alt="">`, "img")?.hasAttribute("src")).toBe(false)
  })
})
