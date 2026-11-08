import { act, fireEvent, render, screen } from "@testing-library/react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest"

const { mediaMock, ensureWasmSanitizerInitialized, sanitizeArticleFragment } = vi.hoisted(() => ({
  mediaMock: vi.fn(),
  ensureWasmSanitizerInitialized: vi.fn<() => Promise<boolean>>(),
  sanitizeArticleFragment: vi.fn(),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: (query: string) => mediaMock(query) }))
vi.mock("@/utils/wasmSanitizer", () => ({ ensureWasmSanitizerInitialized }))
vi.mock("@/utils/sanitizeArticleHtml", async () => {
  const actual = await vi.importActual<typeof import("@/utils/sanitizeArticleHtml")>(
    "@/utils/sanitizeArticleHtml"
  )
  sanitizeArticleFragment.mockImplementation(actual.sanitizeArticleFragment)
  return { ...actual, sanitizeArticleFragment }
})

let NewsDetailBody: (typeof import("@/components/news/NewsDetailBody"))["NewsDetailBody"]

const MARKDOWN_WITH_TOC = `## Background

The university opened a new interdisciplinary lab this spring.

## Methodology

We surveyed enrolment data across three faculties.

## Key Findings

Enrolment rose by a double-digit margin year over year.`

const PLAIN_TEXT = `The new facility is the largest investment in a decade.

It will host robotics, AI, and data-science tracks under one roof.`

/** Stand-in for a TrustedHTML value: a non-string object the enforced sink accepts. */
class FakeTrustedHTML {
  readonly value: string

  constructor(value: string) {
    this.value = value
  }

  toString(): string {
    return this.value
  }
}

type TrustedTypesHarness = {
  /** Raw strings that reached the enforced innerHTML sink. Must stay empty. */
  rawWrites: string[]
  /** Values accepted by the enforced sink after the fake policy branded them. */
  trustedWrites: FakeTrustedHTML[]
  /** Names requested from the Trusted Types factory. */
  policyNames: string[]
  /** Stand-in native parser; present only when requested. */
  setHTML: Mock
  /** Set to true to make the approved policy reject markup from now on. */
  state: { failPolicy: boolean }
  restore: () => void
}

/**
 * Enforces Trusted Types on innerHTML: raw strings throw and are recorded. The
 * optional native parser stands in for Element/Template setHTML; it writes through
 * the original setter, as a browser parser does not touch the TT sink.
 */
function enforceTrustedTypes({
  nativeSetHTML = false,
  policy = true,
}: { nativeSetHTML?: boolean; policy?: boolean } = {}): TrustedTypesHarness {
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

  const originalSetHTML = Object.getOwnPropertyDescriptor(HTMLTemplateElement.prototype, "setHTML")
  const setHTML = vi.fn(function (this: HTMLTemplateElement, html: string) {
    originalSet.call(this, html)
  })
  if (nativeSetHTML) {
    Object.defineProperty(HTMLTemplateElement.prototype, "setHTML", {
      configurable: true,
      value: setHTML,
    })
  }

  const state = { failPolicy: false }
  const policyNames: string[] = []
  const createPolicy = vi.fn((name: string, rules: { createHTML?: (input: string) => string }) => {
    policyNames.push(name)
    if (!policy) throw new TypeError("policy creation blocked")
    return {
      createHTML: (input: string) => {
        if (state.failPolicy) throw new TypeError("policy rejected HTML")
        return new FakeTrustedHTML(rules.createHTML?.(input) ?? input)
      },
      createScriptURL: (input: string) => input,
    }
  })
  Object.defineProperty(window, "trustedTypes", {
    configurable: true,
    value: { createPolicy },
  })

  return {
    rawWrites,
    trustedWrites,
    policyNames,
    setHTML,
    state,
    restore: () => {
      Object.defineProperty(Element.prototype, "innerHTML", innerHTML)
      if (originalSetHTML) {
        Object.defineProperty(HTMLTemplateElement.prototype, "setHTML", originalSetHTML)
      } else {
        Reflect.deleteProperty(HTMLTemplateElement.prototype, "setHTML")
      }
      Reflect.deleteProperty(window, "trustedTypes")
      Reflect.deleteProperty(window, "__ttAppPolicy")
    },
  }
}

/** Markup as the Node server emits it: no document or window is available. */
function renderServerMarkup(content: string, options: { hasParser?: boolean } = {}): string {
  vi.stubGlobal("document", undefined)
  vi.stubGlobal("window", undefined)
  if (options.hasParser === false) vi.stubGlobal("DOMParser", undefined)
  try {
    return renderToString(<NewsDetailBody content={content} />)
  } finally {
    vi.unstubAllGlobals()
  }
}

describe("NewsDetailBody", () => {
  beforeEach(async () => {
    const newsDetailBodyModule = await import("@/components/news/NewsDetailBody")
    NewsDetailBody = newsDetailBodyModule.NewsDetailBody
    mediaMock.mockReset()
    mediaMock.mockImplementation((query: string) => query === "(min-width: 1024px)")
    ensureWasmSanitizerInitialized.mockReset().mockResolvedValue(false)
    sanitizeArticleFragment.mockClear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    Reflect.deleteProperty(window, "__ttAppPolicy")
  })

  it("renders markdown headings and the table of contents on desktop", () => {
    const { container } = render(<NewsDetailBody content={MARKDOWN_WITH_TOC} />)
    expect(screen.getByRole("heading", { name: "Background" })).toHaveAttribute("id", "background")
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
    expect(container.querySelector("section")).toHaveClass(
      "glass-layer-surface",
      "glass-noise",
      "flex",
      "gap-8"
    )
  })

  it("does not reserve table-of-contents layout for fewer than three headings", () => {
    const { container } = render(
      <NewsDetailBody content={"## First heading\n\n## Second heading"} />
    )

    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
    expect(container.querySelector("section")).not.toHaveClass("flex")
    expect(container.querySelector("section")).not.toHaveClass("gap-8")
  })

  it("omits empty linked headings from the table of contents", () => {
    const { container } = render(<NewsDetailBody content="## [](/news/empty)" />)

    expect(container.querySelector(".news-article-body h2")).toHaveAttribute("id", "")
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
  })

  it("recognizes only line-start heading, list, fence, and rule markers", () => {
    const { container } = render(
      <NewsDetailBody
        content={`Inline # marker
Inline - marker
Inline 1. marker
Inline \`\`\` marker
Inline ---
--- trailing

> Preserved quote`}
      />
    )

    expect(container.querySelector("blockquote.news-pullquote")).toHaveTextContent(
      "Preserved quote"
    )
  })

  it("recognizes a heading only when its marker is followed by whitespace", () => {
    render(<NewsDetailBody content="# Campus life" />)

    expect(screen.getByRole("heading", { name: "Campus life" })).toBeInTheDocument()
  })

  it("recognizes multi-character emphasis", () => {
    const { container } = render(<NewsDetailBody content="*Campus life*" />)

    expect(container.querySelector("em")).toHaveTextContent("Campus life")
  })

  it("renders multi-character bold Markdown", () => {
    const { container } = render(<NewsDetailBody content="**Campus life**" />)

    expect(container.querySelector("strong")).toHaveTextContent("Campus life")
  })

  it("does not mistake an asterisk-only run for bold text", () => {
    const { container } = render(<NewsDetailBody content={"*****\n\n> Preserved quote"} />)

    expect(container.querySelector("blockquote.news-pullquote")).toHaveTextContent(
      "Preserved quote"
    )
  })

  it("recognizes a line-start unordered list marker followed by whitespace", () => {
    render(<NewsDetailBody content={"- First item\n- Second item"} />)

    expect(screen.getAllByRole("listitem")).toHaveLength(2)
  })

  it("recognizes multi-digit ordered list markers followed by whitespace", () => {
    render(<NewsDetailBody content="12. Twelfth item" />)

    expect(screen.getByRole("listitem")).toHaveTextContent("Twelfth item")
  })

  it("recognizes links with multi-character labels and destinations", () => {
    render(<NewsDetailBody content="[Docs portal](https://example.edu/docs)" />)

    expect(screen.getByRole("link", { name: "Docs portal" })).toHaveAttribute(
      "href",
      "https://example.edu/docs"
    )
  })

  it("renders GFM tables with multi-character cells", () => {
    const { container } = render(
      <NewsDetailBody
        content={`| Alpha column | Beta column |
| --- | --- |
| Alpha value | Beta value |`}
      />
    )

    expect(container.querySelector("table")).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Alpha column" })).toBeInTheDocument()
  })

  it("uses hard breaks inside setext heading text when building stable heading ids", () => {
    const { container } = render(<NewsDetailBody content={"Campus  \nupdate\n---"} />)
    const heading = container.querySelector(".news-article-body h2")

    expect(heading).toHaveAttribute("id", "campus-update")
    expect(heading?.querySelector("br")).toBeInTheDocument()
  })

  it("decodes complete character references in text while preserving code-token references", () => {
    const { container } = render(
      <NewsDetailBody
        content={
          "## Caf&eacute; &euro; &trade;\n\n" +
          "Entity text: &eacute; &euro; &trade;\n\n" +
          "Inline `&lt;tag&gt;`\n\n" +
          "```html\n&lt;tag&gt;\n```"
        }
      />
    )

    expect(screen.getByRole("heading", { name: "Café € ™" })).toHaveAttribute("id", "café-")
    expect(screen.getByText("Entity text: é € ™")).toBeInTheDocument()
    expect(container.querySelector(".news-article-body p code")).toHaveTextContent("&lt;tag&gt;")
    expect(container.querySelector(".news-article-body pre code")).toHaveTextContent("&lt;tag&gt;")
  })

  it("renders disabled task checkboxes and keeps Markdown URL schemes safe", () => {
    const { container } = render(
      <NewsDetailBody
        content={
          "# Campus\n\n" +
          "- [x] Finished task\n- [ ] Pending task\n\n" +
          "[Anchor](#campus) [Relative](/news/42) [Unsafe](javascript:alert(1))\n\n" +
          "![Unsafe](javascript:alert(2)) ![Campus](/images/campus.png)"
        }
      />
    )

    const checkboxes = screen.getAllByRole("checkbox")
    expect(checkboxes).toHaveLength(2)
    expect(checkboxes[0]).toBeChecked()
    expect(checkboxes[0]).toBeDisabled()
    expect(checkboxes[1]).not.toBeChecked()
    expect(checkboxes[1]).toBeDisabled()
    expect(
      Array.from(container.querySelectorAll("a")).map((link) => link.getAttribute("href"))
    ).toEqual(["#campus", "/news/42"])
    expect(
      Array.from(container.querySelectorAll("img")).map((image) => image.getAttribute("src"))
    ).toEqual(["/images/campus.png"])
    expect(container.innerHTML).not.toMatch(/javascript:/i)
  })

  it("renders rich inline tokens and tight, loose, ordered, and aligned Markdown blocks", () => {
    const content = [
      '## \\*Accessible\\* **heading** `code` ![Campus &amp; City](https://example.edu/campus.png "Campus photo") [Guide](https://example.edu/guide "Read guide")',
      "",
      "Escaped \\*literal\\*, *italic*, ~~outdated~~, and `inline code`.",
      "Hard break  ",
      "continues here.",
      "",
      "> A **quoted** update.",
      "",
      "```ts",
      "const campus = 1",
      "```",
      "",
      "```",
      "plain fenced code",
      "```",
      "",
      "7. First ordered item",
      "8. Second ordered item",
      "",
      "- Tight item one",
      "- Tight item two",
      "",
      "- Loose item one",
      "",
      "- Loose item two",
      "",
      "| Name | Value |",
      "| :--- | ---: |",
      "| Campus | 1 |",
    ].join("\n")

    const { container } = render(<NewsDetailBody content={content} />)
    const body = container.querySelector(".news-article-body")
    const heading = body?.querySelector("h2")

    expect(heading).toHaveAttribute("id", "accessible-heading-code-campus-city-guide")
    expect(heading?.querySelector("img")).toHaveAttribute("title", "Campus photo")
    expect(heading?.querySelector("a")).toHaveAttribute("title", "Read guide")
    expect(body?.querySelector("em")).toHaveTextContent("italic")
    expect(body?.querySelector("del")).toHaveTextContent("outdated")
    expect(body?.querySelector("p br")).toBeInTheDocument()
    expect(body?.querySelector("blockquote strong")).toHaveTextContent("quoted")
    expect(body?.querySelector("pre code.language-ts")).toHaveTextContent("const campus = 1")
    expect(body?.querySelectorAll("pre code")[1]).not.toHaveAttribute("class")
    expect(body?.querySelector("ol")).toHaveAttribute("start", "7")
    expect(body?.querySelectorAll("ul li")).toHaveLength(4)
    expect(body?.querySelector("th")).toHaveAttribute("align", "left")
    expect(body?.querySelectorAll("th")[1]).toHaveAttribute("align", "right")
    expect(body?.querySelector("td")).toHaveAttribute("align", "left")
    expect(body?.querySelectorAll("td")[1]).toHaveAttribute("align", "right")
    expect(body?.textContent).toContain("Escaped *literal*, italic, outdated, and inline code.")
  })

  it("recognizes horizontal rules longer than three hyphens", () => {
    render(<NewsDetailBody content="----" />)

    expect(screen.getByRole("separator")).toBeInTheDocument()
  })

  it("keeps soft Markdown line breaks inside one paragraph", () => {
    const { container } = render(
      <NewsDetailBody content={"# Introduction\n\nFirst line\nSecond line"} />
    )

    expect(container.querySelector(".news-article-body br")).not.toBeInTheDocument()
    expect(screen.getByText("First line Second line")).toBeInTheDocument()
  })

  it("renders plain-text content as paragraphs", () => {
    const { container } = render(<NewsDetailBody content={PLAIN_TEXT} />)
    expect(
      screen.getByText("The new facility is the largest investment in a decade.")
    ).toBeInTheDocument()
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
    expect(container.querySelector(".news-article-body")?.textContent).toBe(
      "The new facility is the largest investment in a decade." +
        "It will host robotics, AI, and data-science tracks under one roof."
    )
  })

  it("keeps single newlines within trimmed legacy paragraphs and skips blank chunks", () => {
    const { container } = render(
      <NewsDetailBody content={"  First line\nSecond line  \n\n   \n\nThird paragraph  \n\n "} />
    )
    const paragraphs = container.querySelectorAll(".news-article-body p")

    expect(paragraphs).toHaveLength(2)
    expect(paragraphs[0]?.textContent).toBe("First line\nSecond line")
    expect(paragraphs[1]?.textContent).toBe("Third paragraph")
  })

  it("escapes every HTML-significant character in legacy text", () => {
    const { container } = render(
      <NewsDetailBody content={'Fish & <chips> are "today\'s" special'} />
    )
    const paragraph = container.querySelector(".news-article-body p")

    expect(paragraph?.textContent).toBe('Fish & <chips> are "today\'s" special')
    expect(container.querySelector("chips")).not.toBeInTheDocument()
  })

  it("renders legacy paragraphs and quotes without assigning HTML under Trusted Types", () => {
    const enforcement = enforceTrustedTypes({ policy: false })
    try {
      const { container } = render(
        <NewsDetailBody
          content={"Campus <img src=x onerror=alert(1)>\n\n> A <script>bad()</script> quote"}
        />
      )
      const body = container.querySelector(".news-article-body")
      expect(body?.querySelector("p")).toHaveTextContent("Campus <img src=x onerror=alert(1)>")
      expect(body?.querySelector("blockquote")).toHaveTextContent("A <script>bad()</script> quote")
      expect(body?.querySelector("img, script")).toBeNull()
      expect(enforcement.rawWrites).toEqual([])
    } finally {
      enforcement.restore()
    }
  })

  it("preserves HTML parser normalization for legacy text nodes", () => {
    const { container } = render(<NewsDetailBody content={"A\r\nB\0C\rD\n\n> Q\0R\rS"} />)
    expect(container.querySelector("p")?.textContent).toBe("A\nBC\nD")
    expect(container.querySelector("blockquote")?.textContent).toBe("QR\nS")
  })

  it("hydrates legacy text without changing its server-rendered markup", async () => {
    const content = "Campus research\r\nupdate\n\n> Safe & sound"
    const markup = renderToString(<NewsDetailBody content={content} />)
    const container = document.createElement("div")
    container.innerHTML = markup
    document.body.append(container)
    const recoverableError = vi.fn()
    try {
      let root: Root | undefined
      await act(async () => {
        root = hydrateRoot(container, <NewsDetailBody content={content} />, {
          onRecoverableError: recoverableError,
        })
      })
      expect(recoverableError).not.toHaveBeenCalled()
      expect(container.querySelector("p")).toHaveTextContent("Campus research update")
      expect(container.querySelector("blockquote")).toHaveTextContent("Safe & sound")
      await act(async () => root?.unmount())
    } finally {
      container.remove()
    }
  })

  it("does not render active SVG/MathML or unknown elements from article markup", () => {
    const { container } = render(
      <NewsDetailBody
        content={
          "# Campus update\n\n" +
          "Approved **editorial** markup.\n\n" +
          '<svg><a xlink:href="javascript:alert(1)">svg payload</a></svg>\n\n' +
          '<math><maction xlink:href="javascript:alert(2)">math payload</maction></math>\n\n' +
          '<custom-active data-action="javascript:alert(3)">custom payload</custom-active>'
        }
      />
    )

    const body = container.querySelector(".news-article-body")
    expect(body).toBeInTheDocument()
    expect(body?.querySelector("svg, math, maction, custom-active")).not.toBeInTheDocument()
    expect(body?.innerHTML).not.toMatch(/xlink:href|javascript:/i)
    expect(body?.querySelector("strong")).toHaveTextContent("editorial")
  })

  it.each([
    ["with a DOM parser", true],
    ["without a DOM parser", false],
  ])("renders encoded article payloads as text during server rendering %s", (_label, hasParser) => {
    const PageParser = DOMParser
    const markup = renderServerMarkup("# Notice\n\n&lt;img src=x onerror=alert(1)&gt;", {
      hasParser,
    })

    const page = new PageParser().parseFromString(markup, "text/html")
    const body = page.querySelector(".news-article-body")
    expect(body).not.toBeNull()
    expect(body?.querySelector("img, script")).toBeNull()
    expect(body?.textContent).toContain("img src=x onerror=alert(1)")
    if (hasParser) expect(body?.textContent).toContain("<img src=x onerror=alert(1)>")
  })

  it("server-renders sanitized paragraphs and headings rather than stripped text", () => {
    const markup = renderServerMarkup("# Notice\n\nBody **bold** text")

    expect(markup).toContain('<h1 id="notice">Notice</h1>')
    expect(markup).toContain("<p>Body <strong>bold</strong> text</p>")
  })

  it("keeps entity-containing heading ids and ToC links stable from SSR through hydration", async () => {
    const content = "## AT&amp;T\n\n## B&amp;B\n\n## R&amp;D"
    const serverMarkup = renderServerMarkup(content, { hasParser: false })
    expect(serverMarkup).toContain('<h2 id="att">AT&amp;T</h2>')
    expect(serverMarkup).toContain("AT&amp;T")

    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.append(container)
    const recoverableError = vi.fn()
    try {
      let root: Root | undefined
      await act(async () => {
        root = hydrateRoot(container, <NewsDetailBody content={content} />, {
          onRecoverableError: recoverableError,
        })
      })

      expect(recoverableError).not.toHaveBeenCalled()
      expect(container.querySelector(".news-article-body h2")).toHaveAttribute("id", "att")
      expect(container.querySelector(".news-article-body h2")).toHaveTextContent("AT&T")
      const heading = container.querySelector(".news-article-body h2") as HTMLHeadingElement
      const scrollIntoView = vi.fn()
      heading.scrollIntoView = scrollIntoView
      fireEvent.click(screen.getByRole("button", { name: "AT&T" }))
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
      await act(async () => root?.unmount())
    } finally {
      container.remove()
    }
  })

  it("hydrates markdown server markup and upgrades it after mount without a recoverable error", async () => {
    const content = "# Heading\n\nA & B\n\n<strong>Raw update</strong>"
    const container = document.createElement("div")
    const serverMarkup = renderServerMarkup(content)
    container.innerHTML = serverMarkup
    expect(container.querySelector(".news-article-body strong")).toBeNull()
    expect(container.querySelector(".news-article-body")?.textContent).toContain("Raw update")
    expect(container.querySelector(".news-article-body")?.textContent).not.toContain("<strong>")
    document.body.append(container)
    const recoverableError = vi.fn()
    try {
      let root: Root | undefined
      await act(async () => {
        root = hydrateRoot(container, <NewsDetailBody content={content} />, {
          onRecoverableError: recoverableError,
        })
      })
      expect(recoverableError).not.toHaveBeenCalled()
      expect(container.querySelector("p")).toHaveTextContent("A & B")
      expect(container.querySelector("h1")).toHaveAttribute("id", "heading")
      expect(container.querySelector(".news-article-body strong")).toHaveTextContent("Raw update")
      await act(async () => root?.unmount())
    } finally {
      container.remove()
    }
  })

  it("hydrates markdown server markup under enforced Trusted Types without raw HTML writes", async () => {
    const content =
      "# Heading\n\n**Bold** text\n\n" +
      "| A | B |\n| --- | --- |\n| One | Two |\n\n" +
      "![Campus](https://example.edu/campus.png)\n\n---"
    const container = document.createElement("div")
    container.innerHTML = renderServerMarkup(content)
    document.body.append(container)
    const recoverableError = vi.fn()
    const enforcement = enforceTrustedTypes({ policy: true })
    try {
      let root: Root | undefined
      await act(async () => {
        root = hydrateRoot(container, <NewsDetailBody content={content} />, {
          onRecoverableError: recoverableError,
        })
      })
      expect(recoverableError).not.toHaveBeenCalled()
      expect(enforcement.rawWrites).toEqual([])
      expect(enforcement.trustedWrites).toEqual([])
      expect(enforcement.policyNames).toEqual([])
      expect(container.querySelector("h1")).toHaveAttribute("id", "heading")
      expect(container.querySelector("strong")).toHaveTextContent("Bold")
      expect(container.querySelector("table td")).toHaveTextContent("One")
      expect(container.querySelector("img")).toHaveAttribute(
        "src",
        "https://example.edu/campus.png"
      )
      expect(container.querySelector("hr")).toBeInTheDocument()
      await act(async () => root?.unmount())
    } finally {
      enforcement.restore()
      container.remove()
    }
  })

  it("renders sanitized article markup through the native parser when Trusted Types requires it", () => {
    const enforcement = enforceTrustedTypes({ nativeSetHTML: true })
    try {
      const { container } = render(
        <NewsDetailBody
          content={
            "# Campus\n\n| A | B |\n| --- | --- |\n| One | Two |\n\n" +
            "---\n\n" +
            '<img src="https://example.edu/image.png" onerror="alert(1)">' +
            "<script>alert(2)</script>"
          }
        />
      )
      const body = container.querySelector(".news-article-body")
      expect(enforcement.setHTML).toHaveBeenCalledWith(
        expect.stringContaining("<img"),
        expect.anything()
      )
      expect(body?.querySelector("h1")).toHaveAttribute("id", "campus")
      expect(body?.querySelector("table td")).toHaveTextContent("One")
      expect(body?.querySelector("hr")).toBeInTheDocument()
      expect(body?.querySelector("img")?.hasAttribute("onerror")).toBe(false)
      expect(body?.querySelector("script")).toBeNull()
      expect(enforcement.rawWrites).toEqual([])
    } finally {
      enforcement.restore()
    }
  })

  it("keeps full GFM markup and safe raw rich text through the app policy when setHTML is unavailable", () => {
    const enforcement = enforceTrustedTypes({ nativeSetHTML: false })
    try {
      const { container } = render(
        <NewsDetailBody
          content={
            "# Campus\n\n## Background\n\n**Readable** update\n\n- first item\n- [Docs](https://example.edu/docs)\n\n" +
            "| A | B |\n| --- | --- |\n| One | Two |\n\n" +
            "![Campus](https://example.edu/campus.png)\n\n---\n\n" +
            "<strong>Approved raw formatting</strong>"
          }
        />
      )
      const body = container.querySelector(".news-article-body")
      expect(body?.querySelector("h1")).toHaveAttribute("id", "campus")
      expect(body?.querySelector("h2")).toHaveAttribute("id", "background")
      expect(enforcement.policyNames).toEqual(["app"])
      expect(enforcement.trustedWrites.length).toBeGreaterThan(0)
      expect(body?.querySelector("strong")).toHaveTextContent("Readable")
      expect(body?.querySelectorAll("li")).toHaveLength(2)
      expect(body?.querySelector("a")).toHaveAttribute("href", "https://example.edu/docs")
      expect(body?.querySelector("table td")).toHaveTextContent("One")
      expect(body?.querySelector("img")).toHaveAttribute("src", "https://example.edu/campus.png")
      expect(body?.querySelector("hr")).toBeInTheDocument()
      expect(
        Array.from(body?.querySelectorAll("strong") ?? []).map((element) => element.textContent)
      ).toContain("Approved raw formatting")
      expect(enforcement.rawWrites).toEqual([])
    } finally {
      enforcement.restore()
    }
  })

  it("sanitizes block-level raw HTML through the approved policy", () => {
    const enforcement = enforceTrustedTypes({ nativeSetHTML: false })
    try {
      const { container } = render(
        <NewsDetailBody
          content={
            "# Campus\n\n" +
            "<em>\nApproved block formatting\n</em>\n\n" +
            "<script>\nwindow.__articlePayload = true\n</script>"
          }
        />
      )
      const body = container.querySelector(".news-article-body")

      expect(body?.querySelector("em")).toHaveTextContent("Approved block formatting")
      expect(body?.querySelector("script")).toBeNull()
      expect(body?.innerHTML).not.toContain("__articlePayload")
      expect(enforcement.policyNames).toEqual(["app"])
      expect(enforcement.rawWrites).toEqual([])
      expect(enforcement.trustedWrites.length).toBeGreaterThan(0)
    } finally {
      enforcement.restore()
    }
  })

  it("retries safe raw article markup after browser WASM initialization", async () => {
    let finishInitialization: ((ready: boolean) => void) | undefined
    const initialization = new Promise<boolean>((resolve) => {
      finishInitialization = resolve
    })
    ensureWasmSanitizerInitialized.mockReturnValue(initialization)
    sanitizeArticleFragment.mockImplementationOnce(() => null)
    const enforcement = enforceTrustedTypes({ nativeSetHTML: false })
    const content = "# Campus\n\n<strong>Approved raw formatting</strong>"
    try {
      const { container } = render(<NewsDetailBody content={content} />)
      const body = container.querySelector(".news-article-body")
      expect(body?.querySelector("strong")).toBeNull()
      expect(body?.textContent).toContain("Approved raw formatting")
      expect(body?.textContent).not.toContain("<strong>")
      expect(enforcement.rawWrites).toEqual([])
      expect(sanitizeArticleFragment).toHaveBeenCalledTimes(1)

      await act(async () => {
        finishInitialization?.(true)
        await initialization
      })

      expect(body?.querySelector("strong")).toHaveTextContent("Approved raw formatting")
      expect(sanitizeArticleFragment).toHaveBeenCalledTimes(2)
      expect(enforcement.rawWrites).toEqual([])
    } finally {
      enforcement.restore()
    }
  })

  it("keeps raw article markup as text if sanitization throws or the effect is cancelled", async () => {
    let finishInitialization: ((ready: boolean) => void) | undefined
    const initialization = new Promise<boolean>((resolve) => {
      finishInitialization = resolve
    })
    ensureWasmSanitizerInitialized.mockReturnValue(initialization)
    sanitizeArticleFragment.mockImplementationOnce(() => {
      throw new Error("parser unavailable")
    })
    const { container, unmount } = render(
      <NewsDetailBody content="# Campus\n\n<strong>Visible source</strong>" />
    )
    const body = container.querySelector(".news-article-body")
    expect(body?.querySelector("strong")).toBeNull()
    expect(body?.textContent).toContain("Visible source")
    expect(body?.textContent).not.toContain("<strong>")
    expect(sanitizeArticleFragment).toHaveBeenCalledTimes(1)

    unmount()
    await act(async () => {
      finishInitialization?.(true)
      await initialization
    })

    expect(sanitizeArticleFragment).toHaveBeenCalledTimes(1)
  })

  it("sanitizes grouped raw HTML with entities, quoted delimiters, and nested active elements", () => {
    const enforcement = enforceTrustedTypes({ nativeSetHTML: false })
    try {
      const { container } = render(
        <NewsDetailBody
          content={
            "# Security update\n\n" +
            '<a href="javascript&#58;alert(1)" onclick="alert(2)">Unsafe link</a> ' +
            '<strong title="quoted > delimiter">Allowed formatting</strong> ' +
            "<svg><script>alert(3)</script></svg> " +
            '<math><maction xlink:href="javascript:alert(4)">Math payload</maction></math> ' +
            "<script><style>active()</style>tail()</script> " +
            "<strong>Malformed closing</em>"
          }
        />
      )

      const body = container.querySelector(".news-article-body")
      const allowedFormatting = Array.from(body?.querySelectorAll("strong") ?? []).find((node) =>
        node.textContent?.includes("Allowed formatting")
      )
      expect(allowedFormatting).toHaveTextContent("Allowed formatting")
      expect(allowedFormatting).not.toHaveAttribute("title")
      expect(body?.querySelector("a")?.hasAttribute("href")).toBe(false)
      expect(body?.querySelector("svg, math, maction, script, style")).toBeNull()
      expect(body?.innerHTML).not.toMatch(/javascript:|onclick=|xlink:href/i)
      expect(enforcement.rawWrites).toEqual([])
      expect(enforcement.trustedWrites.length).toBeGreaterThan(0)
      expect(enforcement.policyNames).toEqual(["app"])
    } finally {
      enforcement.restore()
    }
  })

  it("groups raw HTML through comments and unmatched closing tags", () => {
    const { container } = render(
      <NewsDetailBody
        content={
          "# Raw formatting\n\n" +
          "<strong>before<!-- editorial note -->after</strong> " +
          "<em>left</u>right</em> " +
          "<strong>self<br/></strong>"
        }
      />
    )
    const body = container.querySelector(".news-article-body")

    expect(body?.querySelector("strong")).toHaveTextContent("beforeafter")
    expect(body?.querySelector("em")).toHaveTextContent("leftright")
    expect(body?.querySelector("strong br")).toBeInTheDocument()
    expect(body?.innerHTML).not.toContain("editorial note")
    expect(body?.innerHTML).not.toContain("</u>")
  })

  it("renders Markdown inside a closed inline raw tag as Markdown in the allowlisted element", () => {
    const { container } = render(<NewsDetailBody content={'<a href="https://e.edu">**x**</a>'} />)

    const link = container.querySelector(".news-article-body a")
    expect(link).toHaveAttribute("href", "https://e.edu")
    expect(link?.querySelector("strong")).toHaveTextContent("x")
    expect(container.querySelector(".news-article-body p")?.textContent).toBe("x")
    expect(container.querySelector(".news-article-body")?.textContent).not.toContain("**")
  })

  it("keeps an unsafe href off a closed link while its Markdown still renders", () => {
    const { container } = render(
      <NewsDetailBody content={'<a href="javascript:alert(1)">**x**</a>'} />
    )

    const link = container.querySelector(".news-article-body a")
    expect(link?.hasAttribute("href")).toBe(false)
    expect(link?.querySelector("strong")).toHaveTextContent("x")
    expect(container.innerHTML).not.toMatch(/javascript:/i)
  })

  it("lets Markdown after an unclosed inline raw tag render normally", () => {
    const { container } = render(
      <NewsDetailBody content={'<span class="x">Read **this** [docs](https://e.edu)'} />
    )

    const body = container.querySelector(".news-article-body")
    expect(body?.querySelector("span")).toBeNull()
    expect(body?.querySelector("strong")).toHaveTextContent("this")
    expect(screen.getByRole("link", { name: "docs" })).toHaveAttribute("href", "https://e.edu")
    expect(body?.querySelector("p")?.textContent).toBe("Read this docs")
  })

  it("server-renders the stripped text of a closed inline raw tag with its Markdown children", () => {
    const markup = renderServerMarkup('<a href="https://e.edu">**x**</a>')

    expect(markup).toContain("<p><strong>x</strong></p>")
    expect(markup).not.toContain("**x**")
    expect(markup).not.toContain("&lt;a")
  })

  it("renders readable text only when no approved Trusted Types policy can be created", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined)
    const enforcement = enforceTrustedTypes({ policy: false })
    try {
      const { container } = render(
        <NewsDetailBody content="# Campus\n\n**Readable update**\n\n<strong>Raw markup</strong>" />
      )
      const body = container.querySelector(".news-article-body")
      expect(body).toHaveTextContent("Readable update")
      expect(body?.textContent).toContain("Raw markup")
      expect(body?.textContent).not.toContain("<strong>")
      expect(body?.querySelector("strong")).toHaveTextContent("Readable update")
      expect(body?.querySelectorAll("strong")).toHaveLength(1)
      expect(enforcement.rawWrites).toEqual([])
      expect(enforcement.trustedWrites).toEqual([])
      expect(enforcement.policyNames).toEqual(["app"])
    } finally {
      enforcement.restore()
    }
  })

  it("replaces the previous article when the policy rejects a later update", () => {
    const enforcement = enforceTrustedTypes({ nativeSetHTML: false })
    try {
      const { container, rerender } = render(
        <NewsDetailBody content="# Same title\n\n<strong>Original</strong>" />
      )
      expect(container.querySelector("h1")).toHaveTextContent("Same title")
      expect(container.querySelector(".news-article-body strong")).toHaveTextContent("Original")
      enforcement.state.failPolicy = true
      rerender(<NewsDetailBody content="# Same title\n\n<strong>Updated</strong>" />)
      expect(container.querySelector(".news-article-body h1")).toHaveTextContent("Same title")
      // The identical `<strong>` tag keeps its earlier sanitized element; only its Markdown children change.
      expect(container.querySelector(".news-article-body strong")).toHaveTextContent("Updated")
      expect(container.querySelector(".news-article-body")?.textContent).not.toContain("<strong>")
      expect(container.querySelector(".news-article-body")).toHaveTextContent("Same title")
      expect(enforcement.rawWrites).toEqual([])
      expect(enforcement.trustedWrites.length).toBeGreaterThan(0)
    } finally {
      enforcement.restore()
    }
  })

  it("renders nothing in the body for empty content without throwing", () => {
    expect(() => render(<NewsDetailBody content="" />)).not.toThrow()
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
  })

  it("renders pull quotes and skips blank legacy paragraphs", () => {
    const { container } = render(
      <NewsDetailBody content={"\n\n>   Safety > first\n\n\nPlain paragraph"} />
    )
    expect(container.querySelector("blockquote.news-pullquote")?.textContent).toBe("Safety > first")
    expect(screen.getByText("Plain paragraph")).toBeInTheDocument()
  })

  it("recomputes rendered HTML when article content changes", () => {
    const { rerender } = render(<NewsDetailBody content="First article" />)
    expect(screen.getByText("First article")).toBeInTheDocument()

    rerender(<NewsDetailBody content="Second article" />)

    expect(screen.queryByText("First article")).not.toBeInTheDocument()
    expect(screen.getByText("Second article")).toBeInTheDocument()
  })

  it("places the table of contents below the article on mobile", () => {
    mediaMock.mockReturnValue(false)
    const { container } = render(<NewsDetailBody content={MARKDOWN_WITH_TOC} />)
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
    expect(container.querySelector("section")).not.toHaveClass("flex")
    expect(container.querySelector("section")).not.toHaveClass("gap-8")
  })
})
