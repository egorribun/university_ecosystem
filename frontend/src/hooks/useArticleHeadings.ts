import { useMemo } from "react"
import { marked } from "marked"
import { htmlToPlainText } from "@/utils/htmlText"
import { slugify } from "@/utils/slugify"

export interface TocEntry {
  id: string
  text: string
  level: number
}

/**
 * Extracts heading entries from Markdown content for Table of Contents.
 * Uses marked.lexer() to parse tokens without rendering — lightweight.
 * Shares slugify() with the heading renderer for guaranteed ID match.
 */
export function useArticleHeadings(content: string): TocEntry[] {
  return useMemo(() => {
    if (!content.trim()) return []

    try {
      const tokens = marked.lexer(content)
      const headings: TocEntry[] = []

      for (const token of tokens) {
        if (token.type === "heading" && (token.depth === 2 || token.depth === 3)) {
          const text = htmlToPlainText(token.text).trim()
          if (!text) continue
          headings.push({ id: slugify(text), text, level: token.depth })
        }
      }

      return headings
    } catch {
      return []
    }
  }, [content])
}
