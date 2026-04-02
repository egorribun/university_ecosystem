import { useMemo } from "react"
import { marked, type MarkedExtension, type Tokens } from "marked"
import { SafeHtml } from "@/components/ui"
import { useArticleHeadings } from "@/hooks/useArticleHeadings"
import { NewsTableOfContents } from "./NewsTableOfContents"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"

interface NewsDetailBodyProps {
  content: string
}

/* ── Custom heading renderer — adds id slugs for ToC linking ── */
const headingExtension: MarkedExtension = {
  renderer: {
    heading({ text, depth }: Tokens.Heading) {
      const slug = text
        .replace(/<[^>]+>/g, "")
        .trim()
        .toLowerCase()
        .replace(/[^\p{L}\p{N}\s-]/gu, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .slice(0, 64)

      const tag = `h${depth}`
      return `<${tag} id="${slug}" class="news-heading news-heading-${depth}">${text}</${tag}>\n`
    },
  },
}

/* ── Configure marked once ── */
marked.use({
  gfm: true,
  breaks: false,
  ...headingExtension,
})

/**
 * Detects whether content uses Markdown syntax.
 * If no Markdown features detected, applies legacy plain-text rendering
 * (drop-cap on first paragraph, > pull-quotes).
 */
function hasMarkdownSyntax(text: string): boolean {
  return /^#{1,6}\s/m.test(text) ||       // headings
    /\*\*[^*]+\*\*/m.test(text) ||          // bold
    /\*[^*]+\*/m.test(text) ||              // italic
    /^[-*+]\s/m.test(text) ||               // unordered list
    /^\d+\.\s/m.test(text) ||               // ordered list
    /\[.+\]\(.+\)/m.test(text) ||           // links
    /^```/m.test(text) ||                    // code blocks
    /\|.*\|.*\|/m.test(text) ||             // tables
    /^---+$/m.test(text)                     // horizontal rules
}

/**
 * Legacy plain-text renderer — preserves Wave 57 behavior for
 * existing articles that don't use Markdown syntax.
 */
function renderPlainText(content: string): string {
  const chunks = content.split(/\n{2,}/)
  const parts: string[] = []

  for (let i = 0; i < chunks.length; i++) {
    const text = chunks[i]?.trim()
    if (!text) continue

    // Pull-quote: lines starting with >
    if (text.startsWith(">")) {
      const quote = text.replace(/^>\s*/, "")
      parts.push(`<blockquote class="news-pullquote">${escapeHtml(quote)}</blockquote>`)
      continue
    }

    // Drop cap on first visible paragraph (only if long enough)
    const isFirst = parts.length === 0
    const isDropCap = isFirst && text.length > 200
    parts.push(
      `<p${isDropCap ? ' class="news-dropcap"' : ""}>${escapeHtml(text)}</p>`
    )
  }

  return parts.join("\n")
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
    if (!content?.trim()) return ""

    if (hasMarkdownSyntax(content)) {
      return marked.parse(content) as string
    }

    // Legacy plain-text rendering
    return renderPlainText(content)
  }, [content])

  return (
    <section
      className={cn(
        "glass-layer-surface glass-noise rounded-2xl p-6 sm:p-8 md:p-10",
        showToc && isDesktop && "flex gap-8"
      )}
    >
      {/* Table of Contents — sidebar on desktop, inline on mobile */}
      {showToc && isDesktop && (
        <aside className="shrink-0 w-56 sticky top-24 self-start">
          <NewsTableOfContents headings={headings} />
        </aside>
      )}

      <div className="flex-1 min-w-0">
        {/* Mobile ToC — above article */}
        {showToc && !isDesktop && (
          <div className="mb-6">
            <NewsTableOfContents headings={headings} />
          </div>
        )}

        <div className="news-article-body text-body leading-relaxed text-(--text-secondary)">
          <SafeHtml html={html} className="news-markdown" />
        </div>
      </div>
    </section>
  )
}
