import { useMemo } from "react"
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
function renderPlainText(content: string): string {
  const chunks = content.split(/\n{2,}/)
  const parts: string[] = []

  for (const chunk of chunks) {
    const text = chunk.trim()
    if (!text) continue

    if (text.startsWith(">")) {
      const quote = text.slice(1).trimStart()
      parts.push(`<blockquote class="news-pullquote">${escapeHtml(quote)}</blockquote>`)
      continue
    }

    parts.push(`<p>${escapeHtml(text)}</p>`)
  }

  return parts.join("")
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

export function NewsDetailBody({ content }: NewsDetailBodyProps) {
  const isDesktop = useMediaQuery("(min-width: 1024px)")
  const headings = useArticleHeadings(content)
  const showToc = headings.length >= 3

  const html = useMemo(() => {
    if (hasMarkdownSyntax(content)) {
      const raw = articleMarked.parse(content) as string
      return sanitizeArticleHtml(raw)
    }

    return renderPlainText(content)
  }, [content])

  // Every branch is sanitized: Markdown passes through sanitizeArticleHtml;
  // legacy text is HTML-escaped before tags are constructed.
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

        {articleBody}
      </div>
    </section>
  )
}
