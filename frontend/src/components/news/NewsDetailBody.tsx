import { type ReactNode, useMemo } from "react"
import { Marked, type Tokens } from "marked"
import { sanitizeArticleHtml } from "@/utils/sanitizeArticleHtml"
import { slugify } from "@/utils/slugify"
import { useArticleHeadings } from "@/hooks/useArticleHeadings"
import { NewsTableOfContents } from "./NewsTableOfContents"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"

interface NewsDetailBodyProps {
  content: string
}

/* ── Isolated marked instance — does NOT mutate the global singleton ── */
const articleMarked = new Marked({
  gfm: true,
  breaks: false,
  renderer: {
    heading({ text, depth }: Tokens.Heading) {
      const slug = slugify(text)
      const tag = `h${depth}`
      return `<${tag} id="${slug}">${text}</${tag}>\n`
    },
  },
})

/**
 * Detects whether content uses Markdown syntax.
 * If no Markdown features detected, applies legacy plain-text rendering
 * (drop-cap on first paragraph, > pull-quotes).
 */
function hasMarkdownSyntax(text: string): boolean {
  return (
    /^#{1,6}\s/m.test(text) ||
    /\*[^*]+\*/m.test(text) ||
    /^[-*+]\s/m.test(text) ||
    /^\d+\.\s/m.test(text) ||
    /\[.+\]\(.+\)/m.test(text) ||
    /^```/m.test(text) ||
    /\|.*\|.*\|/m.test(text) ||
    /^---+$/m.test(text)
  )
}

/**
 * Legacy plain-text renderer — preserves Wave 57 behavior for
 * existing articles that don't use Markdown syntax.
 */
function renderPlainText(content: string): ReactNode[] {
  const chunks = content.split(/\n{2,}/)
  const parts: ReactNode[] = []

  for (const [index, chunk] of chunks.entries()) {
    const text = chunk.trim()
    if (!text) continue

    if (text.startsWith(">")) {
      const quote = text.slice(1).trimStart()
      parts.push(
        <blockquote key={index} className="news-pullquote">
          {normalizeLegacyText(quote)}
        </blockquote>
      )
      continue
    }

    parts.push(<p key={index}>{normalizeLegacyText(text)}</p>)
  }

  return parts
}

export function NewsDetailBody({ content }: NewsDetailBodyProps) {
  const isDesktop = useMediaQuery("(min-width: 1024px)")
  const headings = useArticleHeadings(content)
  const showToc = headings.length >= 3

  const { html, textOnly, plainText } = useMemo(() => {
    if (hasMarkdownSyntax(content)) {
      const raw = articleMarked.parse(content) as string
      return {
        html: sanitizeArticleHtml(raw),
        textOnly: typeof document === "undefined",
        plainText: null,
      }
    }

    return { html: "", textOnly: false, plainText: renderPlainText(content) }
  }, [content])

  // The server's Markdown fallback may contain decoded HTML entities and is
  // rendered as text below. Browser Markdown is sanitized; legacy text escaped.
  // prettier-ignore
  const articleBody = <div className="news-article-body text-body leading-relaxed text-(--text-secondary)" dangerouslySetInnerHTML={{ __html: html }} /> // nosemgrep: typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml

  return (
    <section
      className={cn(
        "glass-layer-surface glass-noise rounded-2xl p-6 sm:p-8 md:p-10",
        showToc && isDesktop && "flex gap-8"
      )}
    >
      {showToc && isDesktop && (
        <aside className="shrink-0 w-56 sticky top-24 self-start">
          <NewsTableOfContents headings={headings} />
        </aside>
      )}

      <div className="flex-1 min-w-0">
        {showToc && !isDesktop && (
          <div className="mb-6">
            <NewsTableOfContents headings={headings} />
          </div>
        )}

        {plainText !== null ? (
          <div className="news-article-body text-body leading-relaxed text-(--text-secondary)">
            {plainText}
          </div>
        ) : textOnly ? (
          <div className="news-article-body text-body leading-relaxed text-(--text-secondary)">
            {html}
          </div>
        ) : (
          articleBody
        )}
      </div>
    </section>
  )
}

function normalizeLegacyText(text: string): string {
  // Match the HTML parser's treatment of line endings and null characters.
  return text.replace(/\r\n?/g, "\n").replace(/\0/g, "")
}
