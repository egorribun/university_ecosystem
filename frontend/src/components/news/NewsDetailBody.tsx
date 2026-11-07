import { createElement, type ReactNode, useEffect, useMemo, useState } from "react"
import { Marked, type Token, type Tokens } from "marked"
import {
  articleFragmentToReactNodes,
  decodeArticleAttribute,
  decodeArticleText,
  sanitizeArticleFragment,
  sanitizeArticleUrl,
} from "@/utils/sanitizeArticleHtml"
import { ensureWasmSanitizerInitialized } from "@/utils/wasmSanitizer"
import { NewsTableOfContents } from "./NewsTableOfContents"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"

interface NewsDetailBodyProps {
  content: string
}

interface RenderedArticle {
  tokens: readonly Token[]
}

interface ArticleHeading {
  id: string
  text: string
  level: number
}

const ARTICLE_CLASS = "news-article-body text-body leading-relaxed text-(--text-secondary)"
const RAW_VOID_TAGS = new Set([
  "area",
  "base",
  "br",
  "col",
  "embed",
  "hr",
  "img",
  "input",
  "link",
  "meta",
  "param",
  "source",
  "track",
  "wbr",
])

interface RawHtmlSequence {
  source: string
  endIndex: number
}

const getRawHtmlTag = (
  source: string
): { name: string; closing: boolean; selfClosing: boolean } | null => {
  const match = /^<\s*(\/?)\s*([a-z][a-z\d:-]*)/i.exec(source)
  if (!match) return null
  const name = (match[2] as string).toLowerCase()
  return {
    name,
    closing: match[1] === "/",
    selfClosing: !match[1] && /\/\s*>$/.test(source),
  }
}

/** Groups Marked's separate tag/text tokens into a fragment for the WASM sanitizer. */
function collectRawHtmlSequence(
  tokens: readonly Token[],
  startIndex: number,
  first: Tokens.HTML | Tokens.Tag
): RawHtmlSequence {
  const firstTag = getRawHtmlTag(first.raw)
  if (!firstTag || firstTag.closing || firstTag.selfClosing || RAW_VOID_TAGS.has(firstTag.name)) {
    return { source: first.raw, endIndex: startIndex }
  }

  const openTags = [firstTag.name]
  let source = first.raw
  let endIndex = startIndex

  for (const [offset, token] of tokens.slice(startIndex + 1).entries()) {
    const index = startIndex + offset + 1
    source += token.raw
    endIndex = index
    if (token.type !== "html") continue

    const tag = getRawHtmlTag(token.raw)
    if (!tag) continue
    if (tag.closing) {
      const matchingOpenTag = openTags.lastIndexOf(tag.name)
      if (matchingOpenTag !== -1) openTags.length = matchingOpenTag
    } else if (!tag.selfClosing && !RAW_VOID_TAGS.has(tag.name)) {
      openTags.push(tag.name)
    }

    if (openTags.length === 0) break
  }

  return { source, endIndex }
}

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

/**
 * Marked tokens stay data until React renders them. This keeps the rich article
 * surface out of HTML sinks and gives SSR and the client the same safe tree.
 */
function renderArticleMarkdown(content: string): RenderedArticle {
  const markdown = new Marked({
    gfm: true,
    breaks: false,
  })
  return { tokens: markdown.lexer(content) }
}

function getInlineText(tokens: readonly Token[]): string {
  return tokens
    .map((token) => {
      switch (token.type) {
        case "text": {
          const textToken = token as Tokens.Text
          return decodeArticleText(textToken.text)
        }
        case "escape":
          return decodeArticleText((token as Tokens.Escape).text)
        case "codespan":
          return (token as Tokens.Codespan).text
        case "strong":
        case "em":
        case "del":
        case "link":
          return getInlineText(
            (token as Tokens.Strong | Tokens.Em | Tokens.Del | Tokens.Link).tokens
          )
        case "image":
          return decodeArticleAttribute((token as Tokens.Image).text)
        case "br":
          return " "
        default:
          return ""
      }
    })
    .join("")
}

function slugifyArticleText(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/[\s-]+/g, "-")
    .slice(0, 64)
}

function collectArticleHeadings(tokens: readonly Token[]): ArticleHeading[] {
  const headings: ArticleHeading[] = []

  for (const token of tokens) {
    if (token.type !== "heading") continue
    const heading = token as Tokens.Heading
    if (heading.depth !== 2 && heading.depth !== 3) continue
    const text = getInlineText(heading.tokens).trim()
    if (!text) continue
    headings.push({ id: slugifyArticleText(text), text, level: heading.depth })
  }

  return headings
}

function SanitizedRawHtml({ source }: { source: string }) {
  const [rendered, setRendered] = useState<{ source: string; nodes: ReactNode[] } | null>(null)

  useEffect(() => {
    let active = true
    const render = (): boolean => {
      if (!active) return false
      try {
        const fragment = sanitizeArticleFragment(source)
        if (!fragment) return false
        setRendered({ source, nodes: articleFragmentToReactNodes(fragment) })
        return true
      } catch {
        // Keep the source visible as text if parsing or React-node conversion fails.
        return false
      }
    }

    if (!render()) {
      void ensureWasmSanitizerInitialized().then((ready) => {
        if (ready) render()
      })
    }

    return () => {
      active = false
    }
  }, [source])

  // Raw HTML is text in the SSR and hydration render. The approved sanitizer
  // upgrades it to the safe editor allowlist after hydration.
  return <>{rendered?.source === source ? rendered.nodes : source}</>
}

function renderInlineTokens(tokens: readonly Token[], path: string): ReactNode[] {
  const parts: ReactNode[] = []

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index] as Token
    const key = `${path}-inline-${index}`

    if (token.type === "html") {
      const sequence = collectRawHtmlSequence(tokens, index, token as Tokens.HTML | Tokens.Tag)
      parts.push(<SanitizedRawHtml key={`${key}-${sequence.source}`} source={sequence.source} />)
      index = sequence.endIndex
      continue
    }

    switch (token.type) {
      case "text":
        {
          const textToken = token as Tokens.Text
          parts.push(decodeArticleText(textToken.text))
        }
        break
      case "escape":
        parts.push(decodeArticleText((token as Tokens.Escape).text))
        break
      case "strong":
        parts.push(
          <strong key={key}>{renderInlineTokens((token as Tokens.Strong).tokens, key)}</strong>
        )
        break
      case "em":
        parts.push(<em key={key}>{renderInlineTokens((token as Tokens.Em).tokens, key)}</em>)
        break
      case "del":
        parts.push(<del key={key}>{renderInlineTokens((token as Tokens.Del).tokens, key)}</del>)
        break
      case "codespan":
        parts.push(<code key={key}>{(token as Tokens.Codespan).text}</code>)
        break
      case "br":
        parts.push(<br key={key} />)
        break
      case "link": {
        const link = token as Tokens.Link
        const href = sanitizeArticleUrl("href", link.href)
        const children = renderInlineTokens(link.tokens, key)
        parts.push(
          href ? (
            <a
              key={key}
              href={href}
              title={link.title ? decodeArticleAttribute(link.title) : undefined}
            >
              {children}
            </a>
          ) : (
            <span key={key}>{children}</span>
          )
        )
        break
      }
      case "image": {
        const image = token as Tokens.Image
        const src = sanitizeArticleUrl("src", image.href)
        const alt = decodeArticleAttribute(image.text)
        parts.push(
          src ? (
            <img
              key={key}
              src={src}
              alt={alt}
              title={image.title ? decodeArticleAttribute(image.title) : undefined}
              loading="lazy"
              decoding="async"
            />
          ) : (
            alt
          )
        )
        break
      }
    }
  }

  return parts
}

function renderBlockTokens(tokens: readonly Token[], path: string): ReactNode[] {
  const parts: ReactNode[] = []

  for (const [index, token] of tokens.entries()) {
    const key = `${path}-block-${index}`

    switch (token.type) {
      case "space":
      case "def":
        break
      case "heading": {
        const heading = token as Tokens.Heading
        const tag = `h${heading.depth}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6"
        const headingId = slugifyArticleText(getInlineText(heading.tokens))
        parts.push(
          createElement(tag, { key, id: headingId }, ...renderInlineTokens(heading.tokens, key))
        )
        break
      }
      case "paragraph":
        parts.push(<p key={key}>{renderInlineTokens((token as Tokens.Paragraph).tokens, key)}</p>)
        break
      case "blockquote":
        {
          const quote = token as Tokens.Blockquote
          parts.push(
            <blockquote key={key}>{renderBlockTokens(quote.tokens, `${key}-quote`)}</blockquote>
          )
        }
        break
      case "code": {
        const code = token as Tokens.Code
        const className =
          code.lang && /^language-[a-z0-9_+-]+$/i.test(`language-${code.lang}`)
            ? `language-${code.lang}`
            : undefined
        parts.push(
          <pre key={key}>
            <code className={className}>{code.text}</code>
          </pre>
        )
        break
      }
      case "hr":
        parts.push(<hr key={key} />)
        break
      case "list": {
        const list = token as Tokens.List
        const items = list.items.map((item, itemIndex) => {
          const itemPath = `${key}-item-${itemIndex}`
          const itemContent = item.tokens.flatMap((itemToken, tokenIndex) =>
            renderBlockTokens([itemToken], `${itemPath}-${tokenIndex}`)
          )
          return (
            <li key={itemPath}>
              {item.task ? (
                <input
                  type="checkbox"
                  checked={item.checked === true}
                  disabled
                  readOnly
                  aria-label={item.checked ? "Completed task" : "Incomplete task"}
                />
              ) : null}
              {itemContent}
            </li>
          )
        })
        if (list.ordered) {
          parts.push(
            <ol key={key} start={list.start as number}>
              {items}
            </ol>
          )
        } else {
          parts.push(<ul key={key}>{items}</ul>)
        }
        break
      }
      case "table":
        {
          const table = token as Tokens.Table
          parts.push(
            <table key={key}>
              <thead>
                <tr>
                  {table.header.map((cell, cellIndex) => (
                    <th key={`${key}-head-${cellIndex}`} align={cell.align ?? undefined}>
                      {renderInlineTokens(cell.tokens, `${key}-head-${cellIndex}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, rowIndex) => (
                  <tr key={`${key}-row-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td
                        key={`${key}-row-${rowIndex}-cell-${cellIndex}`}
                        align={cell.align ?? undefined}
                      >
                        {renderInlineTokens(
                          cell.tokens,
                          `${key}-row-${rowIndex}-cell-${cellIndex}`
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
        break
      case "html":
        {
          const html = token as Tokens.HTML | Tokens.Tag
          parts.push(<SanitizedRawHtml key={`${key}-${html.raw}`} source={html.text} />)
        }
        break
      case "text": {
        const textToken = token as Tokens.Text
        parts.push(<p key={key}>{renderInlineTokens(textToken.tokens as Token[], key)}</p>)
        break
      }
    }
  }

  return parts
}

function MarkdownArticleBody({ tokens }: { tokens: readonly Token[] }) {
  return <div className={ARTICLE_CLASS}>{renderBlockTokens(tokens, "article")}</div>
}

export function NewsDetailBody({ content }: NewsDetailBodyProps) {
  const isDesktop = useMediaQuery("(min-width: 1024px)")
  const legacyParts = useMemo(
    () => (hasMarkdownSyntax(content) ? null : renderPlainText(content)),
    [content]
  )
  const article = useMemo(
    () => (legacyParts === null ? renderArticleMarkdown(content) : { tokens: [] }),
    [content, legacyParts]
  )
  const headings = useMemo(() => collectArticleHeadings(article.tokens), [article])
  const showToc = headings.length >= 3

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

        {legacyParts !== null ? (
          <div className={ARTICLE_CLASS}>{legacyParts}</div>
        ) : (
          <MarkdownArticleBody tokens={article.tokens} />
        )}
      </div>
    </section>
  )
}

function normalizeLegacyText(text: string): string {
  // Match the HTML parser's treatment of line endings and null characters.
  return text.replace(/\r\n?/g, "\n").replace(/\0/g, "")
}
